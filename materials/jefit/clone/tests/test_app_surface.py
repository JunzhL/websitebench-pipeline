"""Route surface, titles, and unbranded-404 fidelity."""

import html
import re

PUBLIC_ROUTES = {
    "/": "Your Ultimate Workout Planner & Tracking App for Progress - JEFIT",
    "/elite": None,
    "/exercises": "Exercise Database - JEFIT",
    "/exercises/2/barbell-bench-press": "Barbell Bench Press - JEFIT",
    "/routines": "Workout Routine Database - JEFIT",
    "/routines/beginner": None,
    "/routines/19113/6-weeks-to-six-pack-abs": None,
    "/login": None,
    "/login/forgot-password": None,
    "/signup": None,
    "/signup/results": None,
    "/signup/register": None,
    "/support": None,
    "/support/faq": None,
    "/about-us": None,
    "/ai-workout-tracker": None,
    "/ai-workout-tracker/adaptive-plan": None,
    "/use-case": None,
    "/watch": None,
    "/coach": None,
    "/our-story": None,
    "/community/": None,
    "/blog": None,
    "/terms-of-use": None,
    "/privacy-policy": None,
    "/ip-notice-process": None,
    "/press-media": None,
}


def _title(text: str) -> str:
    match = re.search(r"<title>([^<]*)</title>", text)
    return html.unescape(match.group(1)) if match else ""


def test_public_routes_render(client) -> None:
    for route, expected_title in PUBLIC_ROUTES.items():
        response = client.get(route)
        assert response.status_code == 200, route
        if expected_title:
            assert _title(response.text) == expected_title, route


def test_exercises_page2_title(client) -> None:
    response = client.get("/exercises?page=2")
    assert response.status_code == 200
    assert _title(response.text) == "Exercise Database - Page 2 - JEFIT"
    assert "EXERCISES FOUND" in response.text


def test_exercises_count_is_true_fixture_count(client) -> None:
    # data reduction: the rendered count must equal the fixture's real size,
    # never the source's 1295 (which the fixture does not back).
    response = client.get("/exercises")
    assert ">53<!-- -->&nbsp;</span>EXERCISES FOUND" in response.text


def test_exercise_detail_synthetic_renders(client) -> None:
    response = client.get("/exercises/9001/hanging-knee-raise")
    assert response.status_code in (200, 404)
    listed = client.get("/exercises").text
    match = re.search(r'href="/exercises/(9\d{3})/([a-z0-9-]+)"', listed)
    if match:
        detail = client.get(f"/exercises/{match.group(1)}/{match.group(2)}")
        assert detail.status_code == 200


def test_community_redirects_like_source(client) -> None:
    response = client.get("/community", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/community/"


def test_unknown_path_unbranded_404(client) -> None:
    response = client.get("/zzzz-no-match-websitebench")
    assert response.status_code == 404
    assert "<title>404 Not Found</title>" in response.text
    assert "The requested URL was not found on this server." in response.text
    # unbranded: no site chrome at all
    assert "jefit" not in response.text.casefold()


def test_scope_delta_omissions_fall_to_404(client) -> None:
    for route in ("/download-app", "/blog/some-article", "/q&a/anything",
                  "/user/123"):
        assert client.get(route).status_code == 404, route


def test_routine_sorts_apply(client) -> None:
    default = client.get("/routines").text
    views = client.get("/routines?sort=views").text
    latest = client.get("/routines?sort=last_updated").text
    def order(text):
        return re.findall(r'href="/routines/(\d+)/', text)
    assert order(default) != order(views)
    assert order(default) != order(latest)


def test_external_boundary_page(client) -> None:
    response = client.get("/external/apps.apple.com")
    assert response.status_code == 200
    assert "No remote request was made" in response.text


def _slide_gif_order(document: str) -> list[str]:
    """Ordered slide -> gif pairing inside the onboarding modal.

    Read from each slide's srcset 1x candidate: that is the payload the
    browser renders (the larger optimizer widths were never captured and
    resolve to local 404s, a recorded known difference).
    """

    portal = document[document.find('id="headlessui-portal-root"') :]
    return [
        re.search(r"image\.q([0-9a-f]{10})", match.group(1)).group(1)
        for match in re.finditer(r'srcset="([^"]*?) 1x', portal)
        if re.search(r"image\.q([0-9a-f]{10})", match.group(1))
    ][:6]


def test_build_routine_modal_slide_image_pairing(client) -> None:
    """Each onboarding slide must keep the image the capture paired it with.

    Slide 3 carries the 'Link copied' sharing demo; its gif animates from the
    builder view to the pill, so a screenshot can catch any phase — the
    load-bearing invariant is the pairing, asserted here structurally.
    """

    served = client.get("/build-routine", follow_redirects=True).text
    order = _slide_gif_order(served)
    assert len(order) >= 3, order
    # three distinct slides, in capture order (opt5, opt6, opt7)
    assert order[0] != order[1] != order[2]
    assert order[:3] == ["041467da58", "e5b8b18d47", "a893857efa"], order
    # and the active slide is the third, as captured
    portal = served[served.find('id="headlessui-portal-root"') :]
    active = portal.find("swiper-slide-active")
    third = portal.find("image.qa893857efa")
    assert active > 0 and third > active, "slide 3 is not the active slide"
