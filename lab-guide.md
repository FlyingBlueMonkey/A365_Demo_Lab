# Instructor-Led Lab: OpenAI, Ollama, and Agent 365

## Class Overview

**Audience:** Python developers and security architects comfortable with terminals.
**Duration:** approximately 3.5 hours, excluding software installation and model downloads.
**Platform:** Windows, PowerShell 7, VS Code, and Python 3.13 for a consistent class environment.

By the end of the class, learners will run both model-provider baselines, inspect
supported Agent 365 tracing, distinguish CLI identity setup from runtime
authentication, and instrument an isolated Ollama copy without changing its prompt.

| Exercise | Time | Outcome |
| --- | --- | --- |
| 1. Prepare the workspace | 15 min | Correct checkout, interpreter, and class variables |
| 2. Run the OpenAI baseline | 20 min | Cloud-generated security checklist |
| 3. Run the Ollama baseline | 25 min | Local-generated checklist and provider comparison |
| 4. Validate A365 OpenAI locally | 25 min | Offline tests and observable agent/inference spans |
| 5. Install and validate the A365 CLI | 20 min | Correct tools, tenant, and prerequisite checks |
| 6. Export A365 OpenAI telemetry | 30 min | Approved live export attempt and recorded evidence |
| 7. Instrument an Ollama copy | 45 min | Manual parent/child scopes with local inference |
| 8. Debrief and clean up | 15 min | Comparison worksheet and safe cleanup |

Exercises 1-4 and the console portion of exercise 7 can run without live Azure
credentials. Exercises 5-6 require a prepared tenant or can be instructor
demonstrations. A valid OpenAI API key is required for exercises 2 and 4's model
run, but not for the offline regression tests.

## Source Materials

Use these throughout class rather than treating this guide as a different implementation:

- [Lab overview and CLI reference](readme.md).
- [Standalone OpenAI README](python-openai-agent/readme.md) and [implementation](python-openai-agent/app.py).
- [Standalone Ollama README](python-ollama-agent/readme.md) and [implementation](python-ollama-agent/app.py).
- [Supported A365 OpenAI README](a365-python-openai-agent/readme.md), [application](a365-python-openai-agent/app.py), [bootstrap](a365-python-openai-agent/a365_bootstrap.py), and [tests](a365-python-openai-agent/test_app.py).
- [Ollama A365 integration guide](a365-python-ollama-agent/readme.MD).

There are **three runnable samples**, not four. The A365 Ollama folder contains
only a README. Do not try to install requirements or run an application there.
Exercise 7 uses that README to construct a temporary learner copy elsewhere.

## Instructor Preparation

Complete this section before learners arrive.

1. Publish a tested repository commit or distribute a matching checkout. Confirm
   it includes `microsoft-opentelemetry==1.5.0` in the integrated requirements and
   the 21-test registered-agent regression suite. Do not tell learners to pull over local work.
2. Install VS Code with Python support, PowerShell 7, Git, and Python 3.13 on
   classroom machines. Verify `py -3.13 --version` and `pwsh --version`.
