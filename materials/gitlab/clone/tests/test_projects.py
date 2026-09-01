def create_project(client, path="ci-demo"):
    response = client.post(
        "/projects/new",
        data={
            "name": "CI Demo",
            "path": path,
            "description": "Local CI project",
            "visibility": "private",
            "readme": "yes",
            "gitignore": "Python",
            "license": "MIT",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    return f"/developer/{path}"


def test_project_repository_branch_and_settings(signed_in):
    base = create_project(signed_in)
    assert "CI Demo" in signed_in.get(base).text

    saved = signed_in.post(
        f"{base}/-/files/save",
        data={
            "branch": "main",
            "file_path": "src/app.py",
            "content": "print('local')\n",
            "message": "Add local app",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    file_page = signed_in.get(f"{base}/-/blob/main/src/app.py")
    assert "print(&#x27;local&#x27;)" in file_page.text

    branch = signed_in.post(
        f"{base}/-/branches",
        data={"name": "feature/offline", "source": "main"},
        follow_redirects=False,
    )
    assert branch.status_code == 303
    assert "feature/offline" in signed_in.get(f"{base}/-/branches").text
    assert signed_in.get(f"{base}/-/compare/main...feature/offline").status_code == 200

    settings = signed_in.post(
        f"{base}/-/edit",
        data={
            "name": "CI Demo",
            "description": "Updated locally",
            "visibility": "public",
            "default_branch": "main",
            "topics": "ci, offline",
            "notifications": "watch",
        },
        follow_redirects=False,
    )
    assert settings.status_code == 303
    overview = signed_in.get(base)
    assert "Updated locally" in overview.text
    assert "offline" in overview.text


def test_issue_merge_request_pipeline_and_fork(signed_in):
    base = create_project(signed_in, "workflow-demo")
    signed_in.post(
        f"{base}/-/branches",
        data={"name": "feature", "source": "main"},
        follow_redirects=False,
    )

    issue = signed_in.post(
        f"{base}/-/issues/new",
        data={
            "title": "Pipeline needs review",
            "description": "Inspect the local job.",
            "labels": "ci, bug",
            "assignee": "developer",
            "milestone": "1.0",
        },
        follow_redirects=False,
    )
    assert issue.status_code == 303
    assert "Pipeline needs review" in signed_in.get(f"{base}/-/issues/1").text
    assert signed_in.post(
        f"{base}/-/issues/1/comments",
        data={"body": "Reproduced locally."},
        follow_redirects=False,
    ).status_code == 303
    assert signed_in.post(
        f"{base}/-/issues/1/state",
        data={"status": "closed"},
        follow_redirects=False,
    ).status_code == 303

    merge_request = signed_in.post(
        f"{base}/-/merge_requests/new",
        data={
            "source_branch": "feature",
            "target_branch": "main",
            "title": "Merge local feature",
            "description": "Review this change.",
            "reviewer": "developer",
        },
        follow_redirects=False,
    )
    assert merge_request.status_code == 303
    assert "Merge local feature" in signed_in.get(f"{base}/-/merge_requests/1").text
    assert signed_in.post(
        f"{base}/-/merge_requests/1/state",
        data={"status": "merged"},
        follow_redirects=False,
    ).status_code == 303

    pipeline = signed_in.post(f"{base}/-/pipelines", follow_redirects=False)
    assert pipeline.status_code == 303
    pipeline_page = signed_in.get(f"{base}/-/pipelines/1")
    assert "Job succeeded" in pipeline_page.text
    assert signed_in.post(
        f"{base}/-/pipelines/1/retry", follow_redirects=False
    ).status_code == 303

    activity = signed_in.get("/activity")
    assert "Pipeline" in activity.text
    assert "Merge Request" in activity.text
