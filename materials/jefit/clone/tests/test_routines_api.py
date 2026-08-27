"""Routine builder semantics: instant server-side create, autosave defaults,
the empty-name quirk, reorder, and the anonymous draft flow."""

from __future__ import annotations

from conftest import ISOLATION, login, make_client


def _create_plan(member) -> int:
    response = member.post("/api/plans")
    assert response.status_code == 201
    return response.json()["id"]


def test_create_plan_is_instant_and_opens_editor(member) -> None:
    plan_id = _create_plan(member)
    editor = member.get(f"/my-jefit/workouts/edit?id={plan_id}")
    assert editor.status_code == 200
    assert 'value="New Routine"' in editor.text


def test_added_exercise_defaults_3_sets_10lbs_8_reps_60s(member) -> None:
    plan_id = _create_plan(member)
    day_id = member.post(f"/api/plans/{plan_id}/days").json()["id"]
    entry = member.post(
        f"/api/days/{day_id}/exercises", json={"exercise_id": 2}
    ).json()
    assert entry["sets"] == 3
    assert entry["weight_lbs"] == 10
    assert entry["reps"] == 8
    assert entry["rest_seconds"] == 60
    assert entry["name"] == "Barbell Bench Press"


def test_set_edits_autosave_and_persist(member) -> None:
    plan_id = _create_plan(member)
    day_id = member.post(f"/api/plans/{plan_id}/days").json()["id"]
    entry = member.post(
        f"/api/days/{day_id}/exercises", json={"exercise_id": 12}
    ).json()
    updated = member.post(
        f"/api/entries/{entry['id']}",
        json={"weight_lbs": 45, "reps": 5, "rest_seconds": 90},
    )
    assert updated.status_code == 200
    editor = member.get(f"/my-jefit/workouts/edit?id={plan_id}")
    assert 'value="45"' in editor.text
    assert 'value="90"' in editor.text


def test_empty_name_is_silently_ignored(member) -> None:
    plan_id = _create_plan(member)
    member.post(f"/api/plans/{plan_id}/name", json={"name": "Leg Day Focus"})
    result = member.post(f"/api/plans/{plan_id}/name", json={"name": "   "})
    assert result.status_code == 200
    assert result.json()["name"] == "Leg Day Focus"


def test_reorder_via_position_updates(member) -> None:
    plan_id = _create_plan(member)
    day_id = member.post(f"/api/plans/{plan_id}/days").json()["id"]
    first = member.post(
        f"/api/days/{day_id}/exercises", json={"exercise_id": 2}
    ).json()
    second = member.post(
        f"/api/days/{day_id}/exercises", json={"exercise_id": 12}
    ).json()
    assert (first["position"], second["position"]) == (1, 2)
    member.post(f"/api/entries/{first['id']}", json={"position": 2})
    member.post(f"/api/entries/{second['id']}", json={"position": 1})
    editor = member.get(f"/my-jefit/workouts/edit?id={plan_id}").text
    assert editor.index("Barbell Squat") < editor.index("Barbell Bench Press")


def test_saved_plan_appears_in_workouts_list(member) -> None:
    plan_id = _create_plan(member)
    member.post(f"/api/plans/{plan_id}/name", json={"name": "Bench Block"})
    listing = member.get("/my-jefit/workouts")
    assert "Bench Block" in listing.text


def test_current_plan_renders_twice_in_saved_list(member) -> None:
    # source quirk: the current plan appears in the Current Plan section AND
    # in the plans list below
    listing = member.get("/my-jefit/workouts").text
    assert listing.count(">New Routine</p>") >= 2


def test_delete_plan(member) -> None:
    plan_id = _create_plan(member)
    member.post(f"/api/plans/{plan_id}/name", json={"name": "Doomed Plan"})
    assert "Doomed Plan" in member.get("/my-jefit/workouts").text
    member.post(f"/api/plans/{plan_id}/delete")
    assert "Doomed Plan" not in member.get("/my-jefit/workouts").text


def test_plan_apis_reject_other_actor(member) -> None:
    plan_id = _create_plan(member)
    other = make_client()
    login(other, ISOLATION)
    assert other.post(
        f"/api/plans/{plan_id}/name", json={"name": "X"}
    ).status_code == 403
    assert other.get(
        f"/my-jefit/workouts/edit?id={plan_id}"
    ).status_code == 404


def test_anonymous_build_routine_draft_save(fresh_state) -> None:
    client = fresh_state
    start = client.get("/build-routine", follow_redirects=False)
    assert start.status_code == 302
    location = start.headers["location"]
    assert location.startswith("/build-routine?code=")
    code = location.split("code=", 1)[1]
    page = client.get(location)
    assert page.status_code == 200
    saved = client.post("/api/build-routine/save", json={"code": code})
    assert saved.status_code == 200
    redirect = saved.json()["redirect"]
    assert redirect.startswith("/routines/")
    detail = client.get(redirect)
    assert detail.status_code == 200
    assert "New Routine" in detail.text


def test_member_build_routine_redirects_to_editor(member) -> None:
    response = member.get("/build-routine", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith(
        "/my-jefit/workouts/edit?id="
    )
