# Vegapunk YouTube module: verified migration boundary

## Decision

A concrete YouTube module exists, but only on Vegapunk's unmerged [`feat/embodied-skill-registry-v1`](https://github.com/v6582374-netizen/Vegapunk/tree/feat/embodied-skill-registry-v1) branch at [`c9b41d843f5a6d302bd988aff082d00c4d943e04`](https://github.com/v6582374-netizen/Vegapunk/commit/c9b41d843f5a6d302bd988aff082d00c4d943e04). This revision is the source anchor for a selective migration.

Vegapunk `main` at [`f8733e1367501781b0e6cc73b064bc1b2fcebbf8`](https://github.com/v6582374-netizen/Vegapunk/commit/f8733e1367501781b0e6cc73b064bc1b2fcebbf8), the other published branches, PR #34 refs, and the repository tags contain no comparable module. The public-ref inspection was performed on 2026-09-16 with `git ls-remote --heads --tags`, GitHub's ref/tree APIs, and an ephemeral clone of the source branch.

The feature began with [`46236eec2ee03cada54dc38596dbd51c6f6dddbe`](https://github.com/v6582374-netizen/Vegapunk/commit/46236eec2ee03cada54dc38596dbd51c6f6dddbe). The final anchor includes OAuth failure handling, a manual local-library flow, caption fetching, Chinese translation, API/UI tests, and a source-side request-risk note. It deliberately retires automatic scheduled fetching.

## Product capability worth carrying forward

The verified flow is:

1. User configures their own Google OAuth client and connects a YouTube account with the read-only scope.
2. The client imports subscriptions through YouTube Data API, then manually discovers updates per channel using the public RSS feed.
3. Videos enter a local SQLite library. Caption retrieval is explicitly per selected video; it tries the official caption path and falls back to `youtube-transcript-api` when needed.
4. The user can retain/delete/select entries and translate retrieved captions through a separately configured OpenAI-compatible endpoint. Translation credentials and OAuth values remain in the local secret store.

This is a useful starting point for a personal YouTube knowledge workbench. It is not a general Vegapunk agent, research, automation, or scheduling subsystem.

## Minimum technical boundary

Migrate or reimplement the following as one vertical slice, preserving its behavior while giving the new desktop app its own names and storage location:

| Layer | Verified source | Required local seam |
| --- | --- | --- |
| Domain and persistence | [`coworker/youtube/`](https://github.com/v6582374-netizen/Vegapunk/tree/c9b41d843f5a6d302bd988aff082d00c4d943e04/desktop/openworker/upstream/coworker/youtube) | `YouTubeClient`, `YouTubeAutomationService`, `YouTubeStore`, and `YouTubeTranslationService`; SQLite; a narrow secret-storage interface |
| Local API adapter | [`server/app.py`](https://github.com/v6582374-netizen/Vegapunk/blob/c9b41d843f5a6d302bd988aff082d00c4d943e04/desktop/openworker/upstream/coworker/server/app.py) | OAuth callback/state validation plus `/v1/youtube/*` operations: status, OAuth settings/start/callback/disconnect, subscription refresh, manual update discovery, videos, caption retrieval, selection/deletion, translation settings/test/translation |
| Desktop surface | [`YouTubeView.tsx`](https://github.com/v6582374-netizen/Vegapunk/blob/c9b41d843f5a6d302bd988aff082d00c4d943e04/desktop/openworker/upstream/surfaces/gui/src/components/YouTubeView.tsx), [`youtube-prototype.css`](https://github.com/v6582374-netizen/Vegapunk/blob/c9b41d843f5a6d302bd988aff082d00c4d943e04/desktop/openworker/upstream/surfaces/gui/src/components/youtube-prototype.css), and the YouTube segment of [`api.ts`](https://github.com/v6582374-netizen/Vegapunk/blob/c9b41d843f5a6d302bd988aff082d00c4d943e04/desktop/openworker/upstream/surfaces/gui/src/api.ts) | A single YouTube library route/screen; adapt generic shell components rather than transplanting Vegapunk navigation |
| Verification | [`test_youtube.py`](https://github.com/v6582374-netizen/Vegapunk/blob/c9b41d843f5a6d302bd988aff082d00c4d943e04/desktop/openworker/upstream/tests/test_youtube.py) and [`youtube.spec.ts`](https://github.com/v6582374-netizen/Vegapunk/blob/c9b41d843f5a6d302bd988aff082d00c4d943e04/desktop/openworker/upstream/surfaces/gui/e2e/youtube.spec.ts) | Port the service/API contracts first; keep browser coverage only after the new shell exists |

The only source-level host dependencies are the local secret store (`coworker/secrets.py`), state-directory policy, FastAPI/HTTP transport, and small presentational UI primitives. The source manifest lists `httpx`, `fastapi`, and `youtube-transcript-api`; SQLite and XML parsing are standard-library dependencies. The translator calls a configurable OpenAI-compatible HTTP endpoint, so it should remain an optional feature rather than a foundational dependency.

Do **not** migrate Vegapunk's discovery/research agents, PaperOrchestra, model/provider catalog, skills, task scheduler, `sci_tasks` submodule, or the OpenWorker application shell. The old scheduled YouTube endpoints are retained only as disabled compatibility stubs in the source, not as a product capability to revive.

## Provenance and legal boundary

Vegapunk's repository root carries Apache-2.0, while the source module resides beneath `desktop/openworker/upstream/`, whose [`LICENSE`](https://github.com/v6582374-netizen/Vegapunk/blob/c9b41d843f5a6d302bd988aff082d00c4d943e04/desktop/openworker/upstream/LICENSE) is MIT (copyright Andrew Ng). The module files contain no separate copyright header. Treat the nested MIT notice as applicable to copied source, retain its notice, and complete a dependency-license inventory before distribution; this is the strongest verified provenance, not a statement about authorship beyond the repository records.

The module's own [`request-risk note`](https://github.com/v6582374-netizen/Vegapunk/blob/c9b41d843f5a6d302bd988aff082d00c4d943e04/docs/research/2026-08-20-youtube-fetch-updates-request-risk.md) records two material product constraints: official caption download commonly cannot serve third-party subscription videos because of its authorization rule, and the fallback uses an undocumented YouTube endpoint that can be blocked. The new product should preserve manual, user-initiated retrieval and make availability/failure visible; it must not add automatic proxy or quota-evasion behavior.

## What this does not establish

This audit establishes the source revision and migration boundary. It does not establish that transcript acquisition succeeds for a particular user, that the inherited UI matches the new product, or that third-party dependencies and YouTube platform terms are ready for distribution. Those are separate product, compliance, and architecture decisions.
