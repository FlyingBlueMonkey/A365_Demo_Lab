# A365 Demo Lab

This repository demonstrates the progression from a basic OpenAI agent to the same agent running through an A365-integrated client.

The project is intentionally split into two stages:

1. **Generic OpenAI Agent**: a small Python agent built with the OpenAI Agents SDK and no A365 dependency.
2. **A365-Integrated Agent**: the same agent experience connected through A365 for stronger security controls, operational telemetry, and enterprise governance.

The first stage provides a simple baseline. The second stage shows how an existing agent can gain enterprise capabilities without changing its core purpose or conversation behavior.

## Project Structure

```text
A365_Demo_Lab/
└── a365-python-openai-agent/
    ├── app.py
    ├── a365_bootstrap.py
    ├── requirements.txt
    └── readme.md
```

The current checkout contains the standalone stage-one implementation. The stage-two implementation will build on the same agent and prompt while adding the A365 client and its configuration.

## Stage 1: Generic OpenAI Agent

The stage-one sample is a minimal Python application using the OpenAI Agents SDK. It creates a `Security Architecture Assistant`, sends a fixed request for a five-item security review checklist, and prints the model response to the terminal.

The agent is instructed to:

- Provide concise, technically precise recommendations.
- Distinguish verified facts from suggestions.
- Avoid revealing credentials, tokens, secrets, or hidden configuration.

This stage is useful as a baseline because it keeps the runtime path small and easy to understand. It demonstrates the agent itself while leaving authentication, security policy, monitoring, and governance to the surrounding application and platform.

### Run Stage 1

From the `a365-python-openai-agent` directory, create and activate the virtual environment, then install the dependencies:

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

For complete stage-one details, see [a365-python-openai-agent/readme.md](a365-python-openai-agent/readme.md).

## Stage 2: A365-Integrated Agent

The second stage keeps the agent definition and user scenario the same, but routes the application through an A365-integrated client. This makes the comparison meaningful: the model capability and task remain constant while the surrounding security and operational controls become more enterprise-ready.

The A365-integrated client is intended to provide additional capabilities such as:

### Security

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

- A common integration pattern for multiple agents and teams.
- More consistent deployment and configuration across environments.
- Improved auditability for security reviews and incident investigation.
- A path to apply organization-wide policies as the agent evolves to use external tools or sensitive data.
- The ability to preserve the agent's application-level instructions while adding platform-level controls around it.

These capabilities depend on the A365 client, tenant configuration, enabled services, and deployment environment. They should be verified against the specific A365 integration used by the stage-two implementation; this README describes the intended architectural benefits rather than claiming that all controls are active in the current stage-one checkout.

## Why Compare the Two Stages?

The standalone agent makes the core application easy to inspect and test. The A365-integrated version demonstrates how the same application can be introduced into a more controlled operating model:

```text
User request
    |
    v
Agent instructions and model call
    |
    +--> Stage 1: direct OpenAI Agents SDK path
    |
    +--> Stage 2: A365-integrated client
              |
              +--> security and policy controls
              +--> telemetry and tracing
              +--> governance and operational visibility
```

The comparison highlights an important design principle: security and observability can be added at the client or platform boundary, allowing the agent's core behavior to remain focused and reusable.

## Development Notes

- Keep secrets out of source control. The local `.env` file is for development only.
- Treat model output as untrusted input, especially before passing it to tools or downstream systems.
- Validate tool inputs and restrict tools to the minimum permissions they require.
- Make side effects explicit and observable before enabling them in production.
- Verify the exact A365 security, telemetry, retention, and identity behavior in the target environment.

## Roadmap

- Add the A365 client dependency and bootstrap configuration.
- Run the same security checklist prompt through the integrated client.
- Capture and compare stage-one and stage-two telemetry.
- Add representative tool calls with input validation and least-privilege access.
- Document deployment-specific identity, policy, and monitoring configuration.
