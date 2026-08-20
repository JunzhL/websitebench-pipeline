"""Network closure: no served document or clone-local asset leaves the origin."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import sign_in


CLONE_ROOT = Path(__file__).resolve().parents[1]

# The same shape the offline-clone static diagnostic audits.
REMOTE_REF = re.compile(
    r"(?i)(?:src|href|action|url)\s*[=(:]\s*[\"']?\s*"
    r"(?:https?:)?//(?!localhost|127\.0\.0\.1)[a-z0-9.-]+\.[a-z]{2,}"
)

SERVED_ROUTES = (
    "/",
    "/?nav=product",
    "/?nav=apps",
    "/?nav=resources",
    "/?menu=open",
    "/pricing/",
    "/pricing/?period=yearly",
    "/pricing/?period=monthly",
    "/why-vpn/",
    "/what-is-a-vpn/",
    "/servers/",
    "/vpn-features/",
    "/vpn-features/threat-protection/",
    "/money-back-guarantee/",
    "/coupons/",
    "/vpn-locations/",
    "/reviews/",
    "/trust/",
    "/no-log-vpn-policy/",
    "/secure-browser/",
    "/cloud-storage/",
    "/vpn-setup/windows/",
    "/vpn-for-streaming/",
    "/resources/",
    "/setup-guides/",
    "/what-is-my-ip-address/",
    "/blog/",
    "/tos/",
    "/privacy-policy/",
    "/partners/",
    "/press/",
    "/support",
    "/support/search?query=zzzz-no-match-websitebench",
    "/login",
    "/login/reset-password",
    "/checkout/address-payment-method?flow=essential-annual",
    "/checkout/address-payment-method?flow=essential-annual&method=card",
    "/checkout/address-payment-method?flow=essential-monthly&method=card",
    "/checkout/address-payment-method?flow=advanced-biennial&method=card",
    "/checkout/address-payment-method?flow=essential-annual&method=paypal",
    "/zzzz-no-match-websitebench",
)

SUBSCRIBER_ROUTES = (
    "/account/",
    "/account/billing",
    "/account/plan",
    "/account/billing-contact",
)


def test_served_public_documents_have_no_remote_refs(client: TestClient) -> None:
    for route in SERVED_ROUTES:
        response = client.get(route)
        assert response.status_code in {200, 404}, route
        hits = REMOTE_REF.findall(response.text)
        assert not hits, (route, hits[:5])


def test_served_subscriber_documents_have_no_remote_refs(
    fresh_state: TestClient,
) -> None:
    sign_in(fresh_state)
    for route in SUBSCRIBER_ROUTES:
        response = fresh_state.get(route)
        assert response.status_code == 200, route
        hits = REMOTE_REF.findall(response.text)
        assert not hits, (route, hits[:5])


def test_clone_local_site_assets_have_no_remote_refs() -> None:
    root = CLONE_ROOT / "static" / "site"
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.casefold() in {".css", ".js", ".html", ".svg"}
    ]
    assert files, "clone-local asset tree is missing"
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = REMOTE_REF.findall(text)
        assert not hits, (path.name, hits[:5])


def test_promoted_vendor_stylesheets_exist_and_are_localized() -> None:
    """The 18 demoted stylesheets must have localized siblings."""

    vendor = CLONE_ROOT / "static" / "site" / "vendor"
    sheets = sorted(vendor.glob("localized-*.css"))
    assert sheets, "no promoted stylesheet was found; run promote_localized_assets"
    for sheet in sheets:
        text = sheet.read_text(encoding="utf-8", errors="replace")
        assert not REMOTE_REF.findall(text), sheet.name


def test_served_pages_never_reference_a_demoted_pristine_payload() -> None:
    """A reference to a demoted payload would be a runtime remote font fetch."""

    import json

    manifest = json.loads(
        (CLONE_ROOT.parent / "source-assets" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    demoted = [
        "/" + asset["runtime_path"].removeprefix("clone/")
        for asset in manifest["assets"]
        if not asset["required"] and asset["runtime_path"].endswith(".css")
    ]
    assert demoted, "expected the manifest to demote some stylesheets"
    for path in sorted((CLONE_ROOT / "frontend" / "pages").glob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        offenders = [url for url in demoted if url in text]
        assert not offenders, (path.name, offenders[:3])


def test_detector_flags_injected_remote_ref() -> None:
    """Negative control: the audit regex must catch a real remote load."""

    assert REMOTE_REF.search('<img src="https://evil.example.com/pixel.gif">')
    assert REMOTE_REF.search("body{background:url(//cdn.example.net/x.png)}")
    assert REMOTE_REF.search('<form action="https://checkout.example.com/pay">')
    # and it must not match a clean local path, or it would pass by matching all
    assert not REMOTE_REF.search('<img src="/static/assets/x.png">')
    assert not REMOTE_REF.search('<a href="/pricing/">Pricing</a>')
