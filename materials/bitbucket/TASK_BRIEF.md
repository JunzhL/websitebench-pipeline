# Bitbucket offline clone task brief

## Purpose and roles

Direct observation: Bitbucket is a developer tool for hosting Git repositories, reviewing code changes, and inspecting CI/CD activity. Public visitors can inspect public repository material. Signed-in developers manage repositories and code changes. Reviewers participate in pull requests. Workspace members and administrators manage projects, collaborators, roles, and settings.

## First-party page families and objects

Direct observation covers the public entry page, public workspace and project pages, repository overview and source trees, file details, commits, branches and comparison controls, pull request lists, pipeline run details and logs, clone options, support, and branded missing-resource recovery.

Structural evidence indicates account authentication, dashboard, profile, repository creation, issue tracking, pull request detail, pipelines, membership, repository settings, and account history families. Some of these routes required authentication or returned an application shell during anonymous exploration.

Core objects are workspaces, projects, repositories, files, commits, branches, comparisons, releases or downloads, issues, milestones, labels, pull requests, comments, reviewers, pipelines, jobs, members, roles, repository settings, profiles, and account-history entries.

## Priority

P0 covers public discovery, repository browsing, authentication lifecycle, repository creation, file commits, branches and comparisons, issues, and pull requests.

P1 covers fork and download options, pipelines, collaborators and permissions, repository settings, account history, validation and permission states, help, and missing-route recovery.

P2 covers registration and password-recovery entry surfaces without creating another real account or sending email.

## States and side effects

Login or local construction is required for dashboard, profile, repository creation, owned-repository changes, issues, pull requests, forks, pipeline retry, membership, settings, and account history. Registration input was inaccessible behind AWS WAF during anonymous exploration.

Source-side writes, account creation, invitations, email, source pushes, pipeline triggers, settings changes, payments, external publication, and deployment can create real effects. They are prohibited. The clone implements these actions with isolated local data and a local effects boundary.

## Evidence gaps

Inaccessible content includes successful Atlassian login and registration forms, authenticated dashboard and profile content, account history, repository settings, permissions, public issue detail, anonymous pull request detail, and a working fork flow. These gaps remain labeled unavailable until sanitized authenticated evidence is captured. Local behavior must not be represented as direct source observation.

The Expanded Task Inventory workbook was not supplied and is not required for implementation. Confirmed human trace text and direct source evidence define this clone's scope.
