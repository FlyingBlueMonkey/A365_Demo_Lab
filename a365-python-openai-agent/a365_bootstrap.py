import base64
import json
import math
import os
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from uuid import UUID

import httpx
from microsoft.opentelemetry import use_microsoft_opentelemetry
from opentelemetry.sdk.resources import Resource


OBSERVABILITY_RESOURCE = "9b975845-388f-4429-889e-eab1ef63949c"
OBSERVABILITY_SCOPE = f"api://{OBSERVABILITY_RESOURCE}/.default"
FMI_SCOPE = "api://AzureADTokenExchange/.default"
REFRESH_SKEW_SECONDS = 60


@dataclass(frozen=True)
class Agent365Identity:
    tenant_id: str
    blueprint_id: str
    agent_id: str
    registration_id: str


def _identifier(value: str | None, setting: str) -> str:
    try:
        identifier = UUID(value or "")
        if not identifier.int:
            raise ValueError
        return str(identifier)
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"{setting} must be a nonzero UUID") from None


def _configuration(filename: str) -> dict:
    directory = Path(os.getenv("A365_CONFIG_DIR", str(Path(__file__).parent)))
    path = directory / filename
    if not path.exists():
        return {}
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (OSError, ValueError):
        raise ValueError(f"Cannot read {filename} as a configuration object") from None


def _setting(names: tuple[str, ...], fallback: str | None = None) -> str | None:
    return next((os.environ[name] for name in names if os.getenv(name)), fallback)


def load_identity() -> Agent365Identity:
    """Load local registration metadata; this is not a live catalog verification."""
    config = _configuration("a365.config.json")
    generated = _configuration("a365.generated.config.json")
    identity = Agent365Identity(
        tenant_id=_identifier(_setting(
            ("AZURE_TENANT_ID", "AGENT365OBSERVABILITY__TENANTID"), config.get("tenantId")
        ), "AZURE_TENANT_ID / tenantId"),
        blueprint_id=_identifier(_setting(
            ("A365_BLUEPRINT_ID", "AGENT365OBSERVABILITY__BLUEPRINTID", "AZURE_CLIENT_ID",
             "AGENT365OBSERVABILITY__CLIENTID"), generated.get("agentBlueprintId")
        ), "A365_BLUEPRINT_ID / agentBlueprintId"),
        agent_id=_identifier(_setting(
            ("A365_AGENT_ID", "AGENT365OBSERVABILITY__AGENTID", "AGENT_ID"),
            generated.get("agenticAppId")
        ), "A365_AGENT_ID / agenticAppId"),
        registration_id=_identifier(_setting(
            ("A365_REGISTRATION_ID",), generated.get("agentRegistrationId")
        ), "A365_REGISTRATION_ID / agentRegistrationId (run A365 registration first)"),
    )
    if identity.agent_id == identity.blueprint_id:
        raise ValueError("Agent instance ID must differ from the Agent Blueprint client ID")
    return identity


