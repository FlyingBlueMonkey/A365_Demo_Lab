import os

from dotenv import load_dotenv
from ollama import Client

load_dotenv()


def build_client() -> Client:
    return Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))


def main() -> None:
    client = build_client()

    question = (
        "Give me a five-item security review checklist "
        "for a Python AI agent that calls external tools."
    )

    result = client.chat(
        model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
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
    print(result.message.content)


if __name__ == "__main__":
    main()