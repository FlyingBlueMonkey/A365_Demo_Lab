import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import a365_bootstrap
import app


ENVIRONMENT = {
    "AZURE_TENANT_ID": "test-tenant",
    "AZURE_CLIENT_ID": "test-agent",
    "AZURE_CLIENT_SECRET": "not-a-real-secret",
    "A365_AGENT_ID": "test-agent",
}


class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, ENVIRONMENT, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        a365_bootstrap._credential.cache_clear()
        self.addCleanup(a365_bootstrap._credential.cache_clear)

    def test_supported_initializer_configuration(self) -> None:
        with patch.object(a365_bootstrap, "use_microsoft_opentelemetry") as initialize:
            a365_bootstrap.configure_agent365()
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

    def test_token_scope_and_credential_reuse(self) -> None:
        with patch.object(a365_bootstrap, "ClientSecretCredential") as credential:
            credential.return_value.get_token.return_value = SimpleNamespace(token="test-token")
            for _ in range(2):
                self.assertEqual(
                    a365_bootstrap.resolve_observability_token("test-agent", "test-tenant"),
                    "Bearer test-token",
                )
        credential.assert_called_once_with(
            tenant_id="test-tenant", client_id="test-agent", client_secret="not-a-real-secret"
        )
        credential.return_value.get_token.assert_called_with(
            "api://9b975845-388f-4429-889e-eab1ef63949c/.default"
        )

    def test_mismatched_tenant_or_agent_rejected_before_authentication(self) -> None:
        with patch.object(a365_bootstrap, "ClientSecretCredential") as credential:
            for agent_id, tenant_id in [
                ("test-agent", "other-tenant"),
                ("other-agent", "test-tenant"),
            ]:
                with self.subTest(agent=agent_id, tenant=tenant_id):
                    with self.assertRaises(ValueError):
                        a365_bootstrap.resolve_observability_token(agent_id, tenant_id)
        credential.assert_not_called()

    def test_blueprint_credentials_cannot_impersonate_agent_instance(self) -> None:
        with patch.dict(os.environ, {"AZURE_CLIENT_ID": "different-blueprint"}):
            with patch.object(a365_bootstrap, "ClientSecretCredential") as credential:
                with self.assertRaisesRegex(ValueError, "match the client ID"):
                    a365_bootstrap.resolve_observability_token("test-agent", "test-tenant")
        credential.assert_not_called()


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
        with patch.dict(os.environ, environment, clear=True):
            with patch.object(app, "configure_agent365") as initialize:
                with self.assertRaises(KeyError):
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
with BaggageBuilder().tenant_id('test-tenant').agent_id('test-agent').build():
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