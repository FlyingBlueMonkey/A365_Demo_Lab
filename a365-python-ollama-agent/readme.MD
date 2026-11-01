# Add Agent 365 to the Python Ollama Agent

This folder is documentation only. It contains no runnable agent or dependencies.
The steps below describe future changes to the existing
[python-ollama-agent](../python-ollama-agent/readme.md); they have not been applied.

The goal is to keep Ollama inference while adding Microsoft Agent 365 identity,
registration, and observability. Keep the current model, system instructions,
five-item security checklist request, and terminal output unchanged.

## Choose the Integration Path

Use the supported
[Microsoft OpenTelemetry Distro](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/microsoft-opentelemetry).
The [OpenAI-integrated sample](../a365-python-openai-agent/readme.md) now uses
`microsoft-opentelemetry==1.5.0`. This guide uses only that supported integration
path; do not install the standalone A365 observability SDK packages.

Reuse the supported initialization and context APIs, but choose authentication
that matches the exporting identity and replace OpenAI auto-instrumentation
with manual Ollama agent/inference scopes.

## 1. Establish the Baseline

From the repository root, run the existing project before changing it:

```powershell
Set-Location python-ollama-agent
.\.venv\Scripts\python.exe app.py
```

If its environment or model is not ready, follow its
[setup instructions](../python-ollama-agent/readme.md#setup) first.
Keep `OLLAMA_MODEL` and `OLLAMA_HOST`. No OpenAI API key is needed.

## 2. Prepare the Tenant and CLI

Follow the numbered [A365 CLI setup guide](../readme.md#enable-and-set-up-the-a365-cli)
to install .NET and Azure CLI, install or update `a365`, configure PATH, and
sign in to the intended tenant and subscription.

Confirm Agent 365 tenant enablement and current observability licensing with
your administrator. At least one eligible user must have the required license
assigned; having the SKU available in the tenant is not sufficient.
Arrange the roles and administrator consent required by the selected workflow.

Check prerequisites before provisioning anything:

```powershell
a365 setup requirements
```

CLI installation alone does not enable the tenant, register the agent, or
authorize telemetry export. See the
[current prerequisites](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/get-started#prerequisites).

## 3. Register an Ollama Agent Identity

Use a distinct agent name so the Ollama sample is not attributed to the OpenAI
sample. From the Ollama project directory, preview config-free onboarding:

```powershell
a365 setup all --agent-name "Security Architecture Assistant Ollama" --authmode s2s --dry-run
```

After reviewing the planned changes with your administrator, provision it:

```powershell
a365 setup all --agent-name "Security Architecture Assistant Ollama" --authmode s2s
```

These commands change tenant resources. Complete the administrator handoff
reported by the CLI, and record the tenant, blueprint, and registered agent
instance identifiers. Config-free setup assumes external hosting; it does not
turn this terminal script into a Teams bot or install Python instrumentation.

Keep generated configuration private, especially if it includes credentials.
Use the actual registered agent instance client ID for telemetry attribution,
not the blueprint client ID or a service principal Object ID. Registration and
model-provider selection are independent: the model can remain local Ollama.

## 4. Add the Current Observability Components

Follow the [Microsoft OpenTelemetry setup guide](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/microsoft-opentelemetry)
and [Python A365 usage guide](https://github.com/microsoft/opentelemetry-distro-python/blob/main/A365_DOCUMENTATION.md).
Add `microsoft-opentelemetry==1.5.0` to the Ollama project's existing
[requirements.txt](../python-ollama-agent/requirements.txt), keeping `ollama`
and `python-dotenv`. Add `httpx` when adapting the lab's blueprint FMI resolver,
then reinstall through its virtual environment.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip check
```

For an AI-guided implementation, the official
[Agent 365 Skills workflow](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/get-started)
provides setup and observability instrumentation. Install the skills using
GitHub CLI, then restart your coding assistant:

```powershell
gh skill add microsoft/agent365-skills
```

Open the Ollama project and request: "Add Agent 365 observability to this native
Ollama Python client using Microsoft OpenTelemetry. Keep local inference and
the existing prompt unchanged." Review the generated changes before running.

Whether implementing manually or with skills, make these changes:

1. Add an observability initialization module in the Ollama project. Load `.env`
   before initialization and configure the telemetry provider/exporter once,
   before starting the agent run. Use a distinct Ollama service name.
   Initialize with `use_microsoft_opentelemetry(enable_a365=True, ...)` from
   `microsoft.opentelemetry` and an OpenTelemetry `Resource` for service metadata.
2. Configure authentication for the chosen exporter route using the current
   authentication guide. Keep telemetry credentials separate from Ollama client
   configuration and from interactive CLI authentication.
3. Add the registered tenant, agent instance, and blueprint metadata using the
   distro's supported context and span attributes. Preserve that context through
   the entire run. Do not invent agent-user or human-caller identities for this
   terminal script.
4. Modify [app.py](../python-ollama-agent/app.py) to create a root agent-invocation
   span and a nested inference span around the existing `client.chat(...)` call.
   Record operation `invoke_agent` for the root and `chat` for inference, using
   the supported semantic conventions, provider `ollama`, and the selected model.
   Import `BaggageBuilder`, `AgentDetails`, `Request`, `InvokeAgentScope`,
   `InvokeAgentScopeDetails`, `InferenceScope`, `InferenceCallDetails`, and
   `InferenceOperationType` from `microsoft.opentelemetry.a365.core`.
   Use `InvokeAgentScope.start(...)` around the run and nested
   `InferenceScope.start(...)` around model inference. For manual scopes, set
   `ENABLE_OBSERVABILITY=true` before initializing telemetry.
5. Record actual input/output token counts when present in Ollama's
   `prompt_eval_count` and `eval_count` response fields. Leave missing values
   unset rather than inventing usage numbers. Capture failures and latency
   without swallowing model or connection errors.
6. Preserve `print(result.message.content)`. Close spans and flush/shut down the
   telemetry provider at process exit so this short-lived script does not lose
   its final batch. Use the selected distro's documented lifecycle API.

Native Ollama calls do not emit OpenAI Agents SDK trace events. OpenAI Agents
auto-instrumentation cannot trace this client. Generic HTTP
instrumentation alone is not a substitute for agent and inference spans.

## 5. Configure Authentication and Data Handling

For a registered agent using S2S telemetry, follow
[Agent 365 observability authentication](https://learn.microsoft.com/en-us/microsoft-agent-365/observability-authentication-setup#agent-365-enabled-using-s2s).
The registered agent-instance identity and exporting token must match. Where
the documented flow requires a Federated Managed Identity exchange, a blueprint
client secret by itself is not the final agent-instance observability token.

The supported distro retains `ENABLE_A365_OBSERVABILITY_EXPORTER` as its HTTP
export switch. With `enable_a365=True`, set it to `false` for local console
validation and `true` for service export. Use `a365_use_s2s_endpoint=True` when
using app-only authentication. The lab bootstrap also reads `AZURE_*` variables;
these configure its custom resolver, not the distro's general authentication.

The OpenAI bootstrap now implements the supported blueprint-to-agent FMI flow.
Reuse it with the Ollama instance's own tenant, blueprint client ID, distinct
agent client ID, and registration ID. Supply a blueprint secret for the first
exchange; the final token must represent the instance. Use `AZURE_TENANT_ID`,
`A365_BLUEPRINT_ID`, `A365_AGENT_ID`, `A365_REGISTRATION_ID`, and
`A365_BLUEPRINT_CLIENT_SECRET`, or the documented nonsecret CLI JSON fallbacks.
Use `load_identity()` and attach both Agent ID and blueprint ID to baggage.
Verify CLI registration and catalog visibility independently of telemetry.
Keep secrets out of source control and logs; use managed/workload identity where
supported for deployment rather than committing client secrets.

Start with metadata-only telemetry. Do not record raw prompts, responses,
reasoning, tool arguments, or secrets unless your organization's data-handling
policy explicitly allows it. Suppressing invocation input does not automatically
suppress inference input, output, exception messages, or console logs.

Local model inference does not mean all data stays local after adding A365:
telemetry is sent to Microsoft services. Verify what is exported and the target
tenant's retention, access, and audit policies.

## Supported Components to Reuse

| Existing OpenAI component | Ollama adaptation |
| --- | --- |
| `microsoft-opentelemetry==1.5.0` | Use the same supported distro; keep `ollama` and omit OpenAI dependencies. |
| [a365_bootstrap.py](../a365-python-openai-agent/a365_bootstrap.py) | Adapt exporter setup and service naming, but review authentication for the chosen SDK version. |
| `BaggageBuilder` | Set the actual tenant and registered agent ID before starting spans. Baggage alone does not create spans. |
| Distro OpenAI Agents auto-instrumentation | Use explicit `InvokeAgentScope` and nested `InferenceScope` instead. |
| `Runner.run_sync(...)` | Keep Ollama's native `client.chat(...)` inside the inference scope. |
| Inference details | Use `InferenceOperationType.CHAT`, the selected model, and provider `ollama`. |

Use the supported distro's API signatures and only one telemetry provider.
Do not leave old instrumentor registrations active alongside the distro.

## 6. Validate the Updated Agent

1. With service export disabled using the chosen library's documented setting,
   inspect local console spans: a single root invocation must contain a child
   inference span, correct identity/model metadata, and no disallowed content.
2. Mock the Ollama response to verify prompt preservation, printed output,
   token-count mapping, and correct span nesting. Test connection failure and
   model-not-found cases, including span closure and provider flush.
3. Enable service export and run the unchanged checklist request against the
   local model. Verify the exported identity matches the registered instance.
4. Confirm activity in the applicable Agent 365 admin/security surfaces. HTTP
   200 alone does not establish visibility: check licensing, root-span semantics,
   identity attributes, ingestion delay, and permissions.
5. Repeat with a failed Ollama call to confirm errors are observable without
   leaking credentials or sensitive payloads.

This guide has not performed live tenant registration or verified an implemented
Ollama/A365 exporter. Those checks are required when applying these steps.

## Optional Components

Observability is not tool authorization, DLP enforcement, or a hosting layer.
Add these separately only when the agent's workflow needs them:

- **Agent 365 tools / Work IQ:** use a supported tooling client, approved scopes,
  and administrator consent. Validate inputs and implement the actual tool-call
  loop; a tool-related prompt does not execute tools.
- **Tool spans:** instrument real tool executions as children of the agent span;
  do not fabricate tool activity for the current checklist-only example.
- **Teams or other messaging:** add Microsoft 365 Agents hosting, incoming-token
  validation, a reachable HTTPS messaging endpoint, and channel registration.
- **Purview DLP:** implement supported content checks and tenant policy setup;
  telemetry alone does not block unsafe content.

Keep these follow-up changes separate from the initial identity and observability
update so the baseline remains easy to verify.