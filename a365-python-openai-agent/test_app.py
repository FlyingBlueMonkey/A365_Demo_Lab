import contextlib
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs

import httpx
import a365_bootstrap
import app


ENVIRONMENT = {
    "AZURE_TENANT_ID": "11111111-1111-1111-1111-111111111111",
    "A365_BLUEPRINT_ID": "22222222-2222-2222-2222-222222222222",
    "A365_BLUEPRINT_CLIENT_SECRET": "not-a-real-secret",
    "A365_AGENT_ID": "33333333-3333-3333-3333-333333333333",
    "A365_REGISTRATION_ID": "44444444-4444-4444-4444-444444444444",
}


class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, ENVIRONMENT, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        a365_bootstrap._token_resolver.cache_clear()
        self.addCleanup(a365_bootstrap._token_resolver.cache_clear)

    def test_supported_initializer_configuration(self) -> None:
        with patch.object(a365_bootstrap, "use_microsoft_opentelemetry") as initialize, patch.object(a365_bootstrap, "resolve_observability_token") as resolve:
            a365_bootstrap.configure_agent365()
        resolve.assert_called_once_with(ENVIRONMENT["A365_AGENT_ID"], ENVIRONMENT["AZURE_TENANT_ID"])
        options = initialize.call_args.kwargs
        self.assertTrue(options["enable_a365"])
        self.assertTrue(options["a365_use_s2s_endpoint"])
        self.assertTrue(options["a365_enable_observability_exporter"])
        self.assertTrue(options["a365_suppress_invoke_agent_input"])
        self.assertTrue(options["a365_exporter_disable_offline_storage"])
        self.assertTrue(options["disable_logging"])
        self.assertTrue(options["disable_metrics"])
        self.assertEqual(options["a365_cluster_category"], "prod")
        self.assertEqual(
            options["resource"].attributes["service.name"],
            "security-architecture-assistant",
        )

    def test_console_toggle(self) -> None:
        with patch.dict(os.environ, {"ENABLE_A365_OBSERVABILITY_EXPORTER": "false"}):
            with patch.object(a365_bootstrap, "use_microsoft_opentelemetry") as initialize:
                a365_bootstrap.configure_agent365()
        self.assertFalse(initialize.call_args.kwargs["a365_enable_observability_exporter"])

    def test_mismatched_tenant_or_agent_rejected_before_authentication(self) -> None:
        with patch.object(a365_bootstrap.AgentInstanceTokenResolver, "_request_token") as request:
            for agent_id, tenant_id in [
                (ENVIRONMENT["A365_AGENT_ID"], ENVIRONMENT["A365_REGISTRATION_ID"]),
                (ENVIRONMENT["A365_BLUEPRINT_ID"], ENVIRONMENT["AZURE_TENANT_ID"]),
            ]:
                with self.subTest(agent=agent_id, tenant=tenant_id):
                    with self.assertRaises(ValueError):
                        a365_bootstrap.resolve_observability_token(agent_id, tenant_id)
        request.assert_not_called()

    def test_blueprint_credentials_cannot_impersonate_agent_instance(self) -> None:
        with patch.dict(os.environ, {"A365_AGENT_ID": ENVIRONMENT["A365_BLUEPRINT_ID"]}):
            with self.assertRaisesRegex(ValueError, "must differ"):
                a365_bootstrap.load_identity()

    def test_registered_agent_uses_distinct_blueprint_identity(self) -> None:
        claims = {
            "tid": ENVIRONMENT["AZURE_TENANT_ID"], "azp": ENVIRONMENT["A365_AGENT_ID"],
            "aud": a365_bootstrap.OBSERVABILITY_RESOURCE, "idtyp": "app", "exp": time.time() + 3600,
        }
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        token = f"header.{payload}.signature"
        with patch.object(a365_bootstrap.AgentInstanceTokenResolver, "_request_token", side_effect=[
            {"access_token": "blueprint-assertion"},
            {"access_token": token, "token_type": "Bearer", "expires_in": 3600},
        ]) as request:
            self.assertEqual(
                a365_bootstrap.resolve_observability_token(ENVIRONMENT["A365_AGENT_ID"], ENVIRONMENT["AZURE_TENANT_ID"]),
                token,
            )
            self.assertEqual(
                a365_bootstrap.resolve_observability_token(ENVIRONMENT["A365_AGENT_ID"], ENVIRONMENT["AZURE_TENANT_ID"]),
                token,
            )
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[1]["fmi_path"], ENVIRONMENT["A365_AGENT_ID"])
        self.assertEqual(request.call_args_list[0].args[1]["client_id"], ENVIRONMENT["A365_BLUEPRINT_ID"])
        self.assertEqual(request.call_args_list[1].args[1]["client_id"], ENVIRONMENT["A365_AGENT_ID"])
        self.assertEqual(request.call_args_list[0].args[1]["scope"], a365_bootstrap.FMI_SCOPE)
        self.assertEqual(request.call_args_list[1].args[1]["scope"], a365_bootstrap.OBSERVABILITY_SCOPE)
        self.assertNotIn("client_secret", request.call_args_list[1].args[1])

    def test_generated_identifiers_are_loaded_but_secrets_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "a365.config.json").write_text(json.dumps({
                "tenantId": ENVIRONMENT["AZURE_TENANT_ID"], "clientAppId": ENVIRONMENT["A365_REGISTRATION_ID"],
            }))
            (Path(directory) / "a365.generated.config.json").write_text(json.dumps({
                "agentBlueprintId": ENVIRONMENT["A365_BLUEPRINT_ID"],
                "agenticAppId": ENVIRONMENT["A365_AGENT_ID"],
                "agentRegistrationId": ENVIRONMENT["A365_REGISTRATION_ID"],
                "agentBlueprintClientSecret": "should-not-be-used",
            }))
            with patch.dict(os.environ, {"A365_CONFIG_DIR": directory}, clear=True):
                identity = a365_bootstrap.load_identity()
                self.assertEqual(identity.agent_id, ENVIRONMENT["A365_AGENT_ID"])
                self.assertEqual(identity.blueprint_id, ENVIRONMENT["A365_BLUEPRINT_ID"])
                with self.assertRaises(ValueError):
                    a365_bootstrap._token_resolver()

    def test_invalid_and_missing_registration_configuration_fails(self) -> None:
        with patch.object(a365_bootstrap, "_configuration", return_value={}):
            for changes in [{"A365_REGISTRATION_ID": ""}, {"A365_AGENT_ID": "placeholder"}]:
                with self.subTest(changes=changes), patch.dict(os.environ, changes):
                    with self.assertRaises(ValueError):
                        a365_bootstrap.load_identity()

    def test_check_config_does_not_export_or_reveal_secrets(self) -> None:
        with patch.object(app, "configure_agent365") as configure, contextlib.redirect_stdout(io.StringIO()) as output:
            app.main(check_config=True)
        metadata = json.loads(output.getvalue())
        self.assertFalse(metadata["live_registration_verified"])
        self.assertEqual(metadata["registration_id"], ENVIRONMENT["A365_REGISTRATION_ID"])
        self.assertNotIn(ENVIRONMENT["A365_BLUEPRINT_CLIENT_SECRET"], output.getvalue())
        configure.assert_not_called()


class TokenValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = a365_bootstrap.Agent365Identity(
            ENVIRONMENT["AZURE_TENANT_ID"], ENVIRONMENT["A365_BLUEPRINT_ID"],
            ENVIRONMENT["A365_AGENT_ID"], ENVIRONMENT["A365_REGISTRATION_ID"],
        )
        self.resolver = a365_bootstrap.AgentInstanceTokenResolver(self.identity, "not-a-real-secret")

    def response(self, **changes) -> dict:
        claims = {"tid": self.identity.tenant_id, "azp": self.identity.agent_id,
                  "aud": a365_bootstrap.OBSERVABILITY_RESOURCE, "idtyp": "app", "exp": time.time() + 3600}
        claims.update(changes)
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        return {"access_token": f"header.{payload}.signature", "token_type": "Bearer", "expires_in": 3600}

    def test_delegated_wrong_identity_audience_and_expiry_are_rejected(self) -> None:
        for changes in [{"scp": "delegated"}, {"azp": self.identity.blueprint_id},
                        {"aud": "other"}, {"tid": self.identity.registration_id},
                        {"idtyp": "user"}, {"exp": time.time() - 1}, {"roles": "not-a-list"}]:
            with self.subTest(changes=changes), self.assertRaises(RuntimeError):
                self.resolver._validate_token(self.response(**changes), time.time())

    def test_token_refresh_repeats_both_steps(self) -> None:
        with patch.object(self.resolver, "_request_token", side_effect=[
            {"access_token": "assertion"}, self.response(),
            {"access_token": "new-assertion"}, self.response(),
        ]) as request:
            self.resolver(self.identity.agent_id, self.identity.tenant_id)
            self.resolver._expires_at = time.time() + 10
            self.resolver(self.identity.agent_id, self.identity.tenant_id)
        self.assertEqual(request.call_count, 4)

    def test_invalid_token_lifetimes_and_missing_app_only_signal(self) -> None:
        for lifetime in [True, float("nan"), float("inf"), -1]:
            response = self.response()
            response["expires_in"] = lifetime
            with self.subTest(lifetime=lifetime), self.assertRaises(RuntimeError):
                self.resolver._validate_token(response, time.time())
        with self.assertRaises(RuntimeError):
            self.resolver._validate_token(self.response(idtyp=None), time.time())

    def test_roleless_registered_instance_app_only_token_is_accepted(self) -> None:
        response = self.response()
        self.resolver._validate_token(response, time.time())

    def test_http_failure_does_not_leak_response_or_credentials(self) -> None:
        client = Mock()
        client.post.side_effect = httpx.ConnectError("private-secret-response")
        with self.assertRaises(RuntimeError) as raised:
            self.resolver._request_token(client, {})
        self.assertNotIn("private-secret-response", str(raised.exception))

    def test_redirects_and_missing_bearer_token_are_rejected(self) -> None:
        for status, payload in [(302, {}), (200, {"access_token": "bad", "token_type": "other"})]:
            with self.subTest(status=status):
                with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))) as client:
                    with self.assertRaises(RuntimeError):
                        self.resolver._request_token(client, {})

    def test_real_form_encoding_uses_blueprint_then_agent_assertion(self) -> None:
        requests = []

        def handle(request: httpx.Request) -> httpx.Response:
            requests.append(parse_qs(request.content.decode()))
            response = {"access_token": "intermediate-assertion", "token_type": "Bearer"} if len(requests) == 1 else self.response()
            return httpx.Response(200, json=response)

        client_class = httpx.Client
        with patch.object(a365_bootstrap.httpx, "Client", side_effect=lambda **kwargs: client_class(transport=httpx.MockTransport(handle), **kwargs)) as factory:
            self.resolver(self.identity.agent_id, self.identity.tenant_id)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["client_id"], [self.identity.blueprint_id])
        self.assertEqual(requests[0]["fmi_path"], [self.identity.agent_id])
        self.assertEqual(requests[1]["client_assertion"], ["intermediate-assertion"])
        self.assertEqual(requests[1]["client_id"], [self.identity.agent_id])
        self.assertFalse(factory.call_args.kwargs["follow_redirects"])


