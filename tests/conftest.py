"""In-process fake A2A agent. Tests never touch the network (CLAUDE.md rule);
every HTTP request in the suite lands on this server on 127.0.0.1."""

from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import pytest

METHOD_NOT_FOUND = -32601


def make_valid_card(base_url: str) -> dict[str, Any]:
    return {
        "name": "Fixture Agent",
        "description": "In-process fake agent for a2a-scorecard tests.",
        "version": "1.0.0",
        "capabilities": {},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [
            {
                "id": "echo",
                "name": "Echo",
                "description": "Echoes a short reply.",
            }
        ],
        "supportedInterfaces": [
            {"url": base_url, "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
        ],
    }


class FakeAgentHandler(BaseHTTPRequestHandler):
    # Modes: compliant, no-card, bad-json, invalid-card, card-only, grpc-only,
    # legacy-location, v0-card, no-skills, no-interface, auth-gated,
    # wrong-error-code, no-error-on-unknown.
    mode = "compliant"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass

    def _base_url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path in ("/.well-known/agent-card.json", "/.well-known/agent.json"):
            if self.mode == "no-card":
                self._send(404, b"not found", "text/plain")
            elif self.mode == "bad-json":
                self._send(200, b"{not json", "application/json")
            elif self.mode == "invalid-card":
                card = make_valid_card(self._base_url())
                card["skills"] = "oops"
                self._send(200, json.dumps(card).encode())
            elif self.mode == "grpc-only":
                card = make_valid_card(self._base_url())
                # Spec-legal: gRPC-only agent, no JSON-RPC interface. The URL
                # is never contacted because the JSON-RPC probes must SKIP.
                card["supportedInterfaces"] = [
                    {"url": "grpc.example.invalid:443", "protocolBinding": "GRPC"}
                ]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "legacy-location":
                # Card served only at the pre-v0.3.0 well-known path.
                if self.path == "/.well-known/agent-card.json":
                    self._send(404, b"not found", "text/plain")
                else:
                    self._send(200, json.dumps(make_valid_card(self._base_url())).encode())
            elif self.mode == "v0-card":
                # Legacy-generation card: "url" + "protocolVersion", no
                # "supportedInterfaces" (ADR-0005 generation detection).
                card = {
                    "name": "Fixture Agent v0",
                    "description": "Legacy-generation fixture card.",
                    "version": "0.9.0",
                    "url": self._base_url(),
                    "protocolVersion": "0.3",
                    "skills": [
                        {"id": "echo", "name": "Echo", "description": "Echoes a short reply."}
                    ],
                }
                self._send(200, json.dumps(card).encode())
            elif self.mode == "no-skills":
                card = make_valid_card(self._base_url())
                card["skills"] = []
                self._send(200, json.dumps(card).encode())
            elif self.mode == "no-interface":
                card = make_valid_card(self._base_url())
                del card["supportedInterfaces"]
                self._send(200, json.dumps(card).encode())
            else:
                self._send(200, json.dumps(make_valid_card(self._base_url())).encode())
        else:
            self._send(200, b"ok", "text/plain")

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if self.mode == "card-only":
            self._send(404, b"not found", "text/plain")
            return
        if self.mode == "auth-gated":
            # Auth-gated endpoint: refuses before any JSON-RPC body is read.
            self._send(401, b'{"error": "unauthorized"}')
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            req = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send(400, b"bad request", "text/plain")
            return
        rpc_id = req.get("id")
        method = req.get("method")
        result = {
            "message": {
                "messageId": "fixture-reply-1",
                "role": "ROLE_AGENT",
                "parts": [{"text": "pong"}],
            }
        }
        if method in ("SendMessage", "message/send"):
            body = {"jsonrpc": "2.0", "id": rpc_id, "result": result}
        elif self.mode == "no-error-on-unknown":
            # Misbehaving agent: answers even an unknown method with success.
            body = {"jsonrpc": "2.0", "id": rpc_id, "result": result}
        elif self.mode == "wrong-error-code":
            # Misbehaving agent: rejects the unknown method with the wrong code.
            body = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32602, "message": "Invalid params"},
            }
        else:
            body = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": METHOD_NOT_FOUND, "message": "Method not found"},
            }
        self._send(200, json.dumps(body).encode())


@pytest.fixture
def fake_agent() -> Any:
    servers: list[ThreadingHTTPServer] = []

    def make(mode: str = "compliant") -> str:
        handler = type("Handler", (FakeAgentHandler,), {"mode": mode})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield make
    for server in servers:
        server.shutdown()
        server.server_close()


FakeAgentFactory = Callable[[str], str]
