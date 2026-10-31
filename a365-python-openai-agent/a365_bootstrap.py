import os
from functools import lru_cache

from azure.identity import ClientSecretCredential
from microsoft.opentelemetry import use_microsoft_opentelemetry
from opentelemetry.sdk.resources import Resource


@lru_cache(maxsize=1)
def _credential() -> ClientSecretCredential:
    tenant_id = os.getenv("AZURE_TENANT_ID") or os.environ[
        "AGENT365OBSERVABILITY__TENANTID"
    ]
    client_id = os.getenv("AZURE_CLIENT_ID") or os.environ[
        "AGENT365OBSERVABILITY__CLIENTID"
    ]
    client_secret = os.getenv("AZURE_CLIENT_SECRET") or os.environ[
        "AGENT365OBSERVABILITY__CLIENTSECRET"
    ]

    return ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )


def resolve_observability_token(
    agent_id: str,
    tenant_id: str,
) -> str:
    """
    Obtain a token for the Agent 365 observability resource.

    The agent_id and tenant_id are supplied by the exporter.
    Validate them against the provisioned configuration if your
    application serves more than one agent or tenant.
    """
    expected_tenant = os.getenv("AZURE_TENANT_ID") or os.environ[
        "AGENT365OBSERVABILITY__TENANTID"
    ]

    if tenant_id and tenant_id != expected_tenant:
        raise ValueError("Unexpected tenant ID supplied to token resolver")

    expected_agent = (
        os.getenv("A365_AGENT_ID")
        or os.getenv("AGENT365OBSERVABILITY__AGENTID")
        or os.environ["AGENT_ID"]
    )
    if agent_id != expected_agent:
        raise ValueError("Unexpected agent ID supplied to token resolver")

    client_id = os.getenv("AZURE_CLIENT_ID") or os.environ[
        "AGENT365OBSERVABILITY__CLIENTID"
    ]
    if agent_id != client_id:
        raise ValueError(
            "This service-principal sample requires the agent ID to match the client ID"
        )

    scope = os.getenv(
        "A365_OBSERVABILITY_SCOPE",
        "api://9b975845-388f-4429-889e-eab1ef63949c/.default",
    )
    token = _credential().get_token(scope)

    return f"Bearer {token.token}"


def configure_agent365() -> None:
    use_microsoft_opentelemetry(
        enable_a365=True,
        resource=Resource.create({
            "service.name": "security-architecture-assistant",
            "service.namespace": "chromeweb.custom-agents",
        }),
        a365_token_resolver=resolve_observability_token,
        a365_cluster_category="prod",
        a365_use_s2s_endpoint=True,
        a365_enable_observability_exporter=(
            os.getenv("ENABLE_A365_OBSERVABILITY_EXPORTER", "true").lower() == "true"
        ),
        a365_suppress_invoke_agent_input=True,
        a365_exporter_disable_offline_storage=True,
        disable_logging=True,
        disable_metrics=True,
    )