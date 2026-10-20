# A365 Teams Chat Summary Agent

Stage 3 adds a read-only Microsoft Graph tool to the OpenAI Agents SDK agent,
while retaining Microsoft Agent 365 observability, tracing, and tenant/agent
baggage. The existing examples are unchanged.

The sample supports two entry points: the original local CLI in [app.py](app.py)
and an authenticated Teams service in [teams_app.py](teams_app.py), using the
Microsoft 365 Agents SDK for Python. A365 SDK packages provide observability;
Microsoft Graph REST v1.0 provides chat access via `httpx`.
It does not use A365 MCP tooling or impersonate a provisioned agent identity
when reading chats. The CLI uses delegated user permissions; the Teams service
uses its own bot application with chat-specific resource-specific consent (RSC).

For Teams @mentions and Kubernetes hosting, see [Enable Teams](#enable-teams).

## How It Works

1. The user selects a chat ID and a maximum number of messages on the command line.
2. The application configures A365 observability for the summary run.
3. Azure Identity signs the user in through the device-code flow and acquires
  a delegated Microsoft Graph token.
4. The OpenAI agent calls `read_teams_chat`, a tool bound to the selected chat.
5. The tool retrieves recent messages from Graph, converts HTML to text, and
  returns bounded message content and coverage metadata to the model.
6. The agent prints a summary with message references. A365 instruments the
  agent run and tool execution with tenant and agent context.

The `--list-chats` mode only signs in and queries Graph. It does not initialize
A365 observability or invoke the OpenAI model.

## Prerequisites

- Python 3.10 or newer and PowerShell, or an equivalent shell.
- An OpenAI API key with access to the configured model.
- A Microsoft 365 work or school account with Teams chat access.
- A Microsoft Entra app registration for delegated Graph sign-in, configured below.
- An existing, authorized A365 observability service principal and provisioned
  agent ID for summary runs. See the [stage-2 setup](../a365-python-openai-agent/readme.md).

## Identity and Permissions

Two authentication contexts are deliberately separate:

| Purpose | Identity | Configuration |
| --- | --- | --- |
| A365 telemetry | Existing observability service principal | `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `A365_AGENT_ID` |
| Graph chat reads | Signed-in work/school user through a public-client app | Same tenant, separate `GRAPH_CLIENT_ID`, delegated `Chat.Read` |
| Teams delivery and hosted Graph reads | Separate single-tenant bot app | `TEAMS_BOT_CLIENT_ID`, `TEAMS_BOT_CLIENT_SECRET`; application RSC `ChatMessage.Read.Chat` granted per installed group chat |

For the Graph app registration in Microsoft Entra ID:

1. Register a single-tenant application in the same tenant as the user.
2. Under **Authentication > Advanced settings**, enable **Allow public client flows**.
3. Under **API permissions**, add **Microsoft Graph > Delegated permissions > Chat.Read**.
4. Obtain consent according to your tenant's consent policy. An administrator
   may need to grant consent if user consent is restricted.
5. Set `GRAPH_CLIENT_ID` to that application's client ID. Do not configure a
   client secret for device-code sign-in.

The user must have access to the selected chat. This example does not request
application `Chat.Read.All`, perform tenant-wide reads, or write messages.
The observability service principal's token is never reused for Graph.
The A365 exporter must already be provisioned and authorized as in stage 2.
Use the actual provisioned agent ID for `A365_AGENT_ID`.

Device-code login must be permitted by tenant Conditional Access policy. If it
is blocked, use an organization-approved authentication flow rather than
weakening policy. This sample targets the global Microsoft cloud only.

## Setup

Python 3.10 or newer is required. From this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Populate `.env` with your OpenAI API key, existing A365 observability settings,
and the Graph public-client application ID. Existing environment variables take
precedence. The local `.env`, virtual environment, and caches are ignored by git.
Do not commit credentials or chat exports. `OPENAI_MODEL` defaults to
`gpt-4.1-mini`; `A365_OBSERVABILITY_SCOPE` defaults to the same resource as stage 2.
The bootstrap also accepts the stage-2 `AGENT365OBSERVABILITY__TENANTID`,
`CLIENTID`, and `CLIENTSECRET` equivalents for the Azure settings.

### Configuration Reference

Use the fields in [.env.example](.env.example) to configure the local `.env` file:

| Setting | Required For | Meaning or Default |
| --- | --- | --- |
| `AZURE_TENANT_ID` | Both modes | Microsoft Entra tenant containing the app and user. |
| `GRAPH_CLIENT_ID` | Both modes | Public-client application ID used for delegated Graph sign-in. |
| `OPENAI_API_KEY` | Summaries | API key for the OpenAI model, not an Azure or Graph credential. |
| `OPENAI_MODEL` | Optional | Model name; defaults to `gpt-4.1-mini`. |
| `AZURE_CLIENT_ID` | Summaries | A365 observability service-principal client ID, not `GRAPH_CLIENT_ID`. |
| `AZURE_CLIENT_SECRET` | Summaries | Secret belonging to the observability service principal. |
| `A365_AGENT_ID` | Summaries | Actual provisioned Agent 365 agent ID used in trace baggage and exporter validation. |
| `A365_OBSERVABILITY_SCOPE` | Optional | Observability resource scope; defaults to `api://9b975845-388f-4429-889e-eab1ef63949c/.default`. |

The complete fallback environment-variable names are
`AGENT365OBSERVABILITY__TENANTID`, `AGENT365OBSERVABILITY__CLIENTID`, and
`AGENT365OBSERVABILITY__CLIENTSECRET`. The corresponding `AZURE_*` setting
takes precedence when populated. `A365_AGENT_ID` has no fallback in this example.

The application loads `.env` from beside [app.py](app.py), regardless of the
terminal's working directory. The run commands below assume this sample's directory.

## Run

List up to 50 accessible chat IDs without sending chat data to OpenAI:

```powershell
python app.py --list-chats
```

Follow the device-code sign-in instructions in your terminal. Tokens are cached
in memory only, so a new process may require another sign-in. Listing requires
only `AZURE_TENANT_ID` and `GRAPH_CLIENT_ID`. Output includes `has_more` when the
listing is capped; it is not necessarily a list of the most recent chats.

Choose an exact `id` from the output, not a Teams URL:

```powershell
python app.py --chat-id "19:your-chat-id@thread.v2"
python app.py --chat-id "19:your-chat-id@thread.v2" --max-messages 50
```

The agent calls its Graph tool and prints an overview, decisions, action items,
and open questions with supporting message IDs and timestamps. The tool accepts
no model-supplied parameters: the CLI fixes both the chat and retrieval limit.

### Command-Line Options

| Option | Behavior |
| --- | --- |
| `--list-chats` | Prints JSON containing chat IDs, topics, types, URLs, and a `has_more` flag. |
| `--chat-id ID` | Summarizes the exact Graph chat ID supplied by the user. |
| `--max-messages N` | Limits retrieved message records to 1 through 200; defaults to 100. Does not change the chat-list limit. |
| `--help` | Prints usage without signing in or calling external services. |

Exactly one of `--list-chats` or `--chat-id` is required; they cannot be used
together. To run without activating the virtual environment, replace `python`
with `.\.venv\Scripts\python.exe` in the commands above.

### Example Output

An illustrative chat-list response looks like this. IDs and URLs are placeholders:

```json
{
  "chats": [
    {
      "id": "19:example-chat@thread.v2",
      "topic": "Release planning",
      "chatType": "group",
      "webUrl": "https://teams.microsoft.com/l/chat/19%3Aexample-chat%40thread.v2/0"
    }
  ],
  "has_more": false
}
```

Some chats have no topic; use their exact `id` rather than relying on a topic
being present or unique. The summary is generated text, not a fixed JSON schema.
Its instructions request an overview, decisions, action items, open questions,
message count, and time range. Owners and due dates should appear only when
explicitly stated in the source messages. Review the cited messages before
acting on the summary.

## Scope and Data Handling

- In Teams mode, only an explicit bot @mention with a supported summary command
  triggers a Graph/model call. The authenticated activity selects the group chat;
  prompts cannot select another chat. Replies stay in the originating chat.
- Reads `/chats/{id}/messages`, newest first by creation time, follows Graph
  pagination, then presents messages to the model in chronological order.
- Defaults to 100 retrieved records; `--max-messages` accepts 1 through 200.
  Deleted and system messages count toward that bound but are not summarized.
- Converts HTML bodies to text without fetching links. Attachments, hosted
  images, files, meeting recordings, and meeting transcripts are not downloaded.
- Bounds body text to 4,000 characters per message and 60,000 characters total,
  favoring newer messages. Coverage flags tell the model when older messages
  or body text were omitted. A bounded summary is not a full-history summary.
- Graph failures stop the run instead of returning made-up chat content.
  For HTTP 403, check consent, membership, and tenant policy. For HTTP 429,
  wait for Graph's `Retry-After` interval before retrying; there is no automatic
  retry loop in this demo.
- Continuation URLs must remain on HTTPS `graph.microsoft.com/v1.0`; redirects
  are disabled so bearer tokens are not forwarded to another host.
- Retrieved text and sender names are untrusted model input. Instructions ask
  the model to ignore embedded commands, and the tool boundary prevents it from
  choosing another chat or performing writes. Prompt wording alone is not a
  complete defense against prompt injection.
- **Selected message bodies and sender display names are sent to the configured
  OpenAI model.** Only run this on chats approved for that processing. The summary
  itself may contain confidential data and is printed to the terminal in CLI
  mode or posted to the originating group chat in Teams mode.
- A365 invocation input suppression and OpenAI Agents
  `trace_include_sensitive_data=False` are enabled. The A365 instrumentor
  replaces the default OpenAI trace exporter. These settings reduce telemetry
  payload exposure but do not prevent model processing or establish tenant
  retention policy. Verify exported telemetry and downstream retention in your
  environment before using real confidential chats.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| Missing configuration error | Populate the named setting in the sample's `.env` or environment. Listing needs no OpenAI key or observability credentials. |
| Device-code sign-in fails | Verify the tenant, public-client application ID, enabled public-client flows, consent, and Conditional Access policy. |
| Graph HTTP 401 or 403 | Verify delegated `Chat.Read` consent, the signed-in user's access to the chat, and tenant restrictions. Observability permissions do not grant chat access. |
| Graph HTTP 404 | Use an exact chat ID from Graph, not a Teams URL or channel ID; verify that the signed-in user can access it. |
| Graph HTTP 429 | Respect Graph's `Retry-After` interval before rerunning. The sample does not retry automatically. |
| OpenAI model request fails | Check the API key, model availability, account quota, and connectivity. |
| No readable messages or a partial summary | Check the retrieval limit, body-text caps, and whether the selected records are deleted, system, or attachment-only messages. |
| No A365 telemetry appears | Verify the provisioned agent ID, observability service-principal authorization, tenant, resource scope, and exporter connectivity. Successful Graph access does not validate A365 export. |

Do not paste tokens, client secrets, or private chat content into troubleshooting
logs. Keep tenant policy intact when resolving authentication failures.

## Enable Teams

Teams mode supports **group-chat @mentions only**, not channels or personal
chat history. The CLI remains available with its existing authentication.
The hosted service does not use `GRAPH_CLIENT_ID`, device-code login, delegated
user tokens, or tenant-wide `Chat.Read.All` application access.

### Register the Bot

1. Create a separate, single-tenant Microsoft Entra app registration for the bot
  in `AZURE_TENANT_ID`, then create its client secret. Do not reuse the A365
  telemetry service principal or the CLI public-client registration.
2. Create an **Azure Bot** resource using that existing app registration, with
  single-tenant identity and the same tenant ID. Enable its **Microsoft Teams**
  channel. The Azure Bot registration is required even when hosting in Kubernetes.
3. Set its messaging endpoint to your publicly reachable HTTPS address:
  `https://agent.example.com/api/messages`. For local development, use an
  organization-approved HTTPS development tunnel to local port 3978.
4. Keep the existing OpenAI and A365 telemetry settings in `.env`. Add:

  ```dotenv
  TEAMS_BOT_CLIENT_ID=<bot-app-client-id>
  TEAMS_BOT_CLIENT_SECRET=<bot-app-secret>
  TEAMS_MAX_MESSAGES=100
  PORT=3978
  ```

  The bot and telemetry identities must belong to the same configured tenant.
  Message limits accept 1 through 200. Bot replies authenticate through the
  Agents SDK/MSAL; Graph uses that bot app's client credentials with
  `https://graph.microsoft.com/.default`. `A365_AGENT_ID` remains the separately
  provisioned observability agent ID, not the bot client ID.

### Build and Install the Teams App

[teams/manifest.json](teams/manifest.json) requests **application** RSC
`ChatMessage.Read.Chat` and declares only the `groupChat` bot scope. Do not add
tenant-wide Graph permissions in Entra to make this work. Teams grants the RSC
permission when an authorized person installs and consents to the app in the
specific chat, subject to tenant policy. Installing it somewhere else does not
authorize the target chat.

From this sample directory, with dependencies installed:

```powershell
python build_teams_package.py --bot-id "<bot-app-client-id>" `
  --website "https://your-organization.example" `
  --privacy-url "https://your-organization.example/privacy" `
  --terms-url "https://your-organization.example/terms"
```

Replace the example addresses with real, reachable pages describing this app's
data processing. Update the developer name/description in the manifest for your
organization before distribution. The builder validates GUIDs and HTTPS URL
syntax and generates `teams-app.zip` containing a concrete manifest, a 192x192
color icon, and a 32x32 transparent outline icon. No credentials are packaged.
The Teams app ID defaults to the bot client ID; use `--app-id` to provide a
different stable GUID. Preserve it and increment the manifest version for updates.

Start the service:

```powershell
python teams_app.py
```

The service listens on `http://localhost:3978`. `GET /healthz` is a public
process-health endpoint; `POST /api/messages` requires a valid bot-channel JWT.
There is no anonymous development bypass. Playground-only testing does not
verify real Teams authentication or RSC consent.

Upload `teams-app.zip` through Teams' custom-app upload flow or publish it through
your organization's app catalog. Your administrator may need to enable custom
app upload and chat RSC consent. Add the app to the intended **group chat** and
accept its chat-read permission. Then select it from the @mention picker:

```text
@Chat Summary Assistant summarize this chat
```

The commands `summarize`, `summary`, and `summarize this conversation` are also
accepted after the mention. The app acknowledges processing and posts a bounded
summary to that same chat. All chat members can see the reply. With RSC, Teams
may deliver unmentioned messages too; this service ignores them without querying
Graph or calling the model. Consent permits reading chat history, not just
messages received after installation. Reinstall/reconsent after changing RSC
permissions. A 403 from Graph is a consent/policy/configuration problem, not a
reason to add broader permissions automatically.

### Container and Kubernetes

The [Dockerfile](Dockerfile) runs the Teams service as a non-root user and does
not copy `.env` or credentials into the image. From this directory:

```powershell
docker build -t YOUR_REGISTRY/teams-chat-agent:1.0 .
docker push YOUR_REGISTRY/teams-chat-agent:1.0
```

Scan the built image with your organization's vulnerability tooling and use an
approved, patched base image before production. The editor currently flags high
severity findings in the selected `python:3.13-slim` base; a successful build
does not establish that the image meets your security policy.

[kubernetes.yaml](kubernetes.yaml) includes a single-replica Deployment, Service,
and TLS Ingress template. Before applying it:

1. Replace the image, ingress class, hostname, and TLS secret with your values.
  Install/configure an ingress controller and DNS. Provision a valid TLS certificate.
2. Provision a Kubernetes Secret named `teams-chat-agent-settings` in the same
  namespace through your approved secret-management process. Its keys are
  `OPENAI_API_KEY`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`,
  `A365_AGENT_ID`, `TEAMS_BOT_CLIENT_ID`, and `TEAMS_BOT_CLIENT_SECRET`, plus any
  optional settings. Keep `PORT=3978` to match this template. No secret values
  belong in the YAML, shell history, app package, or container image. Prefer
  your cluster's external secret store integration for provisioning/rotation.
3. Apply with `kubectl apply -f kubernetes.yaml`. Set the Azure Bot messaging
  endpoint to the resulting public `https://<hostname>/api/messages` address.
  The cluster may be private internally, but bot-channel delivery must reach
  that endpoint. The template exposes only `/api/messages` through ingress;
  probes access `/healthz` internally.
4. Allow outbound HTTPS to Microsoft identity, bot-channel reply services,
  Graph, OpenAI, and the configured A365 telemetry service.

This is a **lab service**, not a durable queue implementation. It acknowledges
inbound turns before background processing and uses the SDK's authenticated
conversation continuation for replies. Tasks remain in the receiving pod and
shutdown waits up to 30 seconds before cancellation. A restart can lose an
accepted request; delivery retries can produce duplicates. There is no durable
deduplication, rate limiting, or concurrency cap. MemoryStorage holds only SDK
turn state, not a durable conversation history or shared user token cache.
Before production or autoscaling, add a durable work queue, idempotency, bounded
workers, and appropriate shared state. Workload Identity is not configured by
this example; replacing client secrets requires configuring supported identity
authentication for both SDK replies and Graph, not just assigning a pod identity.

Reference: [Agents SDK](https://learn.microsoft.com/en-us/microsoft-365/agents-sdk/quickstart)
and [Teams RSC](https://learn.microsoft.com/en-us/microsoftteams/platform/graph-api/rsc/resource-specific-consent).

## Project Files

| File | Responsibility |
| --- | --- |
| [app.py](app.py) | CLI, delegated sign-in, agent instructions, bound tool, and A365-instrumented execution. |
| [graph_chat.py](graph_chat.py) | Read-only Graph requests, pagination, HTML conversion, and content limits. |
| [a365_bootstrap.py](a365_bootstrap.py) | Observability configuration and service-principal token resolution. |
| [requirements.txt](requirements.txt) | OpenAI Agents SDK, A365, Azure Identity, HTTP, and environment-loader dependencies. |
| [.env.example](.env.example) | Configuration template without credentials. |
| [test_graph_chat.py](test_graph_chat.py) | Offline Graph reader tests. |
| [test_app.py](test_app.py) | Offline agent wiring, tool binding, and authentication-boundary tests. |
| [teams_app.py](teams_app.py) | JWT-authenticated Teams service, @mention handling, chat-scoped Graph access, and background replies. |
| [teams/manifest.json](teams/manifest.json) | Group-chat bot manifest template requesting chat-specific consent. |
| [build_teams_package.py](build_teams_package.py) | Builds a credential-free uploadable Teams ZIP and PNG icons. |
| [Dockerfile](Dockerfile) | Non-root Teams service image. |
| [kubernetes.yaml](kubernetes.yaml) | Deployment, Service, and TLS Ingress template without secret values. |

## Tests

From this directory, with the dependencies installed:

```powershell
python -m unittest discover -v
```

Tests mock HTTP responses, authentication, and the model runner. They cover
pagination, ordering, HTML parsing, truncation, token safety, Graph failures,
tool binding, sensitive trace settings, Teams mentions/tenant/scope boundaries,
background replies, HTTP authentication routing, and Teams package contents
without contacting Microsoft or OpenAI. A real tenant run is still required to
verify bot-channel JWTs, reply delivery, per-chat RSC consent, A365 export,
tenant policy, and generated summary quality. After deployment, verify that a
valid @mention works, an unmentioned message causes no model call, another chat
cannot be selected in the prompt, and unsigned endpoint requests return 401.

## References

- [Graph: list chat messages](https://learn.microsoft.com/en-us/graph/api/chat-list-messages?view=graph-rest-1.0)
- [Graph: list chats](https://learn.microsoft.com/en-us/graph/api/chat-list?view=graph-rest-1.0)
- [Azure Identity: DeviceCodeCredential](https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.devicecodecredential?view=azure-python)