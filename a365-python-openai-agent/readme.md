# A365 Python OpenAI Agent

This project is a small Python demonstration of the OpenAI Agents SDK integrated
with Microsoft Agent 365 observability through the supported
`microsoft-opentelemetry` distribution. It creates a security architecture
assistant, sends it a fixed request for a five-item security review checklist,
and prints the assistant's response to the terminal.

The assistant is configured to provide concise, technically precise guidance,
distinguish verified facts from suggestions, and avoid revealing credentials,
tokens, secrets, or hidden configuration. The current example does not register
or call external tools; it demonstrates the agent and observability setup.

[a365_bootstrap.py](a365_bootstrap.py) initializes Microsoft OpenTelemetry once,
using the `prod` cluster and S2S exporter. The distro automatically instruments
the OpenAI Agents SDK; no separate instrumentor is installed or invoked.
The sample suppresses invocation input, disables log/metric collection and
offline payload storage, and flushes/shuts down tracing at CLI exit.

This implementation uses a **registered Agent 365 agent instance**, its
**Agent Blueprint**, and the supported two-step FMI S2S exchange. The agent
instance client ID must **differ** from the blueprint client ID. The final
token represents the instance, not the blueprint or CLI login application.

Catalog discovery requires explicit platform registration, not just an OpenAI
`Agent` object or telemetry. [register_agent.ps1](register_agent.ps1) performs
that registration separately; runtime does not provision tenant resources.

The standalone baselines are [python-openai-agent](../python-openai-agent/readme.md)
and [python-ollama-agent](../python-ollama-agent/readme.md). The Ollama sample
uses local inference and does not include this project's A365 integration.

## Requirements

- Python 3.10 or newer (Python 3.13 is used in the current development setup)
- An OpenAI API key
- An Agent 365-enabled tenant with the required observability license assigned
- An Agent Blueprint and distinct agent instance registered with Agent 365
- A blueprint client-secret value for the development FMI exchange
- The platform registration ID and access to verify catalog discovery
- PowerShell on Windows, or an equivalent shell on another platform

## A365 CLI Setup

