# A365 Demo Lab

This repository demonstrates standalone security architecture assistants using
OpenAI or local Ollama inference, plus an Agent 365-integrated OpenAI agent with
observability and Azure service-principal authentication.

The integrated implementation uses the supported `microsoft-opentelemetry`
distribution, not the standalone A365 observability packages.

The lab has two stages, with two provider choices for the standalone baseline:

1. **Standalone Agent**: choose the OpenAI Agents SDK sample or the Ollama Python client sample, both with no A365 dependency.
2. **A365-Integrated Agent**: the same agent experience connected to Microsoft
    Agent 365 observability for operational telemetry and enterprise integration.

The first stage provides a simple baseline. The second stage shows how an
existing agent can gain observability and identity integration without changing
its core purpose or conversation behavior.

## Project Structure

```text
A365_Demo_Lab/
├── python-openai-agent/
│   ├── app.py
│   ├── requirements.txt
│   └── readme.md
├── python-ollama-agent/
│   ├── app.py
│   ├── requirements.txt
│   └── readme.md
├── a365-python-openai-agent/
│   ├── app.py
│   ├── a365_bootstrap.py
│   ├── a365.config.json
│   ├── requirements.txt
│   ├── test_app.py
│   └── readme.md
└── a365-python-ollama-agent/
    └── readme.MD
```

The standalone implementations are in
[python-openai-agent](python-openai-agent/readme.md) and
[python-ollama-agent](python-ollama-agent/readme.md). The integrated implementation
is in [a365-python-openai-agent](a365-python-openai-agent/readme.md) and includes
Agent 365 configuration, observability bootstrap code, and Azure identity
dependencies. The Ollama sample does not include A365 telemetry or tool execution.
The documentation-only [Ollama integration guide](a365-python-ollama-agent/readme.MD)
describes adding the same supported distro to the native Ollama client.

## Stage 1: Generic OpenAI Agent

The stage-one sample is a minimal Python application using the OpenAI Agents
SDK. It creates a `Security Architecture Assistant`, sends a fixed request for
a security review checklist, and prints the model response to the terminal.

The agent is instructed to:

- Provide concise, technically precise recommendations.
- Distinguish verified facts from suggestions.
- Avoid revealing credentials, tokens, secrets, or hidden configuration.

This stage is useful as a baseline because it keeps the runtime path small and easy to understand. It demonstrates the agent itself while leaving authentication, security policy, monitoring, and governance to the surrounding application and platform.

### Run Stage 1

From the `python-openai-agent` directory, create and activate the virtual
environment, then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Configure an OpenAI API key in the environment or in a local `.env` file:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
```

Then run the application:

```powershell
python app.py
```

The model can be selected with `OPENAI_MODEL`; the default is `gpt-4.1-mini`.

For complete stage-one details, see [python-openai-agent/readme.md](python-openai-agent/readme.md).

## Stage 1 Alternative: Local Ollama Agent

This sample copies the OpenAI baseline's security instructions and five-item
checklist request, using Ollama's native Python client instead of OpenAI's SDK.
No OpenAI API key, Azure credentials, or A365 CLI is required.

1. Install [Ollama for Windows](https://ollama.com/download/windows), launch it,
    and reopen PowerShell so the `ollama` command is available.
2. Download the default local model and verify it is available:

    ```powershell
    ollama pull llama3.2:3b
    ollama list
    ```

3. From the repository root, install the Python dependencies and run:

    ```powershell
    Set-Location python-ollama-agent
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install -r requirements.txt
    python app.py
    ```

`OLLAMA_MODEL` defaults to `llama3.2:3b`; `OLLAMA_HOST` defaults to
`http://localhost:11434`. Pull any replacement model before selecting it.
The first inference can take longer while the model loads into memory.

See [python-ollama-agent/readme.md](python-ollama-agent/readme.md) for configuration,
server startup, and troubleshooting.

## Enable and Set Up the A365 CLI

