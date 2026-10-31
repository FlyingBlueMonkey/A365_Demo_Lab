# Python Ollama Agent

This project copies the [Python OpenAI agent](../python-openai-agent/readme.md)
security instructions and fixed five-item checklist request, replacing the
OpenAI Agents SDK with Ollama's native Python client. It prints the model's
response to the terminal. It does not register or call external tools.

The assistant is instructed to provide concise, technically precise guidance,
separate verified facts from suggestions, and avoid revealing credentials,
tokens, secrets, or hidden configuration. Instructions are not a security
boundary; treat the generated checklist as untrusted model output.

## Requirements

- Python 3.10 or newer is recommended for this lab.
- [Ollama](https://ollama.com/download/windows) installed and running.
- Enough disk space and memory for the selected model.
- PowerShell on Windows, or an equivalent shell on another platform.

The default uses a local model. No OpenAI API key, Azure credentials, or A365
CLI is required. For Agent 365 onboarding instructions, see the
[lab README](../readme.md#enable-and-set-up-the-a365-cli). The existing
[A365-integrated sample](../a365-python-openai-agent/readme.md) still uses OpenAI;
this project does not export Agent 365 telemetry.
The documentation-only [Ollama A365 guide](../a365-python-ollama-agent/readme.MD)
describes adding the supported Microsoft OpenTelemetry distribution with manual
agent and inference spans. Those changes have not been applied to this sample.

## Setup

1. Install Ollama, launch the Windows application, and reopen PowerShell.
   Verify the command and download the default model:

   ```powershell
   ollama --version
   ollama pull llama3.2:3b
   ollama list
   ```

2. Keep Ollama running. The Windows application normally starts the server.
   If it is not running, start it in a separate terminal and leave it open:

   ```powershell
   ollama serve
   ```

   Do not start a second server if one is already listening on port 11434.

3. From this project directory, create an environment and install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

4. Optionally select a different downloaded model or server in this session:

   ```powershell
   $env:OLLAMA_MODEL = "llama3.2:3b"
   $env:OLLAMA_HOST = "http://localhost:11434"
   ```

   Or create a private `.env` in this directory:

   ```dotenv
   OLLAMA_MODEL=llama3.2:3b
   OLLAMA_HOST=http://localhost:11434
   ```

   Both values are optional and default to those shown. Pull a replacement
   model before selecting it. Session environment variables take precedence
   over `.env` values. Keep private configuration out of source control.

5. Run the sample:

   ```powershell
   python app.py
   ```

   Without activating the virtual environment, run:

   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```

The application waits for the complete response, then prints the checklist.
The first request can take longer while Ollama loads the model into memory.

## Troubleshooting

- **Command not found:** finish installing Ollama and reopen your terminal.
- **Connection refused:** launch Ollama or run `ollama serve`, and confirm
  `OLLAMA_HOST` points to the running server.
- **Model not found:** run `ollama pull` with the exact `OLLAMA_MODEL` name.
- **Insufficient memory or slow responses:** choose and pull a smaller model
  appropriate for your hardware.
- **Dependency import errors:** install [requirements.txt](requirements.txt)
  using the same Python environment that runs [app.py](app.py).

Use a local, non-cloud model for local-only inference. Changing `OLLAMA_HOST`
to a remote server, or selecting a cloud model, can send prompts off the
machine. Do not expose the default unauthenticated Ollama service to untrusted
networks; remote hosting needs its own authentication and transport protection.

## Project Files

- [app.py](app.py) creates the client, sends system and user messages, and prints the response.
- [requirements.txt](requirements.txt) lists `ollama` and `python-dotenv`.
- [.gitignore](.gitignore) excludes virtual environments, Python caches, and private configuration.

## Extending the Demo

If adding tools, validate inputs, restrict permissions, and make side effects
explicit. The OpenAI SDK's tool runner is not present here; tool execution
would need to be implemented using an appropriate Ollama-compatible framework
or client workflow.