Follow the numbered [A365 CLI setup steps in the lab README](../readme.md#enable-and-set-up-the-a365-cli)
to install prerequisites and the CLI, configure PATH, sign in, validate the
tenant, and optionally provision resources. These commands are onboarding
operations, not commands that must run before every Python invocation.

Review [a365.config.json.example](a365.config.json.example) before updating your
local [a365.config.json](a365.config.json). CLI authentication and runtime
blueprint authentication are separate. `clientAppId` is the interactive CLI
login application's client ID, not the blueprint or runtime agent ID.

### Provision and Register

From this directory, create a private config only if one does not already exist:

```powershell
if (-not (Test-Path a365.config.json)) {
	 Copy-Item a365.config.json.example a365.config.json
}
```

Review your tenant ID and CLI authentication app ID. Keep `aiTeammate=false`,
`useBlueprint=true`, and `authMode=s2s`. Update the CLI to a version supporting
`--authmode` and `--agent-registration-only`, sign in to the intended tenant,
and preview:

```powershell
a365 setup requirements
.\register_agent.ps1
```

After administrator approval, explicitly apply:

```powershell
.\register_agent.ps1 -Apply
```

The helper runs `a365 setup all --authmode s2s --aiteammate false`. The CLI
creates/reuses the blueprint, creates its agent instance, and registers it with
Agent 365. Complete any administrator consent/S2S-grant handoff. The helper
checks generated `agentBlueprintId`, `agenticAppId`, and `agentRegistrationId`,
and prints only those identifiers, not secrets. Blueprint-only setup is insufficient.

If only registration failed, preview and retry it:

```powershell
.\register_agent.ps1 -RegistrationOnly
.\register_agent.ps1 -RegistrationOnly -Apply
```

### Verify Discovery

1. Confirm successful **agent registration** in CLI output, not just Entra
	blueprint creation. Current setup fails if registration cannot be verified.
2. Find the agent in the target tenant's Agent 365/Microsoft 365 admin catalog
	at `https://admin.cloud.microsoft/#/agents/all`. Confirm its display name,
	Agent ID, and blueprint relationship. Access, licensing, and propagation delay
	can affect visibility. An Entra identity alone is not platform registration.
3. Run `python app.py --check-config` and compare its nonsecret values with
	the registration. `live_registration_verified=false` is deliberate: this
	command validates local metadata only; it does not query the catalog.
4. Enable export and confirm activity is attributed to that registered instance.
	Catalog presence and telemetry delivery are separate gates.

Live registration/discovery in your tenant has not been verified by this repository's
offline tests. This console app has no messaging endpoint: discovery does not
make it callable from Teams. Hosting and messaging endpoint registration are separate.

## Setup

From this directory, create and activate a virtual environment. Use the same
Python installation selected in VS Code; do not reuse an environment created
with a removed Python installation:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the dependencies. The distro is pinned to the verified version `1.5.0`:

```powershell
python -m pip install -r requirements.txt
```

When migrating an existing environment, remove the old standalone A365 packages
first to avoid duplicate instrumentation. Alternatively, create a fresh virtual
environment:

```powershell
python -m pip uninstall -y microsoft-agents-a365-observability-core microsoft-agents-a365-runtime microsoft-agents-a365-observability-extensions-openai
python -m pip install -r requirements.txt
python -m pip check
```

Set the required values in the current PowerShell session:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
$env:AZURE_TENANT_ID = "your-tenant-id"
$env:A365_BLUEPRINT_ID = "your-blueprint-client-id"
$env:A365_AGENT_ID = "your-agent-instance-client-id"
$env:A365_REGISTRATION_ID = "your-agent365-registration-id"
$env:A365_BLUEPRINT_CLIENT_SECRET = "your-blueprint-client-secret-value"
$env:ENABLE_A365_OBSERVABILITY_EXPORTER = "true"
```

To persist configuration in a local `.env` file, create `a365-python-openai-agent/.env`
with the following contents instead. Keep this file private and do not commit
it to source control:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4.1-mini
AZURE_TENANT_ID=your-tenant-id
A365_BLUEPRINT_ID=your-blueprint-client-id
A365_AGENT_ID=your-agent-instance-client-id
A365_REGISTRATION_ID=your-agent365-registration-id
A365_BLUEPRINT_CLIENT_SECRET=your-blueprint-client-secret-value
ENABLE_A365_OBSERVABILITY_EXPORTER=true
```

`OPENAI_MODEL` is optional and defaults to `gpt-4.1-mini`.
`A365_OBSERVABILITY_SCOPE` is no longer used; the FMI/observability scopes are
fixed to the documented token flow. Keep the blueprint secret private.

### Identity Configuration

Environment / `.env` values take precedence over local CLI JSON metadata:

| Runtime value | Preferred variable | CLI fallback |
| --- | --- | --- |
| Tenant | `AZURE_TENANT_ID` | config: `tenantId` |
| Blueprint client ID | `A365_BLUEPRINT_ID` | generated config: `agentBlueprintId` |
| Agent instance client ID | `A365_AGENT_ID` | generated config: `agenticAppId` |
| Platform registration ID | `A365_REGISTRATION_ID` | generated config: `agentRegistrationId` |
| Blueprint secret value | `A365_BLUEPRINT_CLIENT_SECRET` | No JSON secret loading/decryption |

`A365_CONFIG_DIR` can select another directory containing `a365.config.json`
and `a365.generated.config.json`; by default this project's directory is used.
All identifiers must be nonzero UUIDs. Blueprint and agent IDs must differ.
A local registration ID is required even in console mode, but is not proof of
live registration. The loader never uses `clientAppId` as a runtime identity.

Compatibility aliases remain: `AGENT365OBSERVABILITY__TENANTID` for tenant;
`AGENT365OBSERVABILITY__BLUEPRINTID`, `AZURE_CLIENT_ID`, or
`AGENT365OBSERVABILITY__CLIENTID` for **blueprint** ID;
`AGENT365OBSERVABILITY__AGENTID` or `AGENT_ID` for instance ID;
`AZURE_CLIENT_SECRET` or `AGENT365OBSERVABILITY__CLIENTSECRET` for **blueprint**
secret. Clear old standard service-principal overrides when migrating. Never
substitute a CLI app ID, blueprint ID, secret ID, or Object ID for Agent ID.

### Fix Equal Blueprint and Agent IDs

If the CLI-generated IDs are distinct but startup reports equal IDs, stale
environment or `.env` aliases are overriding the generated metadata. From this
project directory, use the generated values explicitly for the current session:

```powershell
$ConfigDirectory = if ($env:A365_CONFIG_DIR) { $env:A365_CONFIG_DIR } else { (Get-Location).Path }
$Generated = Get-Content (Join-Path $ConfigDirectory "a365.generated.config.json") -Raw | ConvertFrom-Json
if ($Generated.agentBlueprintId -eq $Generated.agenticAppId) {
	throw "Generated IDs are not distinct; verify the actual agent registration before continuing."
}
$env:A365_BLUEPRINT_ID = $Generated.agentBlueprintId
$env:A365_AGENT_ID = $Generated.agenticAppId
$env:A365_REGISTRATION_ID = $Generated.agentRegistrationId
.\.venv\Scripts\python.exe app.py --check-config
```

For a persistent fix, put those three actual values in the private `.env` using
the preferred variable names above. Remove or correct conflicting older
`AZURE_CLIENT_ID` and `AGENT365OBSERVABILITY__AGENTID` assignments. Current-session
variables take precedence over `.env`, so update them too or use a fresh terminal.
Do not invent a new UUID or change Agent ID to match the blueprint. Existing valid
registration metadata can be reused; missing or genuinely equal generated IDs
require the registration workflow instead.

Live export still needs the correct **blueprint** secret value in
`A365_BLUEPRINT_CLIENT_SECRET`. The ID correction does not validate that credential
or prove live discovery. `--check-config` makes no token or catalog requests.

### Agent-Instance Authentication

Two form-encoded HTTPS requests use the configured tenant's Entra endpoint,
with redirects disabled and a bounded timeout:

1. Blueprint `client_credentials`, blueprint secret, scope
	`api://AzureADTokenExchange/.default`, and `fmi_path=<agent-instance-client-id>`
	produce the intermediate assertion.
2. Agent-instance `client_credentials`, the assertion as `client_assertion`,
	and `api://9b975845-388f-4429-889e-eab1ef63949c/.default` produce the final token.

The resolver checks the final token's tenant, client identity, audience, app-only
claims, and expiry. Delegated tokens with `scp`, blueprint tokens, wrong audiences,
and near-expiry tokens are rejected. These are routing/type guards on an Entra
HTTPS response, not standalone JWT signature verification; the service verifies
the signature. There is no user/OBO fallback. A lock-protected cache refreshes
before expiry and is prewarmed before live model inference/spans. Error text does
not include token responses.

The resolver returns the raw access token. The supported exporter adds the
`Authorization: Bearer` prefix; returning a prefixed token would duplicate it.

A registered instance on the supported S2S route does not need the observability
app role or delegated observability consent solely to export; other setup grants
and tenant policy still apply. See the
[official authentication flow](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/observability-authentication-setup#agent-365-enabled-using-s2s).
This development implementation uses a blueprint secret. Use the documented
managed-identity/FMI approach for secretless deployment.

## Run

With the virtual environment activated:

```powershell
python app.py
```

Or run directly through the virtual environment without activating it:

```powershell
.\.venv\Scripts\python.exe app.py
```

The program prints a five-item security review checklist, generated by the
configured model. By default, it also attempts S2S export to Agent 365.
Missing/inconsistent registration metadata fails startup. Initial live token
acquisition also fails before model inference if authentication is invalid.
Later refresh/export failures can still occur in the background. A printed
checklist does not prove telemetry delivery. Export is best-effort, not a policy gate.

### Console-Only Validation

Disable Agent 365 service export while keeping instrumentation active:

```powershell
$env:ENABLE_A365_OBSERVABILITY_EXPORTER = "false"
python app.py
```

With no other exporter configured, the distro exports spans to the console.
The model call still uses OpenAI and needs its API key; console-only validation
does not mean the model is offline. Identity values are still required, but the
sample's Azure token resolver is not called for console export. Other explicitly
configured OTLP exporters can still transmit data; use a clean environment when
testing console-only behavior.

Run the offline regression suite from the repository root:

```powershell
.\a365-python-openai-agent\.venv\Scripts\python.exe -m unittest discover -s a365-python-openai-agent -v
```

The suite checks identity loading, both FMI requests, token caching/refresh and
rejection cases, safe errors, cleanup, and real distro blueprint/agent metadata
and nesting. It does not call OpenAI, acquire live Azure tokens, or provision resources.

### Telemetry Privacy and Delivery

Invocation-input suppression is not a blanket content filter. Review inference
input/output, model instructions, exception data, and OpenAI SDK tracing against
your organization's policy before using sensitive data. Offline buffering is
disabled to avoid persisting unencrypted payloads; delivery is best-effort.
No DLP, model/tool authorization, or messaging hosting is implemented here.

Confirm export and visibility in the target environment. Check the matching
registered instance and blueprint relationship, tenant licensing, root invocation span, and
ingestion delay. Neither HTTP 200 nor CLI registration alone proves that activity
appears in the intended admin/security surfaces.

## Project files

- [app.py](app.py) builds the agent, sets telemetry baggage, and runs the example request.
- [requirements.txt](requirements.txt) lists the OpenAI Agents SDK, Microsoft OpenTelemetry,
	HTTP client, and environment-variable loader.
- [a365_bootstrap.py](a365_bootstrap.py) configures Agent 365 observability and resolves Azure
	agent-instance tokens through blueprint FMI.
- [a365.config.json](a365.config.json) contains the Agent 365 tenant, client application, and
	agent blueprint metadata used by the demo configuration.
- [test_app.py](test_app.py) contains offline supported-SDK regression tests.
- [register_agent.ps1](register_agent.ps1) previews or applies blueprint/instance registration using the A365 CLI.

## Extending the demo

The next natural extension is to define one or more typed tools and register
them with the agent. Tool implementations should validate their inputs,
restrict access to the minimum required resources, avoid returning secrets,
and make side effects explicit before they are enabled in production. Keep
observability token resolution separate from tool execution and validate the
tenant supplied by the exporter as shown in `a365_bootstrap.py`.