@unittest.skipUnless(shutil.which("pwsh"), "PowerShell 7 is required for registration-helper tests")
class RegistrationWorkflowTests(unittest.TestCase):
    def run_helper(self, flags: str, generated: dict) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "register_agent.ps1"
            script.write_text((Path(__file__).parent / script.name).read_text())
            (root / "a365.config.json").write_text("{}")
            (root / "a365.generated.config.json").write_text(json.dumps(generated))
            environment = {**os.environ, "TEST_REGISTRATION_SCRIPT": str(script)}
            command = (
                "function a365 { Write-Output ('MOCK_CLI ' + ($args -join ' ')); "
                "$global:LASTEXITCODE = 0 }; & $env:TEST_REGISTRATION_SCRIPT " + flags
            )
            return subprocess.run([shutil.which("pwsh"), "-NoProfile", "-NonInteractive", "-Command", command],
                                  env=environment, capture_output=True, text=True, timeout=30)

    def test_preview_apply_and_registration_only_never_use_live_cli(self) -> None:
        generated = {"agentBlueprintId": ENVIRONMENT["A365_BLUEPRINT_ID"],
                     "agenticAppId": ENVIRONMENT["A365_AGENT_ID"],
                     "agentRegistrationId": ENVIRONMENT["A365_REGISTRATION_ID"],
                     "agentBlueprintClientSecret": "private-test-secret"}
        for flags in ["", "-Apply", "-RegistrationOnly -Apply"]:
            with self.subTest(flags=flags):
                result = self.run_helper(flags, generated)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("--authmode s2s --aiteammate false", result.stdout)
                self.assertEqual("--dry-run" in result.stdout, not bool(flags))
                self.assertNotIn("private-test-secret", result.stdout + result.stderr)
                if "RegistrationOnly" in flags:
                    self.assertIn("--agent-registration-only", result.stdout)

    def test_apply_requires_registration_metadata(self) -> None:
        result = self.run_helper("-Apply", {"agentBlueprintId": ENVIRONMENT["A365_BLUEPRINT_ID"],
                                           "agenticAppId": ENVIRONMENT["A365_AGENT_ID"]})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("agentRegistrationId", result.stderr)


