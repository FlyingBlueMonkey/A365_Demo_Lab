import os
from functools import lru_cache

from azure.identity import ClientSecretCredential
from microsoft_agents_a365.observability.core import Agent365ExporterOptions, configure


def required_setting(primary: str, fallback: str | None = None) -> str:
    value = os.getenv(primary) or (os.getenv(fallback) if fallback else None)
    if not value:
        alternative = f" (or {fallback})" if fallback else ""
        raise ValueError(f"Set {primary}{alternative} before running this agent")
    return value


@lru_cache(maxsize=1)
def _credential() -> ClientSecretCredential:
    return ClientSecretCredential(
        tenant_id=required_setting("AZURE_TENANT_ID", "AGENT365OBSERVABILITY__TENANTID"),
        client_id=required_setting("AZURE_CLIENT_ID", "AGENT365OBSERVABILITY__CLIENTID"),
        client_secret=required_setting("AZURE_CLIENT_SECRET", "AGENT365OBSERVABILITY__CLIENTSECRET"),
    )


def resolve_observability_token(agent_id: str, tenant_id: str) -> str:
    expected_tenant = required_setting("AZURE_TENANT_ID", "AGENT365OBSERVABILITY__TENANTID")
    if tenant_id and tenant_id != expected_tenant:
        raise ValueError("Unexpected tenant ID supplied to token resolver")
    expected_agent = os.environ["A365_AGENT_ID"]
    if agent_id and agent_id != expected_agent:
        raise ValueError("Unexpected agent ID supplied to token resolver")
    scope = os.getenv(
        "A365_OBSERVABILITY_SCOPE",
        "api://9b975845-388f-4429-889e-eab1ef63949c/.default",
    )
    return f"Bearer {_credential().get_token(scope).token}"


def configure_agent365() -> None:
    _credential()
    if not configure(
        service_name="teams-chat-summary-assistant",
        service_namespace="chromeweb.custom-agents",
        exporter_options=Agent365ExporterOptions(
            cluster_category="dev",
            token_resolver=resolve_observability_token,
        ),
        suppress_invoke_agent_input=True,
    ):
        raise RuntimeError("Agent 365 observability configuration failed")