These steps are for Agent 365 onboarding, not for the standalone samples.
Installing the CLI does not enable Agent 365 in a tenant. Ask your administrator
to confirm tenant enablement and the licensing required for observability.
Blueprint setup requires Agent ID Developer (or a higher applicable role), with
a Global Administrator available for required admin consent. Azure provisioning
also requires an Azure subscription and appropriate resource permissions.
See the [official prerequisites](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/get-started#prerequisites).

1. **Install prerequisites.** Install the [.NET SDK](https://dotnet.microsoft.com/download)
    (8.0 or later, with a runtime supported by the CLI version) and
    [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli-windows).
    Reopen PowerShell and verify both installations:

    ```powershell
    dotnet --list-sdks
    dotnet --list-runtimes
    az version
    ```

2. **Install the A365 CLI.** Run this as your normal user:

    ```powershell
    dotnet tool install --global Microsoft.Agents.A365.DevTools.Cli
    ```

    If already installed, update it instead:

    ```powershell
    dotnet tool update --global Microsoft.Agents.A365.DevTools.Cli
    ```

3. **Make the command available and verify it.** Reopen PowerShell, then run:

    ```powershell
    a365 --version
    a365 --help
    ```

    If `a365` is not found, add the per-user .NET tools folder to this session:

    ```powershell
    $env:PATH = "$env:USERPROFILE\.dotnet\tools;$env:PATH"
    a365 --help
    ```

    Add that folder to your user PATH in Windows Environment Variables for future
    sessions. Global .NET tools are available only to the user who installs them.

4. **Sign in to the target tenant and subscription.** Replace the placeholders:

    ```powershell
    az login --tenant "your-tenant-id"
    az account set --subscription "your-subscription-id"
    az account show --query "{tenantId:tenantId, subscriptionId:id}" --output table
    ```

5. **Validate Agent 365 prerequisites and authentication.** This command works
    without a configuration file and can prompt for interactive sign-in:

    ```powershell
    a365 setup requirements
    ```

    Complete the reported prerequisites with your tenant administrator. The CLI
    uses the Microsoft-managed Agent 365 CLI application when available, or a
    supported tenant-owned application. Do not disable Conditional Access to
    bypass authentication failures.

6. **Review the integrated project's configuration.** From the repository root:

    ```powershell
    Set-Location a365-python-openai-agent
    a365 setup all --help
    ```

    Review [a365.config.json.example](a365-python-openai-agent/a365.config.json.example)
    and your local [a365.config.json](a365-python-openai-agent/a365.config.json).
    Use your own tenant ID and a valid CLI authentication application client ID,
    not an example ID or a service principal Object ID. Preserve existing local
    configuration. The CLI login application is distinct from the application's
    runtime observability credentials.

7. **Optionally provision Agent 365 resources.** Preview the configured setup:

    ```powershell
    a365 setup all --dry-run
    ```

    After reviewing the planned changes with your administrator, run:

    ```powershell
    a365 setup all
    ```

    This changes tenant resources and can create agent identities and permission
    grants. Complete any administrator consent handoff printed by the CLI. Keep
    generated configuration and secrets private. Registration alone does not
    guarantee that this sample's service principal can export telemetry; validate
    its permissions and runtime variables separately as described in
    [a365-python-openai-agent/readme.md](a365-python-openai-agent/readme.md).

For current commands and version-specific behavior, see the
[CLI installation guide](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/agent-365-cli)
and [setup reference](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/reference/cli/setup).

## Stage 2: A365-Integrated Agent

The second stage keeps the agent definition and security focus, while adding
Agent 365 observability through `a365_bootstrap.py`. The current prompt asks
for the same five-item security review checklist. The application configures the
exporter before running the agent and resolves observability tokens through an
Azure service principal. Microsoft OpenTelemetry `1.5.0` provides automatic
OpenAI Agents instrumentation and A365 baggage propagation. The sample uses
the production cluster and explicit S2S export, and flushes tracing at exit.

### Run Stage 2

From the `a365-python-openai-agent` directory, create the environment and
install its dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Configure `OPENAI_API_KEY`, `OPENAI_MODEL` (optional), `AZURE_TENANT_ID`,
`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, and `A365_AGENT_ID` in the environment
or a private `.env` file. `A365_OBSERVABILITY_SCOPE` is optional and defaults to
`api://9b975845-388f-4429-889e-eab1ef63949c/.default` for this app-only resolver.
Set `A365_AGENT_ID` equal to `AZURE_CLIENT_ID`: this sample uses standard
service-principal S2S authentication, which requires the observability
application role and admin consent. Registered agent-instance authentication
requires a different token flow, not a blueprint ID substituted for the agent ID.
Set `ENABLE_A365_OBSERVABILITY_EXPORTER=false` for console telemetry or `true`
(the sample default) to attempt Agent 365 export. Then run:

```powershell
python app.py
```

Python 3.10 or newer is required; the current development environment uses
Python 3.13. Do not reuse a virtual environment created with a removed Python
installation.

For complete stage-two details, see
[a365-python-openai-agent/readme.md](a365-python-openai-agent/readme.md).

For existing environments, follow the integrated README's package-removal
steps before installing the replacement distro. The standalone samples need
no A365 dependency changes.

The current A365 integration provides observability and service-principal authentication;
additional platform capabilities depend on the configured Agent 365 services
and deployment environment.

### Security

The following are platform integration opportunities, not controls implemented
by this telemetry sample. Policy enforcement and DLP require separate integration.

- Centralized authentication and credential handling instead of scattering API credentials through application code.
- Policy enforcement around which models, endpoints, tools, and data sources the agent may use.
- Better control over data handling, including reducing accidental exposure of prompts, responses, and sensitive context.
- A consistent boundary for validating requests and controlling tool or downstream-service access.
- A place to apply enterprise security requirements such as identity-based access, auditing, and environment-specific configuration.

### Telemetry and Operations

- Centralized request and response telemetry for understanding agent activity.
- Traceability across agent runs, model calls, tool calls, failures, and latency.
- Usage and performance data that can help identify reliability or cost issues.
- Consistent diagnostic information across local development, test, and production environments.
- Operational visibility without requiring every individual agent implementation to build its own monitoring pipeline.

### Governance and Lifecycle Management

These are potential outcomes of deployment and tenant configuration, not
automatic consequences of installing the telemetry library.

- A common integration pattern for multiple agents and teams.
- More consistent deployment and configuration across environments.
- Improved auditability for security reviews and incident investigation.
- A path to apply organization-wide policies as the agent evolves to use external tools or sensitive data.
- The ability to preserve the agent's application-level instructions while adding platform-level controls around it.

These capabilities depend on the Agent 365 configuration, tenant permissions,
enabled services, and deployment environment. Verify retention, policy, and
security behavior against the target environment rather than assuming that
every capability listed above is enabled locally.

## Development Notes

- Keep secrets out of source control. The local `.env` file is for development only.
- Treat model output as untrusted input, especially before passing it to tools or downstream systems.
- Validate tool inputs and restrict tools to the minimum permissions they require.
- Make side effects explicit and observable before enabling them in production.
- Verify the exact A365 security, telemetry, retention, and identity behavior in the target environment.

## Roadmap

- Compare OpenAI and Ollama checklist output and capture stage-two telemetry.
- Add representative tool calls with input validation and least-privilege access.
- Document deployment-specific identity, policy, and monitoring configuration.
