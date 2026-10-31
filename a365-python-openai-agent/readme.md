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

This implementation uses a standard Entra service principal (custom-engine
agent authentication), not a blueprint-to-agent-instance FMI token exchange.
The telemetry agent ID must match that service principal's application client ID.
The principal needs the **application** `Agent365.Observability.OtelWrite` role
on the observability resource with administrator consent. Follow
[S2S authentication and permissions](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/microsoft-opentelemetry).

The standalone baselines are [python-openai-agent](../python-openai-agent/readme.md)
and [python-ollama-agent](../python-ollama-agent/readme.md). The Ollama sample
uses local inference and does not include this project's A365 integration.

## Requirements

- Python 3.10 or newer (Python 3.13 is used in the current development setup)
- An OpenAI API key
- An Agent 365-enabled tenant with the required observability license assigned
- An Azure service principal with the observability application role and admin consent
- A telemetry agent ID equal to that service principal's application client ID
- PowerShell on Windows, or an equivalent shell on another platform

## A365 CLI Setup

Follow the numbered [A365 CLI setup steps in the lab README](../readme.md#enable-and-set-up-the-a365-cli)
to install prerequisites and the CLI, configure PATH, sign in, validate the
tenant, and optionally provision resources. These commands are onboarding
operations, not commands that must run before every Python invocation.

Review [a365.config.json.example](a365.config.json.example) before updating your
local [a365.config.json](a365.config.json). CLI authentication and runtime
service-principal authentication are separate. Do not assume CLI provisioning
automatically authorizes an arbitrary service principal to export telemetry.

For an Agent 365-registered instance, use its actual agent ID and the supported
[agent-instance S2S token flow](https://learn.microsoft.com/en-us/microsoft-agent-365/observability-authentication-setup#agent-365-enabled-using-s2s).
That requires replacing this sample's direct service-principal token resolver;
setting a blueprint's client ID/secret with a different agent ID is rejected.
The script does not itself provision or register identities.

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
$env:AZURE_CLIENT_ID = "your-service-principal-client-id"
$env:AZURE_CLIENT_SECRET = "your-service-principal-client-secret"
$env:A365_AGENT_ID = $env:AZURE_CLIENT_ID
$env:ENABLE_A365_OBSERVABILITY_EXPORTER = "true"
```

To persist configuration in a local `.env` file, create `a365-python-openai-agent/.env`
with the following contents instead. Keep this file private and do not commit
it to source control:

```dotenv
OPENAI_API_KEY=your-api-key
OPENAI_MODEL=gpt-4.1-mini
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-service-principal-client-id
AZURE_CLIENT_SECRET=your-service-principal-client-secret
A365_AGENT_ID=your-service-principal-client-id
ENABLE_A365_OBSERVABILITY_EXPORTER=true
```

`OPENAI_MODEL` is optional and defaults to `gpt-4.1-mini`.
`A365_OBSERVABILITY_SCOPE` is optional and defaults to
`api://9b975845-388f-4429-889e-eab1ef63949c/.default`.
The Azure variables are required because [app.py](app.py) configures Agent 365
before running the agent. The client secret must be kept private.

CLI-generated `AGENT365OBSERVABILITY__TENANTID`,
`AGENT365OBSERVABILITY__CLIENTID`, and `AGENT365OBSERVABILITY__CLIENTSECRET`
can substitute for the corresponding Azure variables. The agent ID can also
come from `AGENT365OBSERVABILITY__AGENTID` or `AGENT_ID`; the code falls back to
neither a blueprint nor a client ID if the agent ID is absent. An explicit
agent ID is required and must match the token-acquiring application's client ID.
Do not copy generated blueprint credentials into this sample as if they were
agent-instance credentials. This script loads
environment variables and `.env`; it does not directly read the JSON CLI config.

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
Missing required identity values fail startup; authentication and export failures
can occur in the background after model inference. A printed checklist does not
prove telemetry was delivered. Export failure is best-effort, not a policy gate.

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

The suite checks initialization, S2S identity matching, credential reuse,
success/failure cleanup, and real distro auto-instrumentation with in-memory
spans. It does not call OpenAI, acquire live Azure tokens, or provision resources.

### Telemetry Privacy and Delivery

Invocation-input suppression is not a blanket content filter. Review inference
input/output, model instructions, exception data, and OpenAI SDK tracing against
your organization's policy before using sensitive data. Offline buffering is
disabled to avoid persisting unencrypted payloads; delivery is best-effort.
No DLP, model/tool authorization, or messaging hosting is implemented here.

Confirm export and visibility in the target environment. Check the matching
identity, app role/admin consent, tenant licensing, root invocation span, and
ingestion delay. Neither HTTP 200 nor CLI registration alone proves that activity
appears in the intended admin/security surfaces.

## Project files

- [app.py](app.py) builds the agent, sets telemetry baggage, and runs the example request.
- [requirements.txt](requirements.txt) lists the OpenAI Agents SDK, Microsoft OpenTelemetry, Azure
	Identity, and the environment-variable loader.
- [a365_bootstrap.py](a365_bootstrap.py) configures Agent 365 observability and resolves Azure
	service-principal tokens.
- [a365.config.json](a365.config.json) contains the Agent 365 tenant, client application, and
	agent blueprint metadata used by the demo configuration.
- [test_app.py](test_app.py) contains offline supported-SDK regression tests.

## Extending the demo

The next natural extension is to define one or more typed tools and register
them with the agent. Tool implementations should validate their inputs,
restrict access to the minimum required resources, avoid returning secrets,
and make side effects explicit before they are enabled in production. Keep
observability token resolution separate from tool execution and validate the
tenant supplied by the exporter as shown in `a365_bootstrap.py`.
