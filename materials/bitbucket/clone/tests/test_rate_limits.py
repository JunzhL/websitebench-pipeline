def test_acceptance_routes_never_return_429(signed_in):
    routes = [
        "/dashboard/overview",
        "/repo/all?name=atlascode",
        "/atlassianlabs/atlascode",
        "/atlassianlabs/atlascode/src/main/",
        "/atlassianlabs/atlascode/commits/main",
        "/atlassianlabs/atlascode/branches",
        "/atlassianlabs/atlascode/pull-requests",
        "/atlassianlabs/atlascode/pipelines/4453",
        "/atlassianlabs/atlascode/downloads",
        "/account/history/",
    ]
    for _ in range(8):
        for route in routes:
            response = signed_in.get(route)
            assert response.status_code != 429, route
            assert "Too Many Requests" not in response.text, route


def test_repeated_pipeline_retry_is_idempotent(signed_in):
    route = "/developer/platform-demo/pipelines/1/retry"
    signed_in.post("/developer/platform-demo/pipelines", follow_redirects=False)
    responses = [signed_in.post(route, follow_redirects=False) for _ in range(12)]
    assert {response.status_code for response in responses} == {303}
    page = signed_in.get("/developer/platform-demo/pipelines/1")
    assert page.text.count("Retry requested locally") == 1
