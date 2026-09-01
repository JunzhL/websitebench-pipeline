# Source access notes

Provider preflight on 2026-09-01 found the Steel CLI unavailable. WebsiteBench/Playwright is the selected controlled browser channel.

Source acquisition is GET-only and single-flight. It uses one page at a time, five seconds of settle time per route, no polling, and no mutation authorization. If Bitbucket returns HTTP 429, acquisition stops and records the affected row. A later run may resume only after the server's `Retry-After` interval. Clone tests and diagnostics use loopback and never contact Bitbucket.

Authenticated source exploration is limited to read-only navigation after the user enters credentials privately. Raw authenticated material belongs in ignored `source-auth-scratch` storage. No credential, cookie, token, session profile, real email address, or private account data may enter committed evidence.

Public client access tokens found in captured source markup use length-preserving `[REDACTED]` replacements in committed evidence.