class AgentInstanceTokenResolver:
    """Cache the final app-only agent-instance token acquired through blueprint FMI."""
    def __init__(self, identity: Agent365Identity, blueprint_secret: str) -> None:
        if not blueprint_secret.strip():
            raise ValueError("A365_BLUEPRINT_CLIENT_SECRET is required for live export")
        self.identity = identity
        self._secret = blueprint_secret
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def _request_token(self, client: httpx.Client, fields: dict[str, str]) -> dict:
        endpoint = f"https://login.microsoftonline.com/{self.identity.tenant_id}/oauth2/v2.0/token"
        try:
            response = client.post(endpoint, data=fields)
            response.raise_for_status()
            result = response.json()
            if (
                not isinstance(result, dict)
                or not isinstance(result.get("access_token"), str)
                or not result["access_token"].strip()
                or str(result.get("token_type", "")).lower() != "bearer"
            ):
                raise ValueError
            return result
        except (httpx.HTTPError, ValueError, TypeError):
            raise RuntimeError(
                "Agent 365 token exchange failed; check blueprint credentials, "
                "agent registration, tenant, and connectivity. Response bodies are not logged."
            ) from None

    def _validate_token(self, result: dict, requested_at: float) -> tuple[str, float]:
        """Apply routing/type guards to an Entra HTTPS response, not JWT signature verification."""
        try:
            token = result["access_token"]
            parts = token.split(".")
            if len(parts) != 3 or not all(parts):
                raise ValueError
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            if not isinstance(claims, dict):
                raise ValueError
            roles = claims.get("roles", [])
            app_only = claims.get("idtyp") == "app" or (
                "idtyp" not in claims and (
                    bool(roles) or (bool(claims.get("oid")) and claims.get("oid") == claims.get("sub"))
                )
            )
            clients = [claims[name] for name in ("azp", "appid") if name in claims]
            if (
                "scp" in claims or not app_only
                or not isinstance(roles, list)
                or not all(isinstance(role, str) and role.strip() for role in roles)
                or ("idtyp" in claims and claims["idtyp"] != "app")
                or claims.get("aud") not in (OBSERVABILITY_RESOURCE, f"api://{OBSERVABILITY_RESOURCE}")
                or _identifier(claims.get("tid"), "token tenant") != self.identity.tenant_id
                or not clients
                or any(_identifier(value, "token client") != self.identity.agent_id for value in clients)
            ):
                raise ValueError
            if isinstance(claims["exp"], bool):
                raise ValueError
            expiry = float(claims["exp"])
            if "expires_in" in result:
                lifetime = float(result["expires_in"])
                if isinstance(result["expires_in"], bool) or not math.isfinite(lifetime) or lifetime <= 0:
                    raise ValueError
                expiry = min(expiry, requested_at + lifetime)
            if not math.isfinite(expiry) or expiry <= time.time() + REFRESH_SKEW_SECONDS:
                raise ValueError
            return token, expiry
        except (ValueError, TypeError, KeyError, OverflowError):
            raise RuntimeError("Invalid app-only agent-instance observability token; no token was cached") from None

    def __call__(self, agent_id: str, tenant_id: str) -> str:
        if (
            _identifier(agent_id, "export agent") != self.identity.agent_id
            or _identifier(tenant_id, "export tenant") != self.identity.tenant_id
        ):
            raise ValueError("Export tenant/agent must match the configured registered agent instance")
        with self._lock:
            if self._token and time.time() < self._expires_at - REFRESH_SKEW_SECONDS:
                return self._token
            self._token = None
            self._expires_at = 0.0
            with httpx.Client(timeout=30, follow_redirects=False) as client:
                assertion = self._request_token(client, {
                    "client_id": self.identity.blueprint_id,
                    "client_secret": self._secret,
                    "grant_type": "client_credentials",
                    "scope": FMI_SCOPE,
                    "fmi_path": self.identity.agent_id,
                })
                requested_at = time.time()
                result = self._request_token(client, {
                    "client_id": self.identity.agent_id,
                    "grant_type": "client_credentials",
                    "scope": OBSERVABILITY_SCOPE,
                    "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
                    "client_assertion": assertion["access_token"],
                })
            self._token, self._expires_at = self._validate_token(result, requested_at)
            return self._token


@lru_cache(maxsize=1)
def _token_resolver() -> AgentInstanceTokenResolver:
    secret = _setting(("A365_BLUEPRINT_CLIENT_SECRET", "AZURE_CLIENT_SECRET",
                       "AGENT365OBSERVABILITY__CLIENTSECRET"), "")
    return AgentInstanceTokenResolver(load_identity(), secret or "")


def resolve_observability_token(agent_id: str, tenant_id: str) -> str:
    return _token_resolver()(agent_id, tenant_id)


def configure_agent365() -> None:
    identity = load_identity()
    exporting = os.getenv("ENABLE_A365_OBSERVABILITY_EXPORTER", "true").lower() == "true"
    if exporting:
        resolve_observability_token(identity.agent_id, identity.tenant_id)
    use_microsoft_opentelemetry(
        enable_a365=True,
        resource=Resource.create({
            "service.name": "security-architecture-assistant",
            "service.namespace": "chromeweb.custom-agents",
        }),
        a365_token_resolver=resolve_observability_token,
        a365_cluster_category="prod",
        a365_use_s2s_endpoint=True,
        a365_enable_observability_exporter=exporting,
        a365_suppress_invoke_agent_input=True,
        a365_exporter_disable_offline_storage=True,
        disable_logging=True,
        disable_metrics=True,
    )