3. Install [Ollama for Windows](https://ollama.com/download/windows), launch it,
   and pre-download `llama3.2:3b`. Test it on classroom hardware. If it does not
   fit, select a smaller local model and announce the exact name to everyone.
4. Arrange OpenAI credentials with access to `gpt-4.1-mini` or announce a tested
   replacement. Set usage limits and explain that model calls can incur charges.
   Do not put shared API keys in slides, repository files, or submitted worksheets.
5. For the Azure portion, confirm tenant enablement, licensing assigned to an
   eligible user, administrative permissions, and access to the intended
   telemetry surfaces. Install the .NET SDK and Azure CLI before class.
6. Prepare a **registered Agent 365 instance and its Agent Blueprint** per learner,
   or an instructor-owned pair for demonstration. Use the integrated README's
   registration workflow with `--authmode s2s`, complete administrator handoffs,
   and confirm catalog discovery. Record tenant, blueprint client ID, distinct
   agent instance client ID, and platform registration ID. Entra Object IDs and
   the interactive CLI authentication app ID are not substitutes.
7. Confirm successful Agent 365 registration, not just blueprint creation. The
   supported registered-instance S2S flow does not require an observability
   application role solely to export; do not prepare a standard service principal
   as a replacement. Other setup permissions and tenant policy still apply.
8. Obtain a short-lived **blueprint** client-secret value through the approved
   administrator/credential workflow. Distribute it privately, schedule revocation,
   and never project CLI-generated secrets. The code does not decrypt protected
   CLI secrets or load plaintext secrets from generated JSON.
9. Verify the two-step FMI exchange and live export before promising a classroom
   result. The final token must identify the registered instance, not its blueprint.
   Review the
   [supported authentication documentation](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/microsoft-opentelemetry).
10. Provide the tenant ID, subscription ID if needed for CLI exercises, learner
    tags, and approved admin/security portal entry points. Establish who may
    provision resources and who may only observe.

**Instructor gate:** If live ingestion or permissions have not been validated,
announce exercises 5-6 as demonstrations or explicitly mark live export as
unverified. The repository's automated tests do not validate a real tenant.

## Class Rules

- Use synthetic checklist prompts only. Do not submit customer data or secrets.
- Run commands in a dedicated PowerShell 7 terminal. Do not switch terminals
  midway: the guide's variables and temporary credentials are session-scoped.
- Each project gets its own virtual environment. Use its explicit Python path;
  activation is unnecessary and cannot accidentally select another project's SDK.
- Never display credentials, record terminal sessions containing secrets, or
  paste secrets into Copilot/chat. Enter them directly into the local masked prompt.
- Console-only **A365** export does not make the OpenAI model local. OpenAI
  inference and its SDK's tracing are separate outbound paths.
- Installing telemetry does not implement DLP, tool authorization, or a Teams bot.
- Do not run tenant-changing commands until the instructor approves the target
  tenant, unique names, and planned changes.

## Exercise 1: Prepare the Workspace

**Instructor says:** "We will keep one model request constant and change the
provider and operational integration around it. First, establish the workspace."

1. Open the instructor-provided repository in VS Code. If you need a new checkout,
   run this from your chosen source directory; skip it if the checkout exists:

   ```powershell
   git clone https://github.com/FlyingBlueMonkey/A365_Demo_Lab.git
   Set-Location A365_Demo_Lab
   code .
   ```

2. In VS Code, open a PowerShell 7 terminal at the repository root. Define the
   class variables. Replace `student01` with your instructor-assigned tag:

   ```powershell
   $LabRoot = (Get-Location).Path
   $StudentTag = "student01"
   $ClassWorkspace = Join-Path $env:TEMP ("A365-Class-" + $StudentTag)
   git status --short --branch
   git rev-parse --short HEAD
   py -3.13 --version
   ```

   Record the commit ID. If you have local changes, preserve them and ask the
   instructor whether this checkout matches the class version. Do not reset it.

3. Confirm the four source directories listed in **Source Materials** are present.
   Open the root README and point out the two standalone providers, the supported
   A365 implementation, and the documentation-only Ollama integration folder.

4. Define a reusable masked credential prompt. This writes a secret only to the
   current process environment and does not echo it or put it in command history:

   ```powershell
   function Set-ClassSecret {
       param([Parameter(Mandatory)][string]$Name)
       $Secret = Read-Host "Enter $Name locally; do not share it" -AsSecureString
       $Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
       try {
           [Environment]::SetEnvironmentVariable(
               $Name,
               [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer),
               "Process"
           )
       }
       finally {
           [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
           $Secret.Dispose()
       }
   }
   ```

   Process environment variables still contain plaintext credentials and are
   inherited by child processes. This is a local lab convenience, not a secret
   store. Do not inspect or print the entire environment during class.

5. For predictable console-only exercises, remove inherited OTLP endpoint/header
   settings from this dedicated terminal only:

   ```powershell
   Remove-Item Env:OTEL_EXPORTER_OTLP_ENDPOINT, Env:OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, Env:OTEL_EXPORTER_OTLP_METRICS_ENDPOINT, Env:OTEL_EXPORTER_OTLP_LOGS_ENDPOINT, Env:OTEL_EXPORTER_OTLP_HEADERS -ErrorAction SilentlyContinue
   $env:APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL = "true"
   ```

**Checkpoint:** Every learner has the class commit, Python 3.13, `$LabRoot`, and
a unique `$StudentTag`. No credentials are visible in the shared display.

## Exercise 2: Run the OpenAI Baseline

**Instructor says:** "This sample is a model-backed assistant. Its prompt talks
about external tools, but no tools are actually registered or executed."

1. Open the [OpenAI README](python-openai-agent/readme.md). Inspect
   [app.py](python-openai-agent/app.py): identify `build_agent()`, the instructions,
   the fixed checklist question, and `Runner.run_sync(...)`.
2. Create the environment and install its own requirements:

   ```powershell
   Set-Location (Join-Path $LabRoot "python-openai-agent")
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m pip check
   ```

3. Enter your API key locally and select the announced model:

   ```powershell
   Set-ClassSecret -Name OPENAI_API_KEY
   $env:OPENAI_MODEL = "gpt-4.1-mini"
   .\.venv\Scripts\python.exe app.py
   ```

4. Read the checklist. Record the provider, model, and one recommendation you
   consider useful. Do not record keys. Expect generated text, not byte-identical
   answers across learners; even the number of items is a model instruction,
   not a programmatic formatting guarantee.
5. In VS Code, use **Python: Select Interpreter** and select this project's
   `.venv` if you want to inspect types or run through the editor. Explicit terminal
   commands continue to use the correct environment regardless of this selection.

**Checkpoint:** The script prints a security checklist. A 401 error requires a
valid key; a model-access error requires the instructor-approved model. Do not
continue troubleshooting by placing credentials directly in source code.

**Discuss:** Which parts are application instructions, and which parts would
require an actual control outside the model? There is no A365 telemetry setup here.

## Exercise 3: Run the Ollama Baseline

**Instructor says:** "Keep the security question the same. Replace the provider,
not the purpose of the assistant."

1. Open the [Ollama README](python-ollama-agent/readme.md) and compare its
   [application](python-ollama-agent/app.py) with the OpenAI application. Locate
   the native `Client`, system/user messages, and `stream=False`.
2. Verify the preinstalled server and model:

   ```powershell
   ollama --version
   ollama list
   Invoke-RestMethod -Uri "http://localhost:11434/api/tags" | Select-Object -ExpandProperty models | Select-Object name
   ```

   If the model is missing, run `ollama pull llama3.2:3b`. If the server is not
   available, launch the Windows Ollama application. Alternatively, open a
   **second** terminal, run `ollama serve`, and leave it running. Do not start a
   second server if the application already owns port 11434.
3. In the original class terminal, create the Ollama environment and run:

   ```powershell
   Set-Location (Join-Path $LabRoot "python-ollama-agent")
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m pip check
   $env:OLLAMA_HOST = "http://localhost:11434"
   $env:OLLAMA_MODEL = "llama3.2:3b"
   .\.venv\Scripts\python.exe app.py
   ```

4. Compare its checklist with exercise 2. Record differences in specificity and
   observed responsiveness. First-run latency includes loading the model, so
   do not claim a controlled performance comparison from one run.
5. Demonstrate a recoverable error using a deliberately nonexistent model:

   ```powershell
   $SavedOllamaModel = $env:OLLAMA_MODEL
   $env:OLLAMA_MODEL = "class-model-that-does-not-exist"
   .\.venv\Scripts\python.exe app.py
   $env:OLLAMA_MODEL = $SavedOllamaModel
   .\.venv\Scripts\python.exe app.py
   ```

   Expect the first run to fail and the restored run to succeed. This baseline
   does not generate A365 error spans; it only raises the client error.

**Checkpoint:** The local model produces output after recovery. Ollama needs
neither `OPENAI_API_KEY` nor Azure credentials. An inherited OpenAI key is unused
by this script; do not delete it yet because exercise 4 still needs it.

**Discuss:** A non-cloud model on localhost keeps inference local. Remote hosts,
cloud models, or added telemetry can change where data travels.

## Exercise 4: Validate A365 OpenAI Locally

**Instructor says:** "We will verify the telemetry wiring before trusting a live
portal. No Azure permission grant is needed for the offline tests."

1. Open the [integrated README](a365-python-openai-agent/readme.md). In its
   [bootstrap](a365-python-openai-agent/a365_bootstrap.py), find
   `use_microsoft_opentelemetry`, the S2S toggle, the production cluster, and
   invocation-input suppression. In its [application](a365-python-openai-agent/app.py),
   find `BaggageBuilder`, the explicit agent ID requirement, and provider cleanup.
2. Install into the integrated project's environment:

   ```powershell
   Set-Location (Join-Path $LabRoot "a365-python-openai-agent")
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m pip check
   ```

   Expected: no broken requirements. If an older environment is reused, follow
   the README's migration steps. If stale optional OTLP exporters conflict,
   use a fresh class environment rather than randomly downgrading the distro.
3. Run the offline tests from the root:

   ```powershell
   Set-Location $LabRoot
   .\a365-python-openai-agent\.venv\Scripts\python.exe -m unittest discover -s a365-python-openai-agent -v
   ```

   Expected: **21 tests, OK** for this class version. Review the test that verifies
   real distro spans with an in-memory exporter: it does not call a cloud model
   or acquire a live token. A passing result proves wiring, not tenant ingestion.
4. Supply clearly synthetic identity values for the console exercise, and
   explicitly disable service export:

   ```powershell
   Set-Location (Join-Path $LabRoot "a365-python-openai-agent")
   $env:AZURE_TENANT_ID = "11111111-1111-1111-1111-111111111111"
   $env:A365_BLUEPRINT_ID = "22222222-2222-2222-2222-222222222222"
   $env:A365_AGENT_ID = "33333333-3333-3333-3333-333333333333"
   $env:A365_REGISTRATION_ID = "44444444-4444-4444-4444-444444444444"
   $env:ENABLE_A365_OBSERVABILITY_EXPORTER = "false"
   .\.venv\Scripts\python.exe app.py
   ```

   These are not usable tenant credentials. Do not enable live export with them.
   The Azure secret is not needed here because the console exporter does not
   invoke the token resolver. The model still uses your OpenAI key.
5. Inspect the console spans. Find `gen_ai.operation.name` values `invoke_agent`
   and `chat`, the tenant/agent identity attributes, and model metadata. Check the
   inference span's parent relationship. The terminal may contain additional
   trace output; it is not limited to the printed checklist.

**Checkpoint:** All 21 tests pass and the console model run emits identifiable
agent/inference spans. Do not switch to live export until the instructor releases
the next gate.

**Discuss:** The distro auto-instruments OpenAI Agents. Why would this same
instrumentation not capture native Ollama calls?

## Exercise 5: Install and Validate the A365 CLI

**Instructor says:** "CLI sign-in is an onboarding identity. It does not replace
the application credentials that acquire an observability token."

1. Follow the [root CLI instructions](readme.md#enable-and-set-up-the-a365-cli).
   Verify preinstalled prerequisites:

   ```powershell
   dotnet --list-sdks
   dotnet --list-runtimes
   az version
   ```

   The CLI requires a supported .NET runtime; the SDK must be 8.0 or newer.
   If required software is missing, complete the documented installation and
   reopen PowerShell. Redefine exercise 1's variables/function in the new terminal.
2. If `a365` is not installed, install it. If already installed, run the update
   command instead; do not treat both commands as mandatory:

   ```powershell
   dotnet tool install --global Microsoft.Agents.A365.DevTools.Cli
   ```

   ```powershell
   dotnet tool update --global Microsoft.Agents.A365.DevTools.Cli
   ```

3. Verify command discovery. If needed, add the tools directory to this session:

   ```powershell
   $env:PATH = "$env:USERPROFILE\.dotnet\tools;$env:PATH"
   a365 --version
   a365 --help
   ```

4. Enter the instructor-provided nonsecret identifiers, sign in interactively,
   and confirm the intended tenant/subscription:

   ```powershell
   $ClassTenantId = Read-Host "Enter the approved class tenant ID"
   $ClassSubscriptionId = Read-Host "Enter the approved class subscription ID"
   az login --tenant $ClassTenantId
   az account set --subscription $ClassSubscriptionId
   az account show --query "{tenantId:tenantId, subscriptionId:id}" --output table
   a365 setup requirements
   ```

   The CLI may prompt for its own sign-in. Complete only the instructor-approved
   authentication flow. If Conditional Access blocks it, ask the identity
   administrator; do not disable security policy.
5. Instructor only, or learners with explicit authorization: demonstrate
   config-free registration in an isolated directory so committed sample config
   is not accidentally reused:

   ```powershell
   $RegistrationDirectory = Join-Path $ClassWorkspace "registration"
   New-Item -ItemType Directory -Path $RegistrationDirectory -Force | Out-Null
   Set-Location $RegistrationDirectory
   $RegisteredAgentName = "A365-Class-$StudentTag"
   a365 setup all --agent-name $RegisteredAgentName --tenant-id $ClassTenantId --authmode s2s --dry-run
   ```

   **Stop:** review the plan and obtain approval. Only then run:

   ```powershell
   a365 setup all --agent-name $RegisteredAgentName --tenant-id $ClassTenantId --authmode s2s
   Set-Location $LabRoot
   ```

   Record newly created resource identifiers privately. Complete any printed
   administrator handoff. Do not project generated configuration that may contain
   secrets. This operation does not install Python code or turn a script into a bot.

**Checkpoint:** Learners can explain which identity logged into the CLI, which
tenant was targeted, and whether any resources were actually created. If step 5
was skipped, record "registration demonstration only" rather than claiming an
agent was provisioned.

**Critical distinction:** The registered agent instance and its blueprint have
different client IDs. Runtime now uses both, plus the platform registration ID.
Verify the generated `agentBlueprintId`, `agenticAppId`, and `agentRegistrationId`
and catalog visibility before using that pair in exercise 6.

## Exercise 6: Export A365 OpenAI Telemetry

**Instructor gate:** Continue only with a registered agent/blueprint pair,
its blueprint credential, catalog verification, and the correct licensed tenant.
Otherwise retain console-only settings and observe the instructor demonstration.

1. Read the integrated README's authentication and privacy sections. Confirm the
   bootstrap implements blueprint FMI followed by an agent-instance assertion
   exchange. It validates the final app-only token and prewarms the cache before
   model inference. No standard service-principal or delegated-token fallback exists.
2. Replace the synthetic console identity with your instructor-issued runtime
   blueprint/instance identity, then enter the blueprint secret locally. Use
   the IDs from your generated config or the instructor's privately issued pair:

   ```powershell
   Set-Location (Join-Path $LabRoot "a365-python-openai-agent")
   $env:AZURE_TENANT_ID = $ClassTenantId
   $env:A365_BLUEPRINT_ID = Read-Host "Enter the approved Agent Blueprint client ID"
   $env:A365_AGENT_ID = Read-Host "Enter the distinct registered Agent ID (client ID)"
   $env:A365_REGISTRATION_ID = Read-Host "Enter the Agent 365 platform registration ID"
   Set-ClassSecret -Name A365_BLUEPRINT_CLIENT_SECRET
   $env:ENABLE_A365_OBSERVABILITY_EXPORTER = "true"
   .\.venv\Scripts\python.exe app.py --check-config
   ```

   Compare all four metadata values with the registration and catalog.
   `--check-config` does not contact the catalog or prove live registration.
   Blueprint ID, Agent ID, Object ID, secret ID, and CLI login ID are not interchangeable.
3. Run the same checklist request:

   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```

   Expected: model output and an export attempt. The application flushes/shuts
   down the provider before exit. Export is best-effort; a checklist can print
   successfully even when background token acquisition or export fails.
4. Open the instructor-approved admin/security telemetry surface. For Agent 365
   admin activity, start at `https://admin.cloud.microsoft/#/agents/all` where
   your tenant exposes that view. Find the registered instance and verify its
   relationship to the blueprint, then inspect its activity. Catalog discovery
   and telemetry visibility are separate checks.
5. Locate the run using its tenant, agent client ID, service name
   `security-architecture-assistant`, and approximate execution time. Record
   whether spans were found, where they were found, and what evidence links them
   to your invocation. Do not fabricate a result if the surface is unavailable.
6. If no data appears, investigate in this order: matching identity and correct
   blueprint secret **value**; completed platform registration; exporter toggle; valid agent root span;
   tenant licensing; ingestion delay and portal permissions. HTTP 200 alone is
   not proof of usable visibility. Follow the integrated README's guidance.
7. Return to a safe default before the next exercise:

   ```powershell
   $env:ENABLE_A365_OBSERVABILITY_EXPORTER = "false"
   ```

**Checkpoint:** Record "live telemetry observed" only with portal/query evidence.
Otherwise record the actual failure or "not attempted". This is an operational
verification exercise, not a test of whether the model returned plausible text.

**Discuss:** Invocation input is suppressed, but inference content and exception
data still require review. Telemetry does not enforce DLP or deny tool access.

## Exercise 7: Instrument an Isolated Ollama Copy

**Instructor says:** "Now use the documentation-only Ollama guide as an engineering
exercise. Keep the original sample intact and add supported manual tracing to a copy."

This exercise uses the same registered-instance blueprint FMI flow as exercise 6.
For a separate Ollama identity, provision a separate registered instance and use
its own metadata; a different service name alone does not create an Agent ID.

1. Open [the Ollama A365 guide](a365-python-ollama-agent/readme.MD). Identify the
   supported imports, the manual scope requirement, and the authentication
   distinction. Do not create files in that documentation-only folder.
2. Create a fresh exercise directory **outside the repository**. If it already
   exists from another class attempt, pick a different `$StudentTag` or directory
   rather than overwriting work:

   ```powershell
   $OllamaExercise = Join-Path $ClassWorkspace "ollama-a365"
   if (Test-Path $OllamaExercise) { throw "Choose a fresh exercise directory before continuing" }
   New-Item -ItemType Directory -Path $OllamaExercise -Force | Out-Null
   Copy-Item (Join-Path $LabRoot "python-ollama-agent/app.py") $OllamaExercise
   Copy-Item (Join-Path $LabRoot "python-ollama-agent/requirements.txt") $OllamaExercise
   Copy-Item (Join-Path $LabRoot "a365-python-openai-agent/a365_bootstrap.py") $OllamaExercise
   Set-Location $OllamaExercise
   py -3.13 -m venv .venv
   code --new-window $OllamaExercise
   ```

   Edit the copy in the new VS Code window, but run commands in the original
   class terminal. Its working directory is now `$OllamaExercise`, and its
   `$LabRoot`, helper function, and session variables remain available.
3. In the copied requirements, retain `ollama` and `python-dotenv`; add only the
   supported telemetry distribution and resolver dependency. The complete file is:

   ```text
   ollama
   python-dotenv
   microsoft-opentelemetry==1.5.0
   httpx
   ```

   Install and check:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m pip check
   ```

4. In the **copied** bootstrap, change `service.name` from
   `security-architecture-assistant` to `security-architecture-assistant-ollama`.
   Retain S2S configuration, identity validation, suppressed invocation input,
   disabled offline storage, and disabled log/metric collection. Do not copy
   credentials or CLI-generated JSON from the original project.
5. Replace the **copied** application's content with this manual-scope version.
   It preserves the baseline instructions and question. Empty telemetry request
   content deliberately avoids recording the prompt; no raw response is attached
   to a span. The model still receives the complete question.

   ```python
   import os
   from typing import cast
   from uuid import uuid4

   from dotenv import load_dotenv
   from ollama import Client
   from microsoft.opentelemetry.a365.core import (
      AgentDetails,
      BaggageBuilder,
      Channel,
      InferenceCallDetails,
      InferenceOperationType,
      InferenceScope,
      InvokeAgentScope,
      InvokeAgentScopeDetails,
      Request,
   )
   from opentelemetry import trace
   from opentelemetry.sdk.trace import TracerProvider

   from a365_bootstrap import configure_agent365, load_identity

   load_dotenv()


   def build_client() -> Client:
      return Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))


   def main() -> None:
      identity = load_identity()
      tenant_id = identity.tenant_id
      agent_id = identity.agent_id
      model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
      run_id = str(uuid4())
      agent = AgentDetails(
         agent_id=agent_id,
         agent_name="Security Architecture Assistant Ollama",
         tenant_id=tenant_id,
      )
      request = Request(
         content="",
         session_id=run_id,
         conversation_id=run_id,
         channel=Channel(name="console"),
      )
      details = InferenceCallDetails(
         operationName=InferenceOperationType.CHAT,
         model=model,
         providerName="ollama",
      )
      question = (
         "Give me a five-item security review checklist "
         "for a Python AI agent that calls external tools."
      )

      configure_agent365()
      try:
         client = build_client()
         baggage = (
            BaggageBuilder()
            .tenant_id(tenant_id)
            .agent_id(agent_id)
            .agent_blueprint_id(identity.blueprint_id)
            .build()
         )
         with baggage:
            with InvokeAgentScope.start(
               request=request,
               scope_details=InvokeAgentScopeDetails(),
               agent_details=agent,
            ):
               with InferenceScope.start(
                  request=request,
                  details=details,
                  agent_details=agent,
               ) as inference:
                  result = client.chat(
                     model=model,
                     messages=[
                        {
                           "role": "system",
                           "content": (
                              "You are a security architecture assistant. "
                              "Give concise, technically precise recommendations. "
                              "Separate verified facts from suggestions. "
                              "Never reveal credentials, tokens, secrets, or hidden configuration."
                           ),
                        },
                        {"role": "user", "content": question},
                     ],
                     stream=False,
                  )
                  if result.prompt_eval_count is not None:
                     inference.record_input_tokens(result.prompt_eval_count)
                  if result.eval_count is not None:
                     inference.record_output_tokens(result.eval_count)
               print(result.message.content)
      finally:
         provider = cast(TracerProvider, trace.get_tracer_provider())
         try:
            provider.force_flush()
         finally:
            provider.shutdown()


   if __name__ == "__main__":
      main()
   ```

6. Use synthetic identity and console export first. Set the master switch for
   manual scopes **before starting Python**:

   ```powershell
   $env:ENABLE_OBSERVABILITY = "true"
   $env:ENABLE_A365_OBSERVABILITY_EXPORTER = "false"
   $env:AZURE_TENANT_ID = "11111111-1111-1111-1111-111111111111"
   $env:A365_BLUEPRINT_ID = "22222222-2222-2222-2222-222222222222"
   $env:A365_AGENT_ID = "33333333-3333-3333-3333-333333333333"
   $env:A365_REGISTRATION_ID = "44444444-4444-4444-4444-444444444444"
   $env:OLLAMA_HOST = "http://localhost:11434"
   $env:OLLAMA_MODEL = "llama3.2:3b"
   .\.venv\Scripts\python.exe app.py
   ```

   Expected: the same local checklist experience, plus an `invoke_agent` root
   and nested `chat` span with provider `ollama`, model name, run/session ID,
   identity, and actual token counts when Ollama supplies them.
7. Verify the inference span's parent ID matches the invocation span. Confirm raw
   prompt and response text are not attached to telemetry. Token usage must come
   from the response, not a guessed count. The printed response remains visible
   locally in the terminal.
8. Repeat exercise 3's nonexistent-model test in this copy. Restore the real
   model after the failure. Confirm the scope context managers close their spans
   and the process flushes them on failure; review error metadata for sensitive
   content before claiming the tracing is safe.
9. Optional live export, instructor approved: provision/register a **second**
   Ollama agent instance using the registration workflow. Supply its tenant,
   blueprint ID, distinct Agent ID, platform registration ID, and blueprint
   secret value. Confirm catalog discovery, then set
   `ENABLE_A365_OBSERVABILITY_EXPORTER=true` and run the copied app.
   Repeat exercise 6's evidence checks using service name
   `security-architecture-assistant-ollama`. A separate service name alone does
   not create a separate Agent 365 identity. Do not enable export with synthetic IDs.

**Checkpoint:** Each learner explains why baggage alone is insufficient, why
manual scopes replace OpenAI auto-instrumentation, and which identity their
token resolver can legitimately represent. The original Ollama source and the
documentation-only folder are unchanged.

## Exercise 8: Debrief and Clean Up

1. Complete this comparison privately; submit findings without secrets or raw
   generated configuration:

   | Implementation | Inference location | Tracing approach | Live A365 result |
   | --- | --- | --- | --- |
   | Standalone OpenAI | Cloud | No A365 setup; OpenAI SDK tracing is separate | Not applicable |
   | Standalone Ollama | Local non-cloud model on localhost | No A365 setup | Not applicable |
   | A365 OpenAI | Cloud | Supported distro auto-instrumentation | Observed / failed / not attempted |
   | Temporary A365 Ollama copy | Local model, telemetry optionally remote | Supported manual scopes | Observed / failed / not attempted |

2. Discuss: What did telemetry add? What still needs separate authorization,
   DLP, input validation, hosting, and governance? Which observed facts support
   your answer, and which claims remain unverified?
3. Remove secrets and class identity overrides from the terminal environment:

   ```powershell
   Remove-Item Env:OPENAI_API_KEY, Env:AZURE_CLIENT_SECRET, Env:AZURE_TENANT_ID, Env:AZURE_CLIENT_ID, Env:A365_AGENT_ID, Env:A365_BLUEPRINT_ID, Env:A365_BLUEPRINT_CLIENT_SECRET, Env:A365_REGISTRATION_ID, Env:A365_CONFIG_DIR -ErrorAction SilentlyContinue
   Remove-Item Env:ENABLE_A365_OBSERVABILITY_EXPORTER, Env:ENABLE_OBSERVABILITY, Env:OLLAMA_HOST, Env:OLLAMA_MODEL, Env:OPENAI_MODEL -ErrorAction SilentlyContinue
   Remove-Item Env:APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL -ErrorAction SilentlyContinue
   Set-Location $LabRoot
   git status --short
   ```

   This clears only current-process settings. If you created private `.env`
   files or used persistent secret storage, remove those credentials separately.
   Close the dedicated terminal to discard its remaining process environment.
4. Instructor/administrator: revoke the issued lab client secrets and review
   the inventory of applications, registrations, and permissions created in
   class. Remove only the class-owned resources after approval. Do not run a
   generic `a365 cleanup` against committed or shared configuration.
5. Stop only the Ollama server that you started in the second terminal, using
   Ctrl+C there. Do not terminate a shared classroom server or uninstall models
   other learners still need.
6. Keep or delete your temporary class workspace according to the instructor's
   retention policy after checking for generated secrets. Nothing in this guide
   requires deleting the repository or its Git history.

## Troubleshooting Desk

| Symptom | Check / next action |
| --- | --- |
| `py -3.13` not found | Install the class Python version or agree on a supported interpreter with the instructor before creating environments. |
| Imports unresolved in VS Code | Select the `.venv` of the project currently being inspected. Explicit terminal Python paths remain authoritative for the run. |
| `pip check` reports old OTLP versions | Use a fresh class environment; do not mix dependencies from the old A365 SDK and the supported distro. |
| OpenAI 401 or model denial | Confirm the private key and model entitlement; never log the key to diagnose it. |
| Ollama connection refused | Launch Ollama or use the server terminal; verify host/port. |
| Ollama model missing | Pull the exact configured name and restore it after the deliberate error exercise. |
| No manual Ollama spans | Set `ENABLE_OBSERVABILITY=true` before Python startup; check nested supported scopes and context. |
| `A365_AGENT_ID` startup error | Set the distinct instance client ID, blueprint ID, and registration ID, or supply the documented CLI metadata. |
| Runtime identity mismatch | Verify the blueprint-to-instance relationship and final token identity; never substitute the blueprint or CLI login ID for Agent ID. |
| Azure token acquisition fails | Confirm tenant, application ID, secret value, expiry, and observability resource access privately. |
| Export 401/403 | Check final agent-instance token identity/audience, platform registration, tenant eligibility, and documented S2S requirements. |
| Checklist prints but no portal data | Model success is independent of export success; check exporter logs, identity, licensing, root span, permissions, and ingestion delay. |
| Generated tenant config appeared in Git changes | Stop before committing or pushing. Review and protect it; do not assume every generated file is safe to publish. |

## Verification Notes

The registered-agent implementation's 21 tests and the supported manual-scope APIs were
validated offline. The classroom code example is a learner exercise, not a fourth
implemented repository agent. Live model quality, machine-specific performance,
tenant provisioning, and telemetry visibility must be verified on the actual
class environment. Record skipped or failed gates honestly.