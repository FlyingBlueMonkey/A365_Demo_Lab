import unittest

import httpx

from graph_chat import GRAPH_ROOT, GraphChatReader, message_text


def chat_message(message_id: str, **changes) -> dict:
    message = {
        "id": message_id,
        "messageType": "message",
        "createdDateTime": f"2026-10-{message_id.zfill(2)}T12:00:00Z",
        "from": {"user": {"displayName": "Alex"}},
        "body": {"contentType": "html", "content": "<p>Hello &amp; welcome</p>"},
    }
    message.update(changes)
    return message


class GraphChatReaderTests(unittest.TestCase):
    def reader(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return GraphChatReader(client, lambda: "test-token")

    def test_pagination_and_chronological_order(self):
        requests = []

        def handler(request):
            requests.append(request)
            self.assertEqual(request.headers["Authorization"], "Bearer test-token")
            if len(requests) == 1:
                return httpx.Response(200, json={
                    "value": [chat_message("3"), chat_message("2")],
                    "@odata.nextLink": f"{GRAPH_ROOT}/chats/test/messages?$skiptoken=next",
                })
            return httpx.Response(200, json={"value": [chat_message("1")]})

        result = self.reader(handler).read_messages("19:chat/test@thread.v2")
        self.assertEqual([message["id"] for message in result["messages"]], ["1", "2", "3"])
        self.assertEqual(result["messages"][0]["text"], "Hello & welcome")
        self.assertIn("19%3Achat%2Ftest%40thread.v2", str(requests[0].url))
        self.assertFalse(result["has_older_messages"])

    def test_limit_marks_partial_page(self):
        reader = self.reader(lambda request: httpx.Response(200, json={
            "value": [chat_message("3"), chat_message("2"), chat_message("1")],
        }))
        result = reader.read_messages("test", limit=2)
        self.assertEqual(result["retrieved_count"], 2)
        self.assertTrue(result["has_older_messages"])

    def test_unsafe_next_link_never_receives_token(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={
                "value": [chat_message("1")],
                "@odata.nextLink": "https://example.com/steal",
            })

        with self.assertRaises(ValueError):
            self.reader(handler).read_messages("test")
        self.assertEqual(len(calls), 1)

    def test_deleted_system_empty_and_null_sender(self):
        reader = self.reader(lambda request: httpx.Response(200, json={"value": [
            chat_message("4", deletedDateTime="2026-10-04T12:00:00Z"),
            chat_message("3", messageType="systemEventMessage"),
            chat_message("2", body={"content": ""}),
            chat_message("1", **{"from": None}),
        ]}))
        result = reader.read_messages("test")
        self.assertEqual(len(result["messages"]), 1)
        self.assertEqual(result["messages"][0]["sender"], "Unknown sender")

    def test_text_budget(self):
        reader = self.reader(lambda request: httpx.Response(200, json={"value": [
            chat_message(str(number), body={"content": "x" * 5000})
            for number in range(20, 0, -1)
        ]}))
        result = reader.read_messages("test")
        self.assertLessEqual(sum(len(message["text"]) for message in result["messages"]), 60000)
        self.assertTrue(result["text_truncated"])

    def test_html_and_plain_text(self):
        self.assertEqual(message_text({"contentType": "html", "content":
            "<div>First<br>Second<script>secret()</script></div>"}), "First\nSecond")
        self.assertEqual(message_text({"contentType": "text", "content": "a < b"}), "a < b")

    def test_graph_error_does_not_return_response_body(self):
        reader = self.reader(lambda request: httpx.Response(403, text="private details"))
        with self.assertRaisesRegex(RuntimeError, "HTTP 403") as context:
            reader.read_messages("test")
        self.assertNotIn("private details", str(context.exception))

    def test_chat_listing(self):
        reader = self.reader(lambda request: httpx.Response(200, json={
            "value": [{"id": "chat", "topic": "Planning", "private": "not returned"}],
        }))
        result = reader.list_chats()
        self.assertEqual(result["chats"][0]["topic"], "Planning")
        self.assertNotIn("private", result["chats"][0])

    def test_invalid_limits_do_not_call_graph(self):
        def handler(request):
            self.fail("Invalid input must not reach Graph")

        reader = self.reader(handler)
        for limit in (0, 201):
            with self.assertRaises(ValueError):
                reader.read_messages("test", limit)
        with self.assertRaises(ValueError):
            reader.read_messages(" ")


if __name__ == "__main__":
    unittest.main()