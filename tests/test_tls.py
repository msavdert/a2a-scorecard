"""Unit tests for C032 (ADR-0010): the TLS handshake probe is monkeypatched
here so these tests never touch the network. `TlsPosture.run` reads only
`ctx.base_url` and calls the module-level `_tls_handshake`, so it can be
exercised directly against a hand-built `ProbeContext` the same way
test_signature.py exercises C031."""

from __future__ import annotations

import httpx

from a2a_scorecard.checks import tls as tls_module
from a2a_scorecard.checks.base import ProbeContext
from a2a_scorecard.checks.tls import TlsHandshakeResult, TlsPosture
from a2a_scorecard.config import Settings
from a2a_scorecard.models import CheckStatus


def _ctx(base_url: str) -> ProbeContext:
    return ProbeContext(base_url, httpx.Client(), Settings(allow_http=True))


def test_plain_http_skips(monkeypatch) -> None:
    calls: list[tuple[str, int, float]] = []

    def _fake_handshake(host: str, port: int, timeout_s: float) -> TlsHandshakeResult:
        calls.append((host, port, timeout_s))
        raise AssertionError("must not be called for a plain-http target")

    monkeypatch.setattr(tls_module, "_tls_handshake", _fake_handshake)
    ctx = _ctx("http://example.invalid")
    result = TlsPosture().run(ctx)
    assert result.status is CheckStatus.SKIP
    assert not calls


def test_handshake_failure_fails(monkeypatch) -> None:
    def _fake_handshake(host: str, port: int, timeout_s: float) -> TlsHandshakeResult:
        return TlsHandshakeResult(
            version=None,
            cipher=None,
            days_to_expiry=None,
            error="[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
        )

    monkeypatch.setattr(tls_module, "_tls_handshake", _fake_handshake)
    ctx = _ctx("https://example.invalid")
    result = TlsPosture().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "CERTIFICATE_VERIFY_FAILED" in result.evidence
    assert result.details["version"] is None


def test_version_below_tls12_fails(monkeypatch) -> None:
    def _fake_handshake(host: str, port: int, timeout_s: float) -> TlsHandshakeResult:
        return TlsHandshakeResult(
            version="TLSv1.1", cipher="ECDHE-RSA-AES128-SHA", days_to_expiry=90
        )

    monkeypatch.setattr(tls_module, "_tls_handshake", _fake_handshake)
    ctx = _ctx("https://example.invalid")
    result = TlsPosture().run(ctx)
    assert result.status is CheckStatus.FAIL
    assert "below TLS 1.2" in result.evidence
    assert result.details["version"] == "TLSv1.1"


def test_expiring_certificate_warns(monkeypatch) -> None:
    def _fake_handshake(host: str, port: int, timeout_s: float) -> TlsHandshakeResult:
        return TlsHandshakeResult(
            version="TLSv1.3", cipher="TLS_AES_256_GCM_SHA384", days_to_expiry=7
        )

    monkeypatch.setattr(tls_module, "_tls_handshake", _fake_handshake)
    ctx = _ctx("https://example.invalid")
    result = TlsPosture().run(ctx)
    assert result.status is CheckStatus.WARN
    assert "7 day" in result.evidence


def test_expiring_certificate_at_threshold_warns(monkeypatch) -> None:
    def _fake_handshake(host: str, port: int, timeout_s: float) -> TlsHandshakeResult:
        return TlsHandshakeResult(
            version="TLSv1.3", cipher="TLS_AES_256_GCM_SHA384", days_to_expiry=14
        )

    monkeypatch.setattr(tls_module, "_tls_handshake", _fake_handshake)
    ctx = _ctx("https://example.invalid")
    result = TlsPosture().run(ctx)
    assert result.status is CheckStatus.WARN


def test_healthy_certificate_passes(monkeypatch) -> None:
    def _fake_handshake(host: str, port: int, timeout_s: float) -> TlsHandshakeResult:
        return TlsHandshakeResult(
            version="TLSv1.3", cipher="TLS_AES_256_GCM_SHA384", days_to_expiry=90
        )

    monkeypatch.setattr(tls_module, "_tls_handshake", _fake_handshake)
    ctx = _ctx("https://example.invalid")
    result = TlsPosture().run(ctx)
    assert result.status is CheckStatus.PASS
    assert result.details == {
        "version": "TLSv1.3",
        "cipher": "TLS_AES_256_GCM_SHA384",
        "days_to_expiry": 90,
    }


def test_probe_called_at_most_once(monkeypatch) -> None:
    calls: list[tuple[str, int, float]] = []

    def _fake_handshake(host: str, port: int, timeout_s: float) -> TlsHandshakeResult:
        calls.append((host, port, timeout_s))
        return TlsHandshakeResult(
            version="TLSv1.3", cipher="TLS_AES_256_GCM_SHA384", days_to_expiry=90
        )

    monkeypatch.setattr(tls_module, "_tls_handshake", _fake_handshake)
    ctx = _ctx("https://example.invalid:8443")
    TlsPosture().run(ctx)
    assert calls == [("example.invalid", 8443, ctx.settings.timeout_s)]
