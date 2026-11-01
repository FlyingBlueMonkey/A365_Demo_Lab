import os
import argparse
import json
from typing import cast

from dotenv import load_dotenv
from agents import Agent, Runner
from microsoft.opentelemetry.a365.core import BaggageBuilder
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from a365_bootstrap import configure_agent365, load_identity

load_dotenv()


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


def main(check_config: bool = False) -> None:
    identity = load_identity()
    if check_config:
        print(json.dumps({
            "tenant_id": identity.tenant_id,
            "blueprint_id": identity.blueprint_id,
            "agent_id": identity.agent_id,
            "registration_id": identity.registration_id,
            "live_registration_verified": False,
        }, indent=2))
        return
    question = (
        "Give me a five-item security review checklist "
        "for a Python AI agent that calls external tools."
    )

    baggage = (
        BaggageBuilder()
        .tenant_id(identity.tenant_id)
        .agent_id(identity.agent_id)
        .agent_blueprint_id(identity.blueprint_id)
        .agent_name("Security Architecture Assistant")
        .build()
    )

    configure_agent365()
    try:
        agent = build_agent()
        with baggage:
            result = Runner.run_sync(agent, question)
        print(result.final_output)
    finally:
        provider = cast(TracerProvider, trace.get_tracer_provider())
        try:
            provider.force_flush()
        finally:
            provider.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-config", action="store_true", help="Validate local identity metadata without network calls")
    main(check_config=parser.parse_args().check_config)