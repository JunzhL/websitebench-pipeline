# GitLab implementation notes

Source acquisition completed with one page and one download per origin at a time. The report recorded no HTTP 429 response. GitLab app pages still became source-limited because their JavaScript attempted non-GET GraphQL and telemetry calls that the read-only policy blocked. Cloudflare returned HTTP 403 for sign-in and the missing-page probe.

The candidate does not retry those source requests. It uses code-native HTML, CSS, and JavaScript with a same-origin Content Security Policy. All state lives in `gitlab.sqlite3` through `backend/runtime.json` and the generated WebsiteBench integration seam.

Local registration and password recovery preserve the auth runtime's cooldown. An exact repeated registration reuses the active flow. Password recovery checks for an active challenge before issuing mail. If the backend still returns a real cooldown, the response includes `Retry-After` and the page disables its submit button until the wait expires.

Authenticated project mutations are clone-local contracts because no source account or source mutation authority was supplied. The suite covers account lifecycle, repositories, branches, files, commits, issues, merge requests, pipelines, settings, activity, reset, missing routes, and zero remote runtime references.
