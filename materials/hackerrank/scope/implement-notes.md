# HackerRank implementation notes

Formal source acquisition returned HTTP 403 for all configured anonymous pages. Steel browser exploration was also unavailable because the installed CLI had no API key. Source-facing routes remain marked unavailable. The candidate implements truthful local contracts from the supplied task descriptions and does not claim source-pixel fidelity.

The candidate uses code-native HTML, CSS, and JavaScript with a same-origin Content Security Policy. It makes no runtime request to HackerRank or another external service. Learner accounts, profiles, saved challenges, drafts, deterministic runs, submissions, progress, badges, and settings live in `hackerrank.sqlite3` through `backend/runtime.json` and the generated WebsiteBench integration seam.

Code runs never execute submitted code. The local judge recognizes deterministic fixture outcomes and records stdout, errors, test status, runtime, and memory. Registration and password recovery use only the local WebsiteBench outbox. No real email, identity provider, assessment, proctoring, employer action, or payment is attempted.
