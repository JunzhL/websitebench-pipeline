import app as app_module


def test_signed_out_actions_fail_closed(client):
    for route in (
        "/challenges/solve-me-first/save",
        "/challenges/solve-me-first/run",
        "/challenges/solve-me-first/submit",
    ):
        response = client.post(route, data={}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/auth/login")
    assert client.get(
        "/challenges/solve-me-first/submissions", follow_redirects=False
    ).status_code == 303


def test_run_submit_history_and_resubmit(signed_in):
    source = "def solveMeFirst(a, b):\n    return a + b\n"
    run = signed_in.post(
        "/challenges/solve-me-first/run",
        data={"language": "python3", "source": source, "custom_input": "8\n9"},
        follow_redirects=False,
    )
    assert run.status_code == 303
    result = signed_in.get(run.headers["location"])
    assert "Accepted" in result.text
    assert "17" in result.text
    assert "3 of 3 tests passed" in result.text

    submitted = signed_in.post(
        "/challenges/solve-me-first/submit",
        data={"language": "python3", "source": source},
        follow_redirects=False,
    )
    assert submitted.status_code == 303
    detail = signed_in.get(submitted.headers["location"])
    assert "All 3 local fixture tests passed" in detail.text
    assert "14832 KB" in detail.text

    submission_id = int(submitted.headers["location"].rsplit("/", 1)[1])
    loaded = signed_in.get(
        f"/challenges/solve-me-first/problem?load={submission_id}"
    )
    assert "Previous submission loaded" in loaded.text
    assert "return a + b" in loaded.text

    resubmitted = signed_in.post(
        "/challenges/solve-me-first/submit",
        data={"language": "python3", "source": source + "\n# revised"},
        follow_redirects=False,
    )
    assert resubmitted.status_code == 303
    history = signed_in.get("/challenges/solve-me-first/submissions")
    assert "v3" in history.text


def test_failed_submission_feedback(signed_in):
    response = signed_in.post(
        "/challenges/solve-me-first/submit",
        data={"language": "python3", "source": "def solveMeFirst(a, b):\n    return 0\n"},
        follow_redirects=False,
    )
    detail = signed_in.get(response.headers["location"])
    assert "Wrong Answer" in detail.text
    assert "expected 7 but received 0" in detail.text


def test_save_profile_and_settings(signed_in):
    toggled = signed_in.post(
        "/challenges/simple-array-sum/save", follow_redirects=False
    )
    assert toggled.status_code == 303
    assert "simple-array-sum" in signed_in.get("/dashboard").text

    assert signed_in.post(
        "/profile",
        data={"full_name": "Updated Learner", "bio": "Local practice profile."},
        follow_redirects=False,
    ).status_code == 303
    assert "Updated Learner" in signed_in.get("/profile").text

    assert signed_in.post(
        "/settings",
        data={"preferred_language": "javascript"},
        follow_redirects=False,
    ).status_code == 303
    with app_module.BACKEND.lifecycle.connection() as connection:
        profile = connection.execute(
            "SELECT preferred_language,email_notifications FROM hr_profiles WHERE subject_id=?",
            (app_module.DEMO_ACCOUNT["subject_id"],),
        ).fetchone()
    assert tuple(profile) == ("javascript", 0)
