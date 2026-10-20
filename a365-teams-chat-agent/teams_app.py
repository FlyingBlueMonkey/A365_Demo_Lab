import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from aiohttp import web
from agents import RunConfig, Runner
from agents.tracing import set_trace_processors
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv
from microsoft_agents.activity import Activity, Mention
from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.aiohttp import (
    CloudAdapter,
    jwt_authorization_middleware,
    start_agent_process,
)
from microsoft_agents.hosting.core import (
    AgentApplication,
    AgentAuthConfiguration,
    MemoryStorage,
    TurnContext,
)
from microsoft_agents_a365.observability.core import BaggageBuilder
from microsoft_agents_a365.observability.extensions.openai import OpenAIAgentsTraceInstrumentor

from a365_bootstrap import configure_agent365, required_setting
from app import AGENT_NAME, build_agent
from graph_chat import GraphChatReader


@dataclass(frozen=True)
class TeamsSettings:
    tenant_id: str
    bot_client_id: str
    bot_client_secret: str
    agent_id: str
    max_messages: int = 100

    @classmethod
    def from_env(cls):
        required_setting("OPENAI_API_KEY")
        limit = int(os.getenv("TEAMS_MAX_MESSAGES", "100"))
        if not 1 <= limit <= 200:
            raise ValueError("TEAMS_MAX_MESSAGES must be between 1 and 200")
        return cls(
            required_setting("AZURE_TENANT_ID", "AGENT365OBSERVABILITY__TENANTID"),
            required_setting("TEAMS_BOT_CLIENT_ID"),
            required_setting("TEAMS_BOT_CLIENT_SECRET"),
            required_setting("A365_AGENT_ID"),
            limit,
        )


def summarize_chat(settings: TeamsSettings, chat_id: str) -> str:
    with ClientSecretCredential(
        tenant_id=settings.tenant_id,
        client_id=settings.bot_client_id,
        client_secret=settings.bot_client_secret,
    ) as credential:
        with httpx.Client() as client:
            reader = GraphChatReader(
                client,
                lambda: credential.get_token("https://graph.microsoft.com/.default").token,
            )
            baggage = (
                BaggageBuilder()
                .tenant_id(settings.tenant_id)
                .agent_id(settings.agent_id)
                .agent_name(AGENT_NAME)
                .build()
            )
            with baggage:
                result = Runner.run_sync(
                    build_agent(reader, chat_id, settings.max_messages),
                    "Summarize the selected Teams chat.",
                    max_turns=4,
                    run_config=RunConfig(trace_include_sensitive_data=False),
                )
            return str(result.final_output)


async def handle_message(
    context: TurnContext, settings: TeamsSettings, activity: Activity | None = None,
) -> None:
    activity = activity or context.activity
    conversation = activity.conversation
    if activity.channel_id != "msteams" or not conversation or not activity.recipient:
        return
    channel_data = activity.channel_data or {}
    tenant_id = (channel_data.get("tenant") or {}).get("id")
    if tenant_id != settings.tenant_id:
        return
    if conversation.tenant_id and conversation.tenant_id != settings.tenant_id:
        return
    if activity.from_property and (
        activity.from_property.id == activity.recipient.id
        or activity.from_property.role == "bot"
    ):
        return
    mentions = [Mention.model_validate(entity.model_dump()) for entity in TurnContext.get_mentions(activity)]
    bot_mentions = [
        mention for mention in mentions
        if mention.mentioned and mention.mentioned.id == activity.recipient.id
    ]
    if not bot_mentions:
        return
    if conversation.conversation_type != "groupChat" or channel_data.get("channel"):
        await context.send_activity("This agent summarizes group chats only. Add it to a group chat and mention it there.")
        return
    if not conversation.id or not conversation.id.startswith("19:") or ";" in conversation.id:
        await context.send_activity("Unable to identify this group chat.")
        return
    command = activity.text or ""
    for mention in bot_mentions:
        if mention.text:
            command = command.replace(mention.text, "")
    command = command.strip().lower().rstrip(".!?")
    if command not in {"summarize", "summary", "summarize this chat", "summarize this conversation"}:
        await context.send_activity("Mention me with 'summarize this chat' to summarize this group chat.")
        return
    await context.send_activity("Summarizing recent messages in this chat...")
    try:
        summary = await asyncio.to_thread(summarize_chat, settings, conversation.id)
    except Exception:
        await context.send_activity(
            "Unable to summarize this chat. Check the app's chat-specific consent, "
            "service configuration, and model availability."
        )
        return
    if not summary.strip():
        summary = "No summary was returned."
    if len(summary) > 24000:
        summary = summary[:23900] + "\n[Summary output truncated.]"
    for offset in range(0, len(summary), 3000):
        await context.send_activity(summary[offset:offset + 3000])


def create_app(settings: TeamsSettings) -> web.Application:
    auth = AgentAuthConfiguration(
        client_id=settings.bot_client_id,
        client_secret=settings.bot_client_secret,
        tenant_id=settings.tenant_id,
        scopes=["https://api.botframework.com/.default"],
    )
    connections = MsalConnectionManager({"SERVICE_CONNECTION": auth})
    adapter = CloudAdapter(connection_manager=connections)
    agent = AgentApplication(
        storage=MemoryStorage(),
        adapter=adapter,
        connection_manager=connections,
    )
    tasks: set[asyncio.Task] = set()

    def completed(task):
        tasks.discard(task)
        if not task.cancelled() and task.exception():
            logging.getLogger(__name__).error("Teams background delivery failed; check bot configuration and connectivity.")

    @agent.activity("message")
    async def on_message(context, _state):
        original_activity = context.activity
        reference = original_activity.get_conversation_reference()

        async def process(continued_context):
            await handle_message(continued_context, settings, original_activity)

        task = asyncio.create_task(adapter.continue_conversation(
            reference=reference,
            callback=process,
            bot_app_id=settings.bot_client_id,
        ))
        tasks.add(task)
        task.add_done_callback(completed)

    async def on_error(context, _error):
        await context.send_activity("The agent could not complete this request.")

    adapter.on_turn_error = on_error

    @web.middleware
    async def authentication(request, handler):
        if request.path == "/healthz" and request.method == "GET":
            return await handler(request)
        authorization = request.headers.get("Authorization", "").split()
        if len(authorization) != 2 or authorization[0].lower() != "bearer":
            raise web.HTTPUnauthorized()
        return await jwt_authorization_middleware(request, handler)

    async def messages(request):
        return await start_agent_process(request, agent, adapter)

    async def health(_request):
        return web.json_response({"status": "ok"})

    async def shutdown(_application):
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=30)
            except asyncio.TimeoutError:
                logging.getLogger(__name__).warning("Pending Teams requests cancelled during shutdown.")

    application = web.Application(middlewares=[authentication], client_max_size=1024 * 1024)
    application["agent_configuration"] = auth
    application.router.add_post("/api/messages", messages)
    application.router.add_get("/healthz", health)
    application.on_shutdown.append(shutdown)
    return application


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))
    settings = TeamsSettings.from_env()
    configure_agent365()
    set_trace_processors([])
    OpenAIAgentsTraceInstrumentor().instrument()
    web.run_app(create_app(settings), host="0.0.0.0", port=int(os.getenv("PORT", "3978")))


if __name__ == "__main__":
    main()