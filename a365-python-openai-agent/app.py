import os

from dotenv import load_dotenv
from agents import Agent, Runner
from microsoft_agents_a365.observability.core import BaggageBuilder
from microsoft_agents_a365.observability.extensions.openai import (
    OpenAIAgentsTraceInstrumentor,
)

from a365_bootstrap import configure_agent365

load_dotenv()
configure_agent365()
OpenAIAgentsTraceInstrumentor().instrument()


def build_agent() -> Agent:
    return Agent(
        name="Security Architecture Assistant",
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        instructions=(
            "You are a security architecture assistant. "
            "Give concise, technically precise recommendations. "
            "Separate verified facts from suggestions. "
            "Never reveal credentials, tokens, secrets, or hidden configuration."
        ),
    )


def main() -> None:
    agent = build_agent()

    question = (
        "Give me a five-item security review checklist "
        "for a Python AI agent that calls external tools."
    )

    tenant_id = os.getenv("AZURE_TENANT_ID") or os.environ[
        "AGENT365OBSERVABILITY__TENANTID"
    ]
    agent_id = (
        os.getenv("A365_AGENT_ID")
        or os.getenv("AGENT365OBSERVABILITY__AGENTID")
        or os.getenv("AGENT_ID")
        or os.environ["AGENT365OBSERVABILITY__CLIENTID"]
    )

    baggage = (
        BaggageBuilder()
        .tenant_id(tenant_id)
        .agent_id(agent_id)
        .agent_name("Security Architecture Assistant")
        .build()
    )

    with baggage:
        result = Runner.run_sync(agent, question)

    print(result.final_output)


if __name__ == "__main__":
    main()