"""Invariant `no-secret-material-anywhere`.

No credential, cookie, authorization header, session token, live or test payment
key, or signed URL may appear in the repository, its evidence, its logs or its
assets.  This run already had one real scare: a bounded capture probe brought
back a live Stripe checkout-session identifier in a refused-request log and a
live publishable key in a captured DOM.  Both were purged and the whole unit was
deleted; this test is the standing guard that they stay gone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import CLONE_ROOT, SITE_ROOT

# Shapes that are secret by nature.  A bare token like `pk_test` appearing as a
# *regex literal* inside a vendor bundle is not a key, so every pattern here
# requires the key body as well.
SECRET_PATTERNS = {
    "stripe-live-secret": re.compile(r"sk_live_[A-Za-z0-9]{8,}"),
    "stripe-live-publishable": re.compile(r"pk_live_[A-Za-z0-9]{8,}"),
    "stripe-live-restricted": re.compile(r"rk_live_[A-Za-z0-9]{8,}"),
    "stripe-live-session": re.compile(r"cs_live_[A-Za-z0-9]{8,}"),
    "stripe-test-secret": re.compile(r"sk_test_[A-Za-z0-9]{8,}"),
    "stripe-test-publishable": re.compile(r"pk_test_[A-Za-z0-9]{8,}"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private-key-block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "bearer-header": re.compile(r"(?i)authorization\s*[:=]\s*[\"']?bearer\s+[A-Za-z0-9._-]{16,}"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "aws-signed-url": re.compile(r"X-Amz-Signature=[A-Fa-f0-9]{32,}"),
    "set-cookie-session": re.compile(
        r"(?i)set-cookie\s*[:=]\s*[\"']?[A-Za-z0-9_-]*session[A-Za-z0-9_-]*="
        r"[A-Za-z0-9._-]{16,}"
    ),
}

TEXTUAL = {
    ".py",
    ".html",
    ".css",
    ".js",
    ".mjs",
    ".json",
    ".jsonl",
    ".txt",
    ".md",
    ".yaml",
    ".yml",
    ".svg",
    ".map",
}
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache"}


def _files(root: Path):
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix.casefold() in TEXTUAL:
            yield path


def _scan(path: Path) -> list[tuple[str, str]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # pragma: no cover
        return []
    hits = []
    for name, pattern in SECRET_PATTERNS.items():
        match = pattern.search(text)
        if match:
            hits.append((name, match.group(0)[:24]))
    return hits


def test_candidate_and_evidence_carry_no_secret_material() -> None:
    offenders: list[tuple[str, str, str]] = []
    scanned = 0
    for root in (CLONE_ROOT, SITE_ROOT / "source-current", SITE_ROOT / "source-assets",
                 SITE_ROOT / "backend", SITE_ROOT / "tools"):
        for path in _files(root):
            scanned += 1
            for name, snippet in _scan(path):
                offenders.append((str(path.relative_to(SITE_ROOT)), name, snippet))
    assert scanned > 500, f"only {scanned} files scanned; the probe looks inert"
    assert not offenders, offenders[:10]


def test_no_session_token_or_cookie_value_is_persisted_in_the_tree() -> None:
    """The cookie *name* is the site's own vocabulary; a cookie *value* is not."""

    cookie_name = "__Host-websitebench-deleteme-session"
    offenders = []
    for path in _files(CLONE_ROOT):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(re.escape(cookie_name) + r"=([A-Za-z0-9._-]+)", text):
            offenders.append((path.name, match.group(1)[:16]))
    assert not offenders, offenders


def test_no_password_literal_leaves_the_seed_module() -> None:
    """The two seeded passwords exist so tests can sign in.  They must live in
    exactly one place and never be echoed into a served document."""

    from conftest import ISOLATION, PRIMARY, make_client, sign_in

    client = make_client()
    sign_in(client)
    for route in ("/account", "/account/profile", "/login"):
        body = client.get(route).text
        assert PRIMARY["password"] not in body, route
        assert ISOLATION["password"] not in body, route


def test_detects_a_planted_key(tmp_path: Path) -> None:
    """Negative control: the scanner must fire on every shape it claims to see.

    A green secret scan has to mean "nothing is there", not "the patterns never
    matched anything at all".
    """

    # Assembled from fragments on purpose: a literal sample key in this file
    # would be a finding in the very scan it exists to prove.
    body = "51QwErTyUiOpAsDfGhJkL"
    samples = {
        "stripe-live-publishable": "pk" + "_live_" + body,
        "stripe-live-session": "cs" + "_live_" + body,
        "stripe-test-secret": "sk" + "_test_" + body,
        "aws-access-key": "AKIA" + "IOSFODNN7EXAMPLE",
        "private-key-block": "-----BEGIN " + "RSA PRIVATE KEY-----",
        "bearer-header": "Authorization: " + "Bearer abcdefghijklmnop0123",
        "jwt": "eyJ" + "hbGciOiJIUzI1NiJ9." + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0."
        + "dBjftJeZ4CVPmB92K27u",
        "aws-signed-url": "X-Amz-" + "Signature=" + "a" * 64,
    }
    for expected, payload in samples.items():
        planted = tmp_path / f"{expected}.txt"
        planted.write_text(f"harmless text {payload} more text\n", encoding="utf-8")
        found = {name for name, _ in _scan(planted)}
        assert expected in found, (expected, found)

    clean = tmp_path / "clean.txt"
    clean.write_text("nothing to see; pk_test is only a prefix here\n", encoding="utf-8")
    assert _scan(clean) == []


def test_the_bare_prefix_in_a_vendor_bundle_is_not_a_finding() -> None:
    """The mirrored Stripe bundle contains the literal `/^pk_test/` as a regex.

    That is a validation rule, not a key.  A scanner that flagged it would cry
    wolf on frozen evidence nobody may edit, so the patterns require a key body.
    """

    bundle = (
        SITE_ROOT
        / "source-assets"
        / "2026-08-20.deleteme-r1"
        / "app.joindeleteme.com"
        / "assets"
        / "CheckoutPage-BGTzsYLQ.js"
    )
    assert bundle.is_file()
    text = bundle.read_text(encoding="utf-8", errors="replace")
    assert "pk_test" in text, "the fixture premise changed"
    assert not _scan(bundle)
