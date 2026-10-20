from collections.abc import Callable
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

import httpx

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"


class _MessageText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style"}:
            self.hidden_depth += 1
        if tag in {"br", "p", "div", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.hidden_depth:
            self.hidden_depth -= 1
        if tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def message_text(body: dict) -> str:
    content = body.get("content") or ""
    if body.get("contentType") != "html":
        return content.strip()
    parser = _MessageText()
    parser.feed(content)
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


class GraphChatReader:
    def __init__(self, client: httpx.Client, token_provider: Callable[[], str]) -> None:
        self.client = client
        self.token_provider = token_provider

    def _get(self, url: str) -> dict:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "graph.microsoft.com"
            or not parsed.path.startswith("/v1.0/")
        ):
            raise ValueError("Refusing a continuation URL outside Microsoft Graph v1.0")
        response = self.client.get(
            url,
            headers={"Authorization": f"Bearer {self.token_provider()}"},
            follow_redirects=False,
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Microsoft Graph returned HTTP {response.status_code}. "
                "Check Chat.Read consent, chat membership, and tenant policy. "
                "For HTTP 429, wait for Retry-After before rerunning."
            )
        return response.json()

    def _collect(self, url: str, limit: int) -> tuple[list[dict], bool]:
        items: list[dict] = []
        visited: set[str] = set()
        while url and len(items) < limit:
            if url in visited or len(visited) >= 100:
                raise RuntimeError("Microsoft Graph pagination did not complete safely")
            visited.add(url)
            page = self._get(url)
            values = page["value"]
            available = limit - len(items)
            items.extend(values[:available])
            url = page.get("@odata.nextLink") or ""
            if len(items) == limit:
                return items, bool(url) or len(values) > available
        return items, False

    def list_chats(self, limit: int = 50) -> dict:
        if not 1 <= limit <= 200:
            raise ValueError("Chat limit must be between 1 and 200")
        chats, has_more = self._collect(f"{GRAPH_ROOT}/me/chats?$top=50", limit)
        return {
            "chats": [
                {key: chat.get(key) for key in ("id", "topic", "chatType", "webUrl")}
                for chat in chats
            ],
            "has_more": has_more,
        }

    def read_messages(self, chat_id: str, limit: int = 100) -> dict:
        if not chat_id.strip():
            raise ValueError("A nonempty chat ID is required")
        if not 1 <= limit <= 200:
            raise ValueError("Message limit must be between 1 and 200")
        url = (
            f"{GRAPH_ROOT}/chats/{quote(chat_id, safe='')}/messages"
            "?$top=50&$orderby=createdDateTime%20desc"
        )
        raw_messages, has_more = self._collect(url, limit)
        messages = []
        remaining = 60000
        text_truncated = False
        for message in raw_messages:
            if message.get("deletedDateTime") or message.get("messageType") != "message":
                continue
            text = message_text(message.get("body") or {})
            if not text:
                continue
            if remaining == 0:
                text_truncated = True
                break
            excerpt = text[: min(4000, remaining)]
            text_truncated |= len(excerpt) < len(text)
            remaining -= len(excerpt)
            sender = message.get("from") or {}
            identity = sender.get("user") or sender.get("application") or {}
            messages.append({
                "id": message.get("id"),
                "created_at": message.get("createdDateTime"),
                "sender": identity.get("displayName") or "Unknown sender",
                "text": excerpt,
                "web_url": message.get("webUrl"),
            })
        messages.sort(key=lambda message: message["created_at"] or "")
        return {
            "chat_id": chat_id,
            "messages": messages,
            "retrieved_count": len(raw_messages),
            "has_older_messages": has_more,
            "text_truncated": text_truncated,
            "scope": "Recent message bodies only; attachments and images are not downloaded.",
        }