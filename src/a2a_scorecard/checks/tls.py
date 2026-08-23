"""Stage 3: TLS configuration and certificate posture (C032).

Performs the single bare TLS handshake ADR-0008 added to
docs/SCANNING-POLICY.md: one connection to the target's host and port using
the stdlib `ssl` default (secure) client context, reading the negotiated
protocol version and the presented certificate, then closing. No HTTP
request rides on this connection, and there is never a second handshake
with a downgraded configuration (ADR-0010).

The handshake lives in the module-level `_tls_handshake` function so unit
tests can monkeypatch it: this is the one check whose probe cannot be
exercised end-to-end by the in-process fake agent, since it serves plain
HTTP (ADR-0010).
"""

from __future__ import annotations

import socket
import ssl
import time
from contextlib import nullcontext
from dataclasses import dataclass
from urllib.parse import urlsplit

from a2a_scorecard.checks.base import Check, ProbeContext
from a2a_scorecard.models import CheckResult, CheckStatus

# Certificates expiring within this many days WARN rather than PASS
# (ADR-0010: matches the shortest common automated renewal cadence).
_EXPIRY_WARN_DAYS = 14


@dataclass
class TlsHandshakeResult:
    """Outcome of one bare TLS handshake, or the error that ended it."""

    version: str | None
    cipher: str | None
    days_to_expiry: int | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _tls_handshake(host: str, port: int, timeout_s: float) -> TlsHandshakeResult:
    """Opens exactly one TCP connection, performs one TLS handshake with the
    stdlib default (secure) client context, reads the negotiated version,
    cipher, and certificate expiry, then closes. Never retries and never
    downgrades (ADR-0010). Any failure - socket, handshake, or certificate
    parsing - is reported in `error` rather than raised, so a hostile or
    misconfigured target degrades this check to a controlled FAIL instead of
    ERROR."""
    context = ssl.create_default_context()
    try:
        with (
            socket.create_connection((host, port), timeout=timeout_s) as sock,
            context.wrap_socket(sock, server_hostname=host) as ssock,
        ):
            version = ssock.version()
            cipher_tuple = ssock.cipher()
            cipher = cipher_tuple[0] if cipher_tuple else None
            cert = ssock.getpeercert()
            days_to_expiry: int | None = None
            not_after = cert.get("notAfter") if cert else None
            if isinstance(not_after, str):
                not_after_s = ssl.cert_time_to_seconds(not_after)
                days_to_expiry = int((not_after_s - time.time()) // 86400)
            return TlsHandshakeResult(version=version, cipher=cipher, days_to_expiry=days_to_expiry)
    except Exception as exc:  # any handshake failure is a FAIL, not a crash
        return TlsHandshakeResult(version=None, cipher=None, days_to_expiry=None, error=str(exc))


def _version_at_least_tls12(version: str | None) -> bool:
    if version is None:
        return False
    # ssl socket.version() returns strings like "TLSv1.2", "TLSv1.3", or
    # older names ("TLSv1", "TLSv1.1", "SSLv3", ...). Anything not matching
    # the modern "TLSv1.X" shape with X >= 2 is below the floor.
    return version in ("TLSv1.2", "TLSv1.3")


class TlsPosture(Check):
    """Performs one bare TLS handshake to the target's host and port and
    grades the negotiated version and certificate expiry (ADR-0010). Plain
    http targets SKIP: there is no TLS to inspect."""

    check_id = "C032"
    title = "TLS configuration and certificate posture"
    stage = 3
    weight = 10
    requires = ("C001",)

    def run(self, ctx: ProbeContext) -> CheckResult:
        parts = urlsplit(ctx.base_url)
        if parts.scheme != "https":
            return self.result(
                CheckStatus.SKIP,
                evidence=f"target scheme is '{parts.scheme}', not https; no TLS to inspect",
            )

        host = parts.hostname
        port = parts.port or 443
        if not host:
            return self.result(
                CheckStatus.FAIL,
                evidence="could not determine hostname from target URL",
            )

        # This handshake is a raw socket, never passing through ctx.client,
        # so it takes a pacer slot directly to observe the same per-host
        # pacing as every httpx request in the scan (ADR-0020). ctx.pacer
        # is only None for direct unit construction of a ProbeContext.
        slot = ctx.pacer.slot(host) if ctx.pacer is not None else nullcontext()
        with slot:
            probe = _tls_handshake(host, port, ctx.settings.timeout_s)
        details = {
            "version": probe.version,
            "cipher": probe.cipher,
            "days_to_expiry": probe.days_to_expiry,
        }

        if not probe.ok:
            return self.result(
                CheckStatus.FAIL,
                evidence=f"TLS handshake failed: {probe.error}",
                details=details,
            )

        if not _version_at_least_tls12(probe.version):
            return self.result(
                CheckStatus.FAIL,
                evidence=f"negotiated protocol version '{probe.version}' is below TLS 1.2",
                details=details,
            )

        if probe.days_to_expiry is not None and probe.days_to_expiry <= _EXPIRY_WARN_DAYS:
            return self.result(
                CheckStatus.WARN,
                evidence=(
                    f"certificate expires in {probe.days_to_expiry} day(s), "
                    f"at or under the {_EXPIRY_WARN_DAYS}-day threshold"
                ),
                details=details,
            )

        return self.result(
            CheckStatus.PASS,
            evidence=(
                f"negotiated {probe.version} ({probe.cipher}); "
                f"certificate valid for {probe.days_to_expiry} more day(s)"
            ),
            details=details,
        )
