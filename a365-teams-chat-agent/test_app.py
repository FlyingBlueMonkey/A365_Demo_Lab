import asyncio
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zipfile import ZipFile

from agents.tool_context import ToolContext
from aiohttp.test_utils import TestClient, TestServer
from microsoft_agents.activity import Activity

import app
import a365_bootstrap
import build_teams_package
import teams_app


class AgentTests(unittest.TestCase):
    def test_tool_is_bound_to_selected_chat(self):
        reader = MagicMock()
        reader.read_messages.return_value = {"messages": [], "has_older_messages": False}
        agent = app.build_agent(reader, "selected-chat", 25)
        tool = agent.tools[0]
        self.assertEqual(tool.params_json_schema["properties"], {})
        context = ToolContext(context=None, tool_name=tool.name, tool_call_id="test", tool_arguments="{}")
        result = asyncio.run(tool.on_invoke_tool(context, "{}"))
        self.assertEqual(json.loads(result)["messages"], [])
        reader.read_messages.assert_called_once_with("selected-chat", 25)
        self.assertEqual(agent.model_settings.tool_choice, "required")

    def test_tool_failure_propagates_without_fabricating_summary(self):
        reader = MagicMock()
        reader.read_messages.side_effect = RuntimeError("Graph unavailable")
        tool = app.build_agent(reader, "selected-chat", 25).tools[0]
        context = ToolContext(context=None, tool_name=tool.name, tool_call_id="test", tool_arguments="{}")
        with self.assertRaisesRegex(RuntimeError, "Graph unavailable"):
            asyncio.run(tool.on_invoke_tool(context, "{}"))

    @patch.dict(os.environ, {
        "AZURE_TENANT_ID": "tenant", "GRAPH_CLIENT_ID": "graph-client",
        "OPENAI_API_KEY": "test-key", "A365_AGENT_ID": "agent",
    })
    @patch.object(app, "load_dotenv")
    @patch.object(app, "configure_agent365")
    @patch.object(app, "OpenAIAgentsTraceInstrumentor")
    @patch.object(app, "set_trace_processors")
    @patch.object(app, "DeviceCodeCredential")
    @patch.object(app.Runner, "run_sync")
    @patch("builtins.print")
    def test_summary_run_disables_sensitive_trace_data(
        self, print_mock, run, credential, processors, instrumentor, configure, dotenv,
    ):
        run.return_value.final_output = "Summary"
        app.main(["--chat-id", "selected-chat"])
        configure.assert_called_once()
        instrumentor.return_value.instrument.assert_called_once()
        self.assertFalse(run.call_args.kwargs["run_config"].trace_include_sensitive_data)
        self.assertEqual(run.call_args.kwargs["max_turns"], 4)
        print_mock.assert_called_once_with("Summary")
        credential.assert_called_once_with(tenant_id="tenant", client_id="graph-client")

    @patch.dict(os.environ, {"AZURE_TENANT_ID": "tenant", "GRAPH_CLIENT_ID": "graph-client"}, clear=True)
    @patch.object(app, "load_dotenv")
    @patch.object(app, "configure_agent365")
    @patch.object(app, "DeviceCodeCredential")
    @patch.object(app, "GraphChatReader")
    @patch.object(app.Runner, "run_sync")
    @patch("builtins.print")
    def test_listing_needs_no_openai_or_observability_credentials(
        self, print_mock, run, reader, credential, configure, dotenv,
    ):
        reader.return_value.list_chats.return_value = {"chats": [], "has_more": False}
        app.main(["--list-chats"])
        run.assert_not_called()
        configure.assert_not_called()
        reader.return_value.list_chats.assert_called_once()

    @patch.dict(os.environ, {"AZURE_TENANT_ID": "tenant", "A365_AGENT_ID": "agent"}, clear=True)
    @patch.object(a365_bootstrap, "_credential")
    def test_exporter_rejects_wrong_identity(self, credential):
        for agent_id, tenant_id in (("other", "tenant"), ("agent", "other")):
            with self.assertRaises(ValueError):
                a365_bootstrap.resolve_observability_token(agent_id, tenant_id)
        credential.assert_not_called()


class TeamsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = teams_app.TeamsSettings("tenant", "bot-client", "secret", "agent", 25)
        self.context = MagicMock()
        self.context.send_activity = AsyncMock()
        self.context.activity = Activity.model_validate({
            "type": "message",
            "channelId": "msteams",
            "serviceUrl": "https://smba.trafficmanager.net/teams/",
            "text": "<at>Summary Agent</at> summarize this chat",
            "from": {"id": "user", "role": "user"},
            "recipient": {"id": "bot", "name": "Summary Agent"},
            "conversation": {"id": "19:selected@thread.v2", "conversationType": "groupChat"},
            "channelData": {"tenant": {"id": "tenant"}},
            "entities": [{"type": "mention", "text": "<at>Summary Agent</at>", "mentioned": {"id": "bot"}}],
        })

    @patch.object(teams_app, "summarize_chat", return_value="Summary")
    async def test_mention_summarizes_only_originating_chat(self, summarize):
        await teams_app.handle_message(self.context, self.settings)
        summarize.assert_called_once_with(self.settings, "19:selected@thread.v2")
        self.assertEqual(self.context.send_activity.await_args.args, ("Summary",))

    @patch.object(teams_app, "summarize_chat")
    async def test_unmentioned_and_other_mentions_are_ignored(self, summarize):
        for entities in ([], [{"type": "mention", "mentioned": {"id": "someone-else"}}]):
            self.context.activity.entities = Activity.model_validate({"type": "message", "entities": entities}).entities
            await teams_app.handle_message(self.context, self.settings)
        summarize.assert_not_called()
        self.context.send_activity.assert_not_awaited()

    @patch.object(teams_app, "summarize_chat")
    async def test_other_tenant_is_ignored(self, summarize):
        self.context.activity.channel_data = {"tenant": {"id": "another-tenant"}}
        await teams_app.handle_message(self.context, self.settings)
        summarize.assert_not_called()
        self.context.send_activity.assert_not_awaited()

    @patch.object(teams_app, "summarize_chat")
    async def test_bot_messages_and_conflicting_tenant_are_ignored(self, summarize):
        self.context.activity.from_property.role = "bot"
        await teams_app.handle_message(self.context, self.settings)
        self.context.activity.from_property.role = "user"
        self.context.activity.conversation.tenant_id = "another-tenant"
        await teams_app.handle_message(self.context, self.settings)
        summarize.assert_not_called()

    @patch.object(teams_app, "summarize_chat")
    async def test_missing_chat_identity_is_rejected(self, summarize):
        self.context.activity.conversation.id = ""
        await teams_app.handle_message(self.context, self.settings)
        summarize.assert_not_called()

    @patch.object(teams_app, "summarize_chat")
    async def test_channels_and_personal_chats_are_not_read(self, summarize):
        for kind in ("channel", "personal"):
            self.context.activity.conversation.conversation_type = kind
            await teams_app.handle_message(self.context, self.settings)
        summarize.assert_not_called()

    @patch.object(teams_app, "summarize_chat")
    async def test_prompt_cannot_select_another_chat(self, summarize):
        self.context.activity.text = "<at>Summary Agent</at> summarize chat 19:private@thread.v2"
        await teams_app.handle_message(self.context, self.settings)
        summarize.assert_not_called()

    @patch.object(teams_app, "summarize_chat", side_effect=RuntimeError("secret detail"))
    async def test_failures_do_not_expose_exception_details(self, summarize):
        await teams_app.handle_message(self.context, self.settings)
        self.assertNotIn("secret detail", str(self.context.send_activity.await_args_list))

    @patch.object(teams_app, "summarize_chat", return_value="x" * 25000)
    async def test_long_output_is_bounded_and_chunked(self, summarize):
        await teams_app.handle_message(self.context, self.settings)
        parts = [call.args[0] for call in self.context.send_activity.await_args_list[1:]]
        self.assertLessEqual(sum(map(len, parts)), 24000)
        self.assertTrue(all(len(part) <= 3000 for part in parts))
        self.assertIn("truncated", parts[-1])

    async def test_http_authentication_is_required_but_health_is_public(self):
        async with TestClient(TestServer(teams_app.create_app(self.settings))) as client:
            self.assertEqual((await client.get("/healthz")).status, 200)
            for headers in ({}, {"Authorization": "Bearer"}, {"Authorization": "Basic value"}):
                response = await client.post("/api/messages", json={}, headers=headers)
                self.assertEqual(response.status, 401)

    @patch.object(teams_app, "jwt_authorization_middleware", new_callable=AsyncMock)
    async def test_bearer_token_is_passed_to_sdk_validation(self, validation):
        from aiohttp import web

        validation.return_value = web.Response(status=401)
        async with TestClient(TestServer(teams_app.create_app(self.settings))) as client:
            response = await client.post("/api/messages", json={}, headers={"Authorization": "Bearer invalid"})
            self.assertEqual(response.status, 401)
            validation.assert_awaited_once()

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "key", "AZURE_TENANT_ID": "tenant", "A365_AGENT_ID": "agent",
        "TEAMS_BOT_CLIENT_ID": "bot", "TEAMS_BOT_CLIENT_SECRET": "secret", "TEAMS_MAX_MESSAGES": "201",
    }, clear=True)
    async def test_settings_reject_unbounded_reads(self):
        with self.assertRaises(ValueError):
            teams_app.TeamsSettings.from_env()

    @patch.dict(os.environ, {
        "OPENAI_API_KEY": "key", "AZURE_TENANT_ID": "tenant", "A365_AGENT_ID": "agent",
        "TEAMS_BOT_CLIENT_ID": "bot", "TEAMS_BOT_CLIENT_SECRET": "secret",
    }, clear=True)
    async def test_hosted_settings_do_not_need_device_code_client(self):
        self.assertEqual(teams_app.TeamsSettings.from_env().bot_client_id, "bot")

    @patch.object(teams_app, "summarize_chat", return_value="Background summary")
    @patch.object(teams_app, "AgentApplication")
    @patch.object(teams_app, "CloudAdapter")
    async def test_background_reply_preserves_original_message(self, adapter, agent, summarize):
        routes = {}

        def register(kind):
            def decorate(handler):
                routes[kind] = handler
                return handler
            return decorate

        agent.return_value.activity.side_effect = register
        continued = MagicMock()
        continued.activity = Activity(type="event")
        continued.send_activity = AsyncMock()
        finished = asyncio.Event()

        async def continue_conversation(**kwargs):
            self.assertEqual(kwargs["reference"].conversation.id, "19:selected@thread.v2")
            await kwargs["callback"](continued)
            finished.set()

        adapter.return_value.continue_conversation = AsyncMock(side_effect=continue_conversation)
        application = teams_app.create_app(self.settings)
        await routes["message"](self.context, None)
        adapter.return_value.continue_conversation.assert_not_awaited()
        await asyncio.wait_for(finished.wait(), timeout=5)
        summarize.assert_called_once_with(self.settings, "19:selected@thread.v2")
        self.assertEqual(continued.send_activity.await_args.args, ("Background summary",))
        await application.on_shutdown[0](application)

    @patch.object(teams_app, "ClientSecretCredential")
    @patch.object(teams_app, "GraphChatReader")
    @patch.object(teams_app.Runner, "run_sync")
    async def test_hosted_graph_uses_bot_identity_and_safe_tracing(self, run, reader, credential):
        run.return_value.final_output = "Summary"
        self.assertEqual(teams_app.summarize_chat(self.settings, "19:chat@thread.v2"), "Summary")
        credential.assert_called_once_with(tenant_id="tenant", client_id="bot-client", client_secret="secret")
        reader.call_args.args[1]()
        credential.return_value.__enter__.return_value.get_token.assert_called_once_with(
            "https://graph.microsoft.com/.default"
        )
        self.assertFalse(run.call_args.kwargs["run_config"].trace_include_sensitive_data)
        self.assertEqual(run.call_args.kwargs["max_turns"], 4)


