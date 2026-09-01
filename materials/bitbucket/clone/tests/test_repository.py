def create_project(client, path="ci-demo"):
    response = client.post(
        "/repo/create",
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
    assert signed_in.get(f"{base}/src/main/").status_code == 200

    saved = signed_in.post(
        f"{base}/save-file",
        data={
            "branch": "main",
            "file_path": "src/app.py",
            "content": "print('local')\n",
            "message": "Add local app",
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    file_page = signed_in.get(f"{base}/src/main/src/app.py")
    assert "print(&#x27;local&#x27;)" in file_page.text

    branch = signed_in.post(
        f"{base}/branches",
        data={"name": "feature/offline", "source": "main"},
        follow_redirects=False,
    )
    assert branch.status_code == 303
    assert "feature/offline" in signed_in.get(f"{base}/branches").text
    switched = signed_in.get(f"{base}/src/feature%2Foffline")
    assert switched.status_code == 200
    assert "Files" in switched.text
    assert signed_in.get(f"{base}/branches/compare/main...feature/offline").status_code == 200

    settings = signed_in.post(
        f"{base}/admin",
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
        f"{base}/branches",
        data={"name": "feature", "source": "main"},
        follow_redirects=False,
    )

    issue = signed_in.post(
        f"{base}/issues/new",
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
    assert "Pipeline needs review" in signed_in.get(f"{base}/issues/1").text
    assert signed_in.post(
        f"{base}/issues/1/comments",
        data={"body": "Reproduced locally."},
        follow_redirects=False,
    ).status_code == 303
    assert signed_in.post(
        f"{base}/issues/1/state",
        data={"status": "closed"},
        follow_redirects=False,
    ).status_code == 303

    merge_request = signed_in.post(
        f"{base}/pull-requests/new",
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
    assert "Merge local feature" in signed_in.get(f"{base}/pull-requests/1").text
    assert signed_in.post(
        f"{base}/pull-requests/1/comments",
        data={"body": "Diff reviewed locally."},
        follow_redirects=False,
    ).status_code == 303
    merge_request_page = signed_in.get(f"{base}/pull-requests/1")
    assert "README.md" in merge_request_page.text
    assert "Diff reviewed locally." in merge_request_page.text
    assert "Reviewer:</strong> developer" in merge_request_page.text
    assert signed_in.post(
        f"{base}/pull-requests/1/state",
        data={"status": "merged"},
        follow_redirects=False,
    ).status_code == 303

    pipeline = signed_in.post(f"{base}/pipelines", follow_redirects=False)
    assert pipeline.status_code == 303
    pipeline_page = signed_in.get(f"{base}/pipelines/1")
    assert "Job succeeded" in pipeline_page.text
    assert signed_in.post(
        f"{base}/pipelines/1/retry", follow_redirects=False
    ).status_code == 303

    activity = signed_in.get("/account/history/")
    assert "Pipeline" in activity.text
    assert "Pull Request" in activity.text


def test_fork_download_members_and_permissions(signed_in):
    downloads = signed_in.get("/atlassianlabs/atlascode/downloads")
    assert downloads.status_code == 200
    assert "Clone in Sourcetree" in downloads.text
    assert "Clone in VS Code" in downloads.text

    forked = signed_in.post("/atlassianlabs/atlascode/fork", follow_redirects=False)
    assert forked.status_code == 303
    assert signed_in.get("/developer/atlascode").status_code == 200
    assert "7c4d9a21" in signed_in.get("/developer/atlascode/commits/main").text

    member = signed_in.post(
        "/developer/platform-demo/admin/access",
        data={"username": "reviewer", "role": "Developer"},
        follow_redirects=False,
    )
    assert member.status_code == 303
    access = signed_in.get("/developer/platform-demo/admin/access")
    assert "reviewer" in access.text
    assert "Developer" in access.text


def test_anonymous_write_requires_sign_in(client):
    routes = [
        ("/repo/create", {}),
        ("/atlassianlabs/atlascode/fork", {}),
        ("/atlassianlabs/atlascode/issues/new", {"title": "No"}),
        ("/atlassianlabs/atlascode/pipelines/4453/retry", {}),
    ]
    for route, data in routes:
        response = client.post(route, data=data, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/account/signin/")


def test_action_validation_and_seeded_activity_options(signed_in):
    invalid = signed_in.post(
        "/repo/create", data={"name": ""}, follow_redirects=False
    )
    assert invalid.status_code == 303
    validation = signed_in.get(invalid.headers["location"])
    assert "Project name is required" in validation.text

    history = signed_in.get("/account/history/")
    assert history.status_code == 200
    assert "active" in history.text
    assert "View details" in history.text
    assert "cancellable" in history.text
    assert "href='/developer/platform-demo'" in history.text
