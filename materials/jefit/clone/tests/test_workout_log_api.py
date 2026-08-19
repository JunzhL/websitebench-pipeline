"""Workout logging semantics: '+ Add session' creates a session, adding an
exercise logs the default set, the persisted Training Summary renders, and
empty days show the 'No logs' state."""

from __future__ import annotations

from conftest import ISOLATION, login, make_client


def test_seeded_session_training_summary(member) -> None:
    page = member.get("/my-jefit/progress/history?date=2026-08-18")
    assert page.status_code == 200
    assert "Training Summary" in page.text
    assert "Barbell Bench Press" in page.text
    assert "25 lbs x 8 reps" in page.text
    assert "BEST 1RM: 31.67" in page.text
    assert "200 lbs" in page.text  # volume 25 x 8


def test_empty_day_shows_no_logs(member) -> None:
    page = member.get("/my-jefit/progress/history?date=2026-08-01")
    assert "No logs" in page.text
    assert "You don't have any logs for this day." in page.text


def test_add_session_and_default_set(member) -> None:
    created = member.post("/api/sessions", json={"date": "2026-08-19",
                                                 "start": "07:30",
                                                 "end": "08:15"})
    assert created.status_code == 201
    session_id = created.json()["id"]
    logged = member.post(
        f"/api/sessions/{session_id}/sets", json={"exercise_id": 2}
    )
    assert logged.status_code == 201
    body = logged.json()
    assert body["weight_lbs"] == 25.0 and body["reps"] == 8
    page = member.get("/my-jefit/progress/history?date=2026-08-19")
    assert "Training Summary" in page.text
    assert "25 lbs x 8 reps" in page.text


def test_set_edit_persists(member) -> None:
    session_id = member.post(
        "/api/sessions", json={"date": "2026-08-20"}
    ).json()["id"]
    set_id = member.post(
        f"/api/sessions/{session_id}/sets",
        json={"exercise_id": 12, "weight_lbs": 95, "reps": 5},
    ).json()["id"]
    updated = member.post(
        f"/api/sets/{set_id}", json={"weight_lbs": 105, "reps": 3}
    )
    assert updated.status_code == 200
    page = member.get("/my-jefit/progress/history?date=2026-08-20")
    assert "105 lbs x 3 reps" in page.text


def test_record_badge_marks_new_best(member) -> None:
    session_id = member.post(
        "/api/sessions", json={"date": "2026-08-21"}
    ).json()["id"]
    heavier = member.post(
        f"/api/sessions/{session_id}/sets",
        json={"exercise_id": 2, "weight_lbs": 135, "reps": 3},
    ).json()
    assert heavier["is_record"] is True
    lighter = member.post(
        f"/api/sessions/{session_id}/sets",
        json={"exercise_id": 2, "weight_lbs": 45, "reps": 10},
    ).json()
    assert lighter["is_record"] is False


def test_invalid_log_values_rejected(member) -> None:
    session_id = member.post(
        "/api/sessions", json={"date": "2026-08-22"}
    ).json()["id"]
    bad = member.post(
        f"/api/sessions/{session_id}/sets",
        json={"exercise_id": 2, "weight_lbs": -5, "reps": 8},
    )
    assert bad.status_code == 422
    unknown = member.post(
        f"/api/sessions/{session_id}/sets", json={"exercise_id": 999999}
    )
    assert unknown.status_code == 404


def test_logging_is_actor_isolated(member) -> None:
    session_id = member.post(
        "/api/sessions", json={"date": "2026-08-23"}
    ).json()["id"]
    other = make_client()
    login(other, ISOLATION)
    hijack = other.post(
        f"/api/sessions/{session_id}/sets", json={"exercise_id": 2}
    )
    assert hijack.status_code == 403
    empty = other.get("/my-jefit/progress/history?date=2026-08-18")
    assert "No logs" in empty.text


def test_insights_reflect_logged_sessions(member) -> None:
    page = member.get("/my-jefit/progress/insights")
    assert page.status_code == 200
    assert "workout" in page.text and "logged" in page.text


def test_body_stats_goal_update(member) -> None:
    page = member.get("/my-jefit/progress/body-stats")
    assert page.status_code == 200
    assert ">Weight</p>" in page.text
    update = member.post(
        "/my-jefit/progress/body-stats/weight",
        data={"current": "182", "goal": "172"},
        follow_redirects=False,
    )
    assert update.status_code == 302
    detail = member.get("/my-jefit/progress/body-stats/weight")
    assert "182" in detail.text and "172" in detail.text