class ApplicationTests(unittest.TestCase):
    def test_success_and_runner_failure_flush_and_shutdown(self) -> None:
        for error in [None, RuntimeError("offline model failure")]:
            with self.subTest(error=error):
                provider = Mock()
                with (
                    patch.dict(os.environ, ENVIRONMENT, clear=True),
                    patch.object(app, "configure_agent365") as initialize,
                    patch.object(app, "build_agent", return_value="test-agent"),
                    patch.object(app.Runner, "run_sync", side_effect=error,
                                 return_value=SimpleNamespace(final_output="checklist")) as run,
                    patch.object(app.trace, "get_tracer_provider", return_value=provider),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    if error:
                        with self.assertRaisesRegex(RuntimeError, "offline model failure"):
                            app.main()
                    else:
                        app.main()
                        self.assertEqual(output.getvalue(), "checklist\n")
                initialize.assert_called_once()
                run.assert_called_once_with(
                    "test-agent",
                    "Give me a five-item security review checklist "
                    "for a Python AI agent that calls external tools.",
                )
                provider.force_flush.assert_called_once()
                provider.shutdown.assert_called_once()

    def test_shutdown_even_when_flush_fails(self) -> None:
        provider = Mock()
        provider.force_flush.side_effect = RuntimeError("flush failed")
        with (
            patch.dict(os.environ, ENVIRONMENT, clear=True),
            patch.object(app, "configure_agent365"),
            patch.object(app, "build_agent", return_value="test-agent"),
            patch.object(app.Runner, "run_sync", return_value=SimpleNamespace(final_output="checklist")),
            patch.object(app.trace, "get_tracer_provider", return_value=provider),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with self.assertRaisesRegex(RuntimeError, "flush failed"):
                app.main()
        provider.shutdown.assert_called_once()

    def test_agent_id_is_required_without_client_id_fallback(self) -> None:
        environment = {**ENVIRONMENT, "AGENT365OBSERVABILITY__CLIENTID": "blueprint"}
        del environment["A365_AGENT_ID"]
        with patch.dict(os.environ, environment, clear=True), patch.object(a365_bootstrap, "_configuration", return_value={}):
            with patch.object(app, "configure_agent365") as initialize:
                with self.assertRaises(ValueError):
                    app.main()
        initialize.assert_not_called()


class DistroIntegrationTests(unittest.TestCase):
    def test_real_auto_instrumentation_and_identity(self) -> None:
        code = """
from agents import agent_span, generation_span, trace as agent_trace
from microsoft.opentelemetry import use_microsoft_opentelemetry
from microsoft.opentelemetry.a365.core import BaggageBuilder
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

exporter = InMemorySpanExporter()
use_microsoft_opentelemetry(
    enable_a365=True,
    a365_enable_observability_exporter=False,
    span_processors=[SimpleSpanProcessor(exporter)],
    disable_logging=True,
    disable_metrics=True,
)
with BaggageBuilder().tenant_id('test-tenant').agent_id('test-agent').agent_blueprint_id('test-blueprint').build():
    with agent_trace('offline-check'):
        with agent_span('Security Architecture Assistant'):
            with generation_span(model='gpt-4.1-mini', usage={'input_tokens': 5, 'output_tokens': 7}):
                pass
provider = trace.get_tracer_provider()
provider.force_flush()
spans = exporter.get_finished_spans()
operations = {span.attributes.get('gen_ai.operation.name'): span for span in spans}
for operation in ['invoke_agent', 'chat']:
    assert operation in operations, list(operations)
    assert operations[operation].attributes['microsoft.tenant.id'] == 'test-tenant'
    assert operations[operation].attributes['gen_ai.agent.id'] == 'test-agent'
    assert operations[operation].attributes['microsoft.a365.agent.blueprint.id'] == 'test-blueprint'
assert operations['chat'].parent.span_id == operations['invoke_agent'].context.span_id
provider.shutdown()
print('PASS: supported auto-instrumentation, identity propagation, and span nesting')
"""
        environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("OTEL_", "A365_", "AGENT365", "APPLICATIONINSIGHTS"))
            and key != "OPENAI_API_KEY"
        }
        environment.update({
            "ENABLE_OBSERVABILITY": "true",
            "ENABLE_A365_OBSERVABILITY_EXPORTER": "false",
            "APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL": "true",
        })
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).parent,
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: supported auto-instrumentation", result.stdout)


if __name__ == "__main__":
    unittest.main()