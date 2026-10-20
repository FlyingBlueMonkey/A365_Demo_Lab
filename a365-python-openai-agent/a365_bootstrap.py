import os
from typing import Optional

from azure.identity import ClientSecretCredential
from microsoft_agents_a365.observability.core import (
    Agent365ExporterOptions,
    configure,
)


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
) -> Optional[str]:
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

    scope = os.getenv(
        "A365_OBSERVABILITY_SCOPE",
        "api://9b975845-388f-4429-889e-eab1ef63949c/.default",
    )
    token = _credential().get_token(scope)

    return f"Bearer {token.token}"


def configure_agent365() -> None:
    configure(
        service_name="security-architecture-assistant",
        service_namespace="chromeweb.custom-agents",
        exporter_options=Agent365ExporterOptions(
            cluster_category="dev",
            token_resolver=resolve_observability_token,
        ),
        suppress_invoke_agent_input=True,
    )