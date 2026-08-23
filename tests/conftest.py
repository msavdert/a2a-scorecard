"""In-process fake A2A agent. Tests never touch the network (CLAUDE.md rule);
every HTTP request in the suite lands on this server on 127.0.0.1."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import pytest

METHOD_NOT_FOUND = -32601


def _b64url(obj: dict[str, Any]) -> str:
    raw = json.dumps(obj).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


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


def make_rest_only_card(base_url: str) -> dict[str, Any]:
    """Card declaring only an HTTP+JSON interface (C023 fixtures, ADR-0014):
    no JSONRPC entry at all, so C020 SKIPs via its existing
    non-JSONRPC-SKIP branch and C023's ping-budget SKIP does not fire."""
    card = make_valid_card(base_url)
    card["supportedInterfaces"] = [
        {"url": base_url, "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"}
    ]
    return card


class FakeAgentHandler(BaseHTTPRequestHandler):
    # Modes: compliant, no-card, bad-json, invalid-card, card-only, grpc-only,
    # legacy-location, v0-card, version-silent-card, v1-card-with-legacy-fields,
    # no-generation-signal-card, no-skills, no-interface, auth-gated,
    # wrong-error-code, no-error-on-unknown, security-coherent,
    # security-dangling-ref, security-plain-http, security-malformed,
    # security-schemes-not-object, v0-card-with-security, signed-well-formed,
    # signed-alg-none, signed-undecodable-protected, signed-symmetric-alg,
    # signed-missing-key-hint, signed-not-a-list, streaming, streaming-unary,
    # streaming-rejected, streaming-stalls, streaming-garbled,
    # streaming-trickle, streaming-multiline, streaming-no-newline,
    # streaming-oversized, legacy-streaming-drift, rest-only-ok,
    # rest-only-drift, rest-only-rejected, rest-only-auth-gated.
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
            elif self.mode == "version-silent-card":
                # ADR-0016 regression fixture (a): a real-world shape the
                # 2026-08-22 census proved exists - top-level "url" and no
                # version signal at all, neither "protocolVersion" nor
                # "preferredTransport". Must still detect v0.x from the
                # "url" signal alone, and C012 must SKIP rather than fail
                # this card against the v1 schema.
                card = {
                    "name": "Fixture Agent version-silent",
                    "description": "Version-silent legacy-generation fixture card.",
                    "version": "0.9.0",
                    "url": self._base_url(),
                    "skills": [
                        {"id": "echo", "name": "Echo", "description": "Echoes a short reply."}
                    ],
                }
                self._send(200, json.dumps(card).encode())
            elif self.mode == "v1-card-with-legacy-fields":
                # ADR-0016 regression fixture (c): a card carrying BOTH the
                # v1 "supportedInterfaces" signal and legacy "url" /
                # "protocolVersion" fields. The v1 signal wins (decision 2)
                # so this must detect v1 and C012 must still FAIL: the v1
                # schema sets additionalProperties:false, so the legacy
                # top-level fields are genuine violations. This guards
                # against "fixing" the v0.x/undetermined SKIP too broadly.
                card = make_valid_card(self._base_url())
                card["url"] = self._base_url()
                card["protocolVersion"] = "0.3"
                self._send(200, json.dumps(card).encode())
            elif self.mode == "no-generation-signal-card":
                # ADR-0016 regression fixture (d): neither a v1 signal
                # (supportedInterfaces) nor any v0.x signal (url,
                # preferredTransport, additionalInterfaces, protocolVersion,
                # supportsExtendedAgentCard) is present. Generation is
                # genuinely undetermined and C012 must SKIP.
                card = {
                    "name": "Fixture Agent no-generation-signal",
                    "description": "Card with no structural generation signal.",
                    "version": "0.9.0",
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
            elif self.mode == "security-coherent":
                card = make_valid_card(self._base_url())
                card["securitySchemes"] = {
                    "bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}},
                    "google": {
                        "openIdConnectSecurityScheme": {
                            "openIdConnectUrl": (
                                "https://accounts.example.com/.well-known/openid-configuration"
                            )
                        }
                    },
                }
                card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}}]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "security-dangling-ref":
                card = make_valid_card(self._base_url())
                card["securitySchemes"] = {
                    "bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}},
                }
                card["securityRequirements"] = [{"schemes": {"ghost": {"list": []}}}]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "security-plain-http":
                card = make_valid_card(self._base_url())
                card["securitySchemes"] = {
                    "oauth2": {
                        "oauth2SecurityScheme": {
                            "flows": {
                                "authorizationCode": {
                                    "authorizationUrl": "http://auth.example.com/authorize",
                                    "tokenUrl": "https://auth.example.com/token",
                                }
                            }
                        }
                    },
                }
                card["securityRequirements"] = [{"schemes": {"oauth2": {"list": []}}}]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "security-malformed":
                card = make_valid_card(self._base_url())
                card["securitySchemes"] = {
                    "apikey": {"apiKeySecurityScheme": {"description": "no name or location"}},
                }
                card["securityRequirements"] = [{"schemes": {"apikey": {"list": []}}}]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "security-schemes-not-object":
                # Malformed card: securitySchemes is a list, not an object.
                card = make_valid_card(self._base_url())
                card["securitySchemes"] = ["bearer"]
                card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}}]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "v0-card-with-security":
                # Legacy-generation card that also declares a security scheme,
                # isolating the v1-only SKIP from the no-declaration SKIP.
                card = {
                    "name": "Fixture Agent v0",
                    "description": "Legacy-generation fixture card.",
                    "version": "0.9.0",
                    "url": self._base_url(),
                    "protocolVersion": "0.3",
                    "skills": [
                        {"id": "echo", "name": "Echo", "description": "Echoes a short reply."}
                    ],
                    "securitySchemes": {
                        "bearer": {"httpAuthSecurityScheme": {"scheme": "Bearer"}},
                    },
                    "securityRequirements": [{"schemes": {"bearer": {"list": []}}}],
                }
                self._send(200, json.dumps(card).encode())
            elif self.mode == "signed-well-formed":
                card = make_valid_card(self._base_url())
                card["signatures"] = [
                    {
                        "protected": _b64url({"alg": "ES256", "kid": "key-1"}),
                        "signature": base64.urlsafe_b64encode(b"fake-signature-bytes")
                        .decode()
                        .rstrip("="),
                    }
                ]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "signed-alg-none":
                card = make_valid_card(self._base_url())
                card["signatures"] = [
                    {
                        "protected": _b64url({"alg": "none"}),
                        "signature": base64.urlsafe_b64encode(b"fake-signature-bytes")
                        .decode()
                        .rstrip("="),
                    }
                ]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "signed-undecodable-protected":
                card = make_valid_card(self._base_url())
                card["signatures"] = [
                    {
                        "protected": "not!valid!base64url!",
                        "signature": base64.urlsafe_b64encode(b"fake-signature-bytes")
                        .decode()
                        .rstrip("="),
                    }
                ]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "signed-symmetric-alg":
                card = make_valid_card(self._base_url())
                card["signatures"] = [
                    {
                        "protected": _b64url({"alg": "HS256", "kid": "key-1"}),
                        "signature": base64.urlsafe_b64encode(b"fake-signature-bytes")
                        .decode()
                        .rstrip("="),
                    }
                ]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "signed-missing-key-hint":
                card = make_valid_card(self._base_url())
                card["signatures"] = [
                    {
                        "protected": _b64url({"alg": "ES256"}),
                        "signature": base64.urlsafe_b64encode(b"fake-signature-bytes")
                        .decode()
                        .rstrip("="),
                    }
                ]
                self._send(200, json.dumps(card).encode())
            elif self.mode == "signed-not-a-list":
                card = make_valid_card(self._base_url())
                card["signatures"] = "oops"
                self._send(200, json.dumps(card).encode())
            elif self.mode in (
                "streaming",
                "streaming-unary",
                "streaming-rejected",
                "streaming-stalls",
                "streaming-garbled",
                "streaming-trickle",
                "streaming-multiline",
                "streaming-no-newline",
                "streaming-oversized",
                "legacy-streaming-drift",
                "auth-gated",
            ):
                # auth-gated also declares streaming so C022's SKIP can be
                # attributed to ctx.auth_gated, not to a missing declaration
                # (tests/test_scan.py::test_auth_gated_endpoint_warns_ping).
                card = make_valid_card(self._base_url())
                card["capabilities"] = {"streaming": True}
                self._send(200, json.dumps(card).encode())
            elif self.mode in (
                "rest-only-ok",
                "rest-only-drift",
                "rest-only-rejected",
                "rest-only-auth-gated",
            ):
                self._send(200, json.dumps(make_rest_only_card(self._base_url())).encode())
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
        if self.path == "/message:send":
            self.server.message_send_request_count = (  # type: ignore[attr-defined]
                getattr(self.server, "message_send_request_count", 0) + 1
            )
            self._handle_rest_message_send()
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            req = json.loads(self.rfile.read(length))
        except json.JSONDecodeError:
            self._send(400, b"bad request", "text/plain")
            return
        rpc_id = req.get("id")
        method = req.get("method")
        if method == "SendStreamingMessage":
            self.server.streaming_request_count = (  # type: ignore[attr-defined]
                getattr(self.server, "streaming_request_count", 0) + 1
            )
            self._handle_streaming(rpc_id)
            return
        result = {
            "message": {
                "messageId": "fixture-reply-1",
                "role": "ROLE_AGENT",
                "parts": [{"text": "pong"}],
            }
        }
        if method == "SendMessage" and self.mode == "legacy-streaming-drift":
            # v1 method rejected so C020 falls through to its legacy
            # message/send retry (tests/test_scan.py::
            # test_legacy_drift_still_runs_streaming_probe).
            body = {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": METHOD_NOT_FOUND, "message": "Method not found"},
            }
        elif method in ("SendMessage", "message/send"):
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

    def _handle_rest_message_send(self) -> None:
        """POST /message:send responses, keyed by self.mode (ADR-0014, C023).

        rest-only-ok: happy path, a recognizable Task response body.
        rest-only-drift: HTTP 200 but a body not recognizable as a
        Message/Task. rest-only-rejected: a non-2xx status, exercising the
        FAIL-on-bad-status path. rest-only-auth-gated: 401, exercising the
        auth-gated WARN path.
        """
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)  # drain the request body
        if self.mode == "rest-only-auth-gated":
            self._send(401, b'{"error": "unauthorized"}')
        elif self.mode == "rest-only-drift":
            self._send(200, json.dumps({"unexpected": "shape"}).encode())
        elif self.mode == "rest-only-rejected":
            self._send(500, b"internal error", "text/plain")
        else:
            body = {
                "task": {
                    "id": "fixture-task-1",
                    "contextId": "fixture-context-1",
                    "status": {"state": "TASK_STATE_COMPLETED"},
                }
            }
            self._send(200, json.dumps(body).encode())

    def _handle_streaming(self, rpc_id: Any) -> None:
        """SendStreamingMessage responses, keyed by self.mode.

        streaming: happy path, one SSE data event carrying a valid JSON-RPC
        result. streaming-unary: drift - a plain 200 JSON reply, no SSE
        framing at all. streaming-rejected: SSE framing (not plain JSON) with
        a JSON-RPC method-not-found error as the first event - plain JSON
        would only exercise the unary-drift WARN path, not the
        rejected-error FAIL path, since the probe checks Content-Type before
        it looks at the body. streaming-stalls: valid SSE headers, then no
        data event ever, to exercise the timeout/FAIL path. streaming-garbled:
        valid SSE headers, one data event whose payload is not a JSON-RPC
        response object, to exercise the unparseable-first-event WARN path
        distinctly from the unary-drift WARN. streaming-trickle: never sends
        a data event, but writes an SSE comment line every 0.1s indefinitely
        (bounded so the daemonic thread can't outlive the suite) - a
        keepalive-style target that would defeat a naive per-read idle
        timeout, to exercise the absolute-deadline enforcement. streaming-
        multiline: one data event spread across several `data:` lines (a
        pretty-printed JSON body), to exercise multi-line SSE event
        reassembly. streaming-no-newline: drips a few bytes containing no
        line terminator at all every 0.1s, bounded to ~2s, to exercise the
        absolute-deadline check in the byte-oriented read loop even though no
        line (and so no event) ever completes. streaming-oversized: a single
        write, larger than the probe's size bound, containing no line
        terminator anywhere, to exercise the size-bound FAIL path.
        """
        if self.mode == "streaming-unary":
            result = {
                "message": {
                    "messageId": "fixture-reply-1",
                    "role": "ROLE_AGENT",
                    "parts": [{"text": "pong"}],
                }
            }
            body = {"jsonrpc": "2.0", "id": rpc_id, "result": result}
            self._send(200, json.dumps(body).encode())
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            if self.mode == "streaming-stalls":
                # Never write a data event; sleep in short increments so the
                # thread (daemonic under ThreadingHTTPServer) doesn't block
                # the rest of the suite even if the client disconnects first.
                for _ in range(15):
                    time.sleep(0.1)
                return
            if self.mode == "streaming-trickle":
                # Never write a data event either, but keep the connection
                # alive with SSE comment lines more often than the client's
                # deadline: a naive per-read idle timeout resets on each one
                # and never fires, so this only terminates promptly if the
                # client enforces an absolute wall-clock deadline. Bounded to
                # 2s so the daemonic thread can't outlive the suite even if
                # the client fails to disconnect.
                for _ in range(20):
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    time.sleep(0.1)
                return
            if self.mode == "streaming-no-newline":
                # No line terminator ever: a naive line-buffered reader
                # (e.g. httpx's iter_lines()) never hands control back to
                # the caller, so this only trips a client's deadline check
                # if that check runs per raw chunk. Bounded to ~2s so the
                # daemonic thread can't outlive the suite.
                for _ in range(20):
                    self.wfile.write(b"x" * 50)
                    self.wfile.flush()
                    time.sleep(0.1)
                return
            if self.mode == "streaming-oversized":
                # One write, no line terminator anywhere, bigger than the
                # probe's size bound: exercises the size-bound FAIL path
                # directly, independent of the deadline.
                self.wfile.write(b"x" * (128 * 1024))
                self.wfile.flush()
                return
            if self.mode == "streaming-multiline":
                payload = {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "statusUpdate": {
                            "taskId": "fixture-task-1",
                            "status": {"state": "TASK_STATE_COMPLETED"},
                        }
                    },
                }
                # Pretty-print so the event is legitimately spread across
                # several `data:` lines, each newline already a valid
                # whitespace boundary between JSON tokens.
                for line in json.dumps(payload, indent=2).split("\n"):
                    self.wfile.write(f"data: {line}\n".encode())
                self.wfile.write(b"\n")
                self.wfile.flush()
                return
            if self.mode == "streaming-rejected":
                payload: Any = {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": METHOD_NOT_FOUND, "message": "Method not found"},
                }
            elif self.mode == "streaming-garbled":
                # Not a JSON-RPC response object at all: no "jsonrpc" key.
                payload = {"unexpected": "shape"}
            else:
                payload = {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "statusUpdate": {
                            "taskId": "fixture-task-1",
                            "status": {"state": "TASK_STATE_COMPLETED"},
                        }
                    },
                }
            self.wfile.write(f"data: {json.dumps(payload)}\n\n".encode())
            self.wfile.flush()
        except OSError:
            # Client closed the connection first (e.g. after its own
            # timeout); nothing left to do.
            pass


@pytest.fixture
def fake_agent() -> Any:
    servers: list[ThreadingHTTPServer] = []
    by_url: dict[str, ThreadingHTTPServer] = {}

    def make(mode: str = "compliant") -> str:
        handler = type("Handler", (FakeAgentHandler,), {"mode": mode})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        server.streaming_request_count = 0  # type: ignore[attr-defined]
        server.message_send_request_count = 0  # type: ignore[attr-defined]
        Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        by_url[url] = server
        return url

    def streaming_request_count(url: str) -> int:
        """Number of SendStreamingMessage requests the server at `url` saw."""
        return int(by_url[url].streaming_request_count)  # type: ignore[attr-defined]

    def message_send_request_count(url: str) -> int:
        """Number of POST /message:send requests the server at `url` saw."""
        return int(by_url[url].message_send_request_count)  # type: ignore[attr-defined]

    make.streaming_request_count = streaming_request_count  # type: ignore[attr-defined]
    make.message_send_request_count = message_send_request_count  # type: ignore[attr-defined]
    yield make
    for server in servers:
        server.shutdown()
        server.server_close()


FakeAgentFactory = Callable[[str], str]