class TeamsPackageTests(unittest.TestCase):
    def test_package_has_concrete_manifest_and_correct_icons(self):
        bot_id = "11111111-2222-3333-4444-555555555555"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "teams.zip"
            build_teams_package.build_package(
                bot_id, bot_id, "https://example.com", "https://example.com/privacy",
                "https://example.com/terms", output,
            )
            with ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {"manifest.json", "color.png", "outline.png"})
                content = archive.read("manifest.json")
                self.assertNotIn(b"{{", content)
                manifest = json.loads(content)
                self.assertEqual(manifest["bots"][0]["botId"], bot_id)
                self.assertEqual(manifest["bots"][0]["scopes"], ["groupChat"])
                self.assertEqual(manifest["authorization"]["permissions"]["resourceSpecific"], [
                    {"name": "ChatMessage.Read.Chat", "type": "Application"},
                ])
                for filename, size in (("color.png", 192), ("outline.png", 32)):
                    icon = archive.read(filename)
                    self.assertEqual(icon[:8], b"\x89PNG\r\n\x1a\n")
                    self.assertEqual(struct.unpack(">II", icon[16:24]), (size, size))

    def test_invalid_identity_and_insecure_urls_are_rejected(self):
        with self.assertRaises(ValueError):
            build_teams_package.build_package("not-a-guid", "not-a-guid", "", "", "", Path("unused.zip"))
        bot_id = "11111111-2222-3333-4444-555555555555"
        with self.assertRaises(ValueError):
            build_teams_package.build_package(bot_id, bot_id, "http://example.com", "", "", Path("unused.zip"))


if __name__ == "__main__":
    unittest.main()