"""Target list and exclusion list: format, provenance and loading.

Implements ADR-0019. `data/targets.jsonl` is the committed list of
endpoints the scanner is permitted to scan; `data/exclusions.jsonl` is
the committed, permanent opt-out list. See docs/SCANNING-POLICY.md
"What we scan" and "Opt-out" for the policy this code enforces.

Provenance is a precondition for scanning, not documentation: an entry
without `sources` is not something we are permitted to scan, so
`load_targets` raises rather than warns.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# Hosts under these suffixes are per-app tenants, so the full host - not
# the registrable domain - is the operator unit. Carried over verbatim
# from research/census-2026-08-22/tools/sample.py per ADR-0019: this
# table encodes real knowledge (each *.vercel.app tenant is a distinct
# owner) and must not be re-derived.
PAAS_SUFFIXES = (
    "vercel.app",
    "workers.dev",
    "onrender.com",
    "railway.app",
    "fly.dev",
    "run.app",
    "pages.dev",
    "herokuapp.com",
    "netlify.app",
    "deno.dev",
    "modal.run",
    "hf.space",
    "azurewebsites.net",
    "ngrok.io",
    "ngrok-free.app",
    "replit.dev",
    "koyeb.app",
    "cloudfunctions.net",
)

_DEFAULT_PORTS = {"http": 80, "https": 443}

_SOURCE_KINDS = frozenset({"registry", "directory", "documentation", "agent-card"})
_EXCLUSION_SCOPES = frozenset({"url", "host", "domain"})


class TargetListError(Exception):
    """Raised when `data/targets.jsonl` contains an invalid entry.

    In particular, an entry missing `sources` fails the load rather than
    being skipped or logged: per ADR-0019, provenance is a precondition
    for scanning, and a load that silently drops or warns about it would
    let the precondition slip in an unattended run.
    """


def normalize_target(url: str) -> str:
    """Return the dataset join key for `url`.

    Lowercases scheme and host, drops the default port for that scheme,
    strips a trailing slash, and preserves any non-root path. Idempotent:
    ``normalize_target(normalize_target(x)) == normalize_target(x)``.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    host = parts.hostname or ""
    host = host.lower()
    port = parts.port
    netloc = f"{host}:{port}" if port is not None and _DEFAULT_PORTS.get(scheme) != port else host
    path = parts.path
    if path.endswith("/") and path != "/":
        path = path.rstrip("/")
    if path == "/":
        path = ""
    normalized = f"{scheme}://{netloc}{path}"
    if parts.query:
        normalized = f"{normalized}?{parts.query}"
    return normalized


def operator_unit(url: str) -> str:
    """Return the operator unit for `url`: the registrable domain, or the
    full host for PaaS tenants (see `PAAS_SUFFIXES`)."""
    host = urlsplit(url).netloc.lower().split(":")[0]
    for suffix in PAAS_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return host
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


@dataclass
class Source:
    """One provenance record for a target: where we saw it advertised."""

    directory: str
    ref: str
    kind: str
    observed_at: str


@dataclass
class Target:
    """One entry in `data/targets.jsonl`."""

    target: str
    operator: str
    sources: list[Source]
    first_seen: str
    tags: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def target_id(self) -> str:
        """The dataset join key: `normalize_target(self.target)`."""
        return normalize_target(self.target)


@dataclass
class Exclusion:
    """One entry in `data/exclusions.jsonl`: a permanent opt-out."""

    pattern: str
    scope: str
    reason: str = ""
    requested_by: str = ""
    issue: str = ""
    effective_from: str = ""
    permanent: bool = True


def _strip_lines(path: str) -> list[tuple[int, str]]:
    """Read `path`, returning (1-based line number, content) pairs for
    lines that are neither blank nor `#`-prefixed comments."""
    out: list[tuple[int, str]] = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            out.append((lineno, line))
    return out


def _parse_source(raw: object, path: str, lineno: int) -> Source:
    if not isinstance(raw, dict):
        raise TargetListError(f"{path}:{lineno}: source entry must be an object, got {raw!r}")
    directory = raw.get("directory")
    ref = raw.get("ref")
    kind = raw.get("kind")
    observed_at = raw.get("observed_at")
    if not directory or not isinstance(directory, str):
        raise TargetListError(f"{path}:{lineno}: source entry missing non-empty 'directory'")
    if not ref or not isinstance(ref, str):
        raise TargetListError(f"{path}:{lineno}: source entry missing non-empty 'ref'")
    if kind not in _SOURCE_KINDS:
        raise TargetListError(
            f"{path}:{lineno}: source 'kind' must be one of {sorted(_SOURCE_KINDS)}, got {kind!r}"
        )
    if not observed_at or not isinstance(observed_at, str):
        raise TargetListError(f"{path}:{lineno}: source entry missing non-empty 'observed_at'")
    return Source(directory=directory, ref=ref, kind=kind, observed_at=observed_at)


