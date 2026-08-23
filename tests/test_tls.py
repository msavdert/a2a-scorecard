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
from a2a_scorecard.transport import HostPacer, ScanTransport


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


# --- Real pacer branch: regression for the AttributeError crash on every ----------
# --- HTTPS target (ADR-0020) -------------------------------------------------------
#
# Every test above builds `ProbeContext` with `pacer=None` (the default),
# which takes the `nullcontext()` shortcut in TlsPosture.run and so never
# exercises `ctx.pacer.slot(host)` at all. That is exactly how the original
# bug hid from this whole file: production always supplies a real pacer
# (scan.py passes `scan_transport.pacer`), and that pacer's default key
# function used to be `lambda url: url.host`, which raised AttributeError
# when called with the bare hostname string this check passes - the fake
# agent is HTTP-only, so C032 always SKIPs there too, meaning nothing in the
# existing suite ever called `_tls_handshake` behind a real pacer. This test
# builds a `HostPacer` the same way `ScanTransport` builds its default one
# (see transport.py's `ScanTransport.__init__`) and drives an https target
# through it.


def test_run_with_real_pacer_does_not_raise_and_takes_a_slot(monkeypatch) -> None:
    def _fake_handshake(host: str, port: int, timeout_s: float) -> TlsHandshakeResult:
        return TlsHandshakeResult(
            version="TLSv1.3", cipher="TLS_AES_256_GCM_SHA384", days_to_expiry=90
        )

    monkeypatch.setattr(tls_module, "_tls_handshake", _fake_handshake)

    # Built the same way ScanTransport.__init__ builds its default pacer:
    # HostPacer(pace_per_host_s, key=_default_host_key, ...). Constructing it
    # via a real ScanTransport (rather than importing _default_host_key
    # directly) is deliberate: it proves this test tracks whatever key
    # function production actually wires up, not a copy of it.
    pacer = ScanTransport(sleep=lambda s: None).pacer
    assert isinstance(pacer, HostPacer)

    ctx = ProbeContext("https://example.invalid", httpx.Client(), Settings(), pacer=pacer)
    result = TlsPosture().run(ctx)  # must not raise AttributeError

    assert result.status is CheckStatus.PASS
    # Proves the real-pacer branch actually ran (not the nullcontext()
    # shortcut): a slot was taken for this host, so HostPacer now has a
    # recorded next-allowed time for it.
    assert "example.invalid" in pacer._next_allowed  # noqa: SLF001


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