def _parse_target_line(path: str, lineno: int, line: str) -> Target:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise TargetListError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise TargetListError(f"{path}:{lineno}: expected a JSON object, got {record!r}")

    target = record.get("target")
    if not target or not isinstance(target, str):
        raise TargetListError(f"{path}:{lineno}: entry missing non-empty 'target'")

    sources = record.get("sources")
    if not sources or not isinstance(sources, list):
        raise TargetListError(
            f"{path}:{lineno}: entry for {target!r} has no 'sources'. Provenance is a "
            "precondition for scanning (ADR-0019, docs/SCANNING-POLICY.md); an "
            "unprovenanced entry may not be scanned."
        )
    parsed_sources = [_parse_source(s, path, lineno) for s in sources]

    operator = record.get("operator")
    if not operator or not isinstance(operator, str):
        operator = operator_unit(target)

    first_seen = record.get("first_seen")
    if not first_seen or not isinstance(first_seen, str):
        raise TargetListError(f"{path}:{lineno}: entry missing non-empty 'first_seen'")

    tags = record.get("tags") or []
    if not isinstance(tags, list):
        raise TargetListError(f"{path}:{lineno}: 'tags' must be a list")

    notes = record.get("notes", "")
    if not isinstance(notes, str):
        raise TargetListError(f"{path}:{lineno}: 'notes' must be a string")

    return Target(
        target=target,
        operator=operator,
        sources=parsed_sources,
        first_seen=first_seen,
        tags=list(tags),
        notes=notes,
    )


def load_targets(path: str, exclusions_path: str | None = None) -> list[Target]:
    """Load `data/targets.jsonl`-shaped file at `path`.

    Skips blank lines and `#`-prefixed comment lines. Raises
    `TargetListError`, naming the offending line, on any entry with
    missing or empty `sources`: per ADR-0019, provenance is a
    precondition for scanning, not documentation.

    When `exclusions_path` is given, exclusions are applied before
    returning so no caller can forget (ADR-0019).
    """
    targets = [_parse_target_line(path, lineno, line) for lineno, line in _strip_lines(path)]
    if exclusions_path is not None:
        exclusions = load_exclusions(exclusions_path)
        targets, _excluded = apply_exclusions(targets, exclusions)
    return targets


def _parse_exclusion_line(path: str, lineno: int, line: str) -> Exclusion:
    try:
        record = json.loads(line)
    except json.JSONDecodeError as exc:
        raise TargetListError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    if not isinstance(record, dict):
        raise TargetListError(f"{path}:{lineno}: expected a JSON object, got {record!r}")

    pattern = record.get("pattern")
    if not pattern or not isinstance(pattern, str):
        raise TargetListError(f"{path}:{lineno}: entry missing non-empty 'pattern'")

    scope = record.get("scope", "domain")
    if scope not in _EXCLUSION_SCOPES:
        raise TargetListError(
            f"{path}:{lineno}: 'scope' must be one of {sorted(_EXCLUSION_SCOPES)}, got {scope!r}"
        )

    return Exclusion(
        pattern=pattern,
        scope=scope,
        reason=record.get("reason", ""),
        requested_by=record.get("requested_by", ""),
        issue=record.get("issue", ""),
        effective_from=record.get("effective_from", ""),
        permanent=record.get("permanent", True),
    )


def load_exclusions(path: str) -> list[Exclusion]:
    """Load `data/exclusions.jsonl`-shaped file at `path`.

    Skips blank lines and `#`-prefixed comment lines.
    """
    return [_parse_exclusion_line(path, lineno, line) for lineno, line in _strip_lines(path)]


def _domain_matches(host: str, pattern: str) -> bool:
    """True if `host` is `pattern` itself or a subdomain of it.

    "example.com" matches "example.com" and "api.example.com", but not
    "notexample.com".
    """
    return host == pattern or host.endswith("." + pattern)


def _excluded_by(target: Target, exclusion: Exclusion) -> bool:
    target_id = target.target_id
    host = urlsplit(target_id).hostname or ""
    pattern = exclusion.pattern.lower()
    if exclusion.scope == "url":
        return target_id == normalize_target(exclusion.pattern)
    if exclusion.scope == "host":
        return host == pattern
    if exclusion.scope == "domain":
        return _domain_matches(host, pattern)
    return False  # pragma: no cover - scope is validated at load time


def apply_exclusions(
    targets: list[Target], exclusions: list[Exclusion]
) -> tuple[list[Target], list[Target]]:
    """Split `targets` into (kept, excluded) per `exclusions`.

    `url` scope matches the normalised target exactly. `host` scope
    matches the target's host exactly. `domain` scope matches the host
    itself and any subdomain of it.
    """
    kept: list[Target] = []
    excluded: list[Target] = []
    for target in targets:
        if any(_excluded_by(target, exclusion) for exclusion in exclusions):
            excluded.append(target)
        else:
            kept.append(target)
    return kept, excluded
