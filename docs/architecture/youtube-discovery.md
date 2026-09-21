# Official subscription discovery

The existing read-only OAuth connection and native credential store authorize subscriptions,
channels (uploads playlist), playlistItems and necessary videos detail requests. Discovery has
no RSS, WebSub, scraped-page or private-API fallback. Caption acquisition remains separate.

A dedicated local scheduler checks every 300 seconds while Auto Update is on. Model work and
caption cooldown do not occupy this scheduler. Membership sync has its own six-hour schedule
and explicit refresh in the existing connection interface. Off prevents new automatic passes
and automatic recovery; an already issued request may finish. Reconnect requires user action.

Each pass checks at most 100 channels, one page of 50 entries per channel, and inserts at most
100 candidates. A next-page token, unresolved video details, failure or exhausted pass limit
means coverage is incomplete, even if the first item is already known or old. Complete means
the bounded API listing ended and all relevant facts were verified, not that YouTube's API
perfectly mirrors its website. Fair paging across large subscriptions is a later issue.

SQLite retains per-source scan intervals and proven coverage windows, first source observation
request interval (saved before details so failures cannot erase it), local discovery time, playlist insertion time and public publication time.
`playlistItems.snippet.publishedAt` is insertion time; `videos.snippet.publishedAt` is used only
for public, processed ordinary videos and corroborated against any playlist publication fact.
Contradictory/missing/future times and live/premiere uncertainty wait. Completed and cancelled
records stay retained and are never requeued by rediscovery. First observation is sampled,
not the first website appearance; five-minute polling is not a ten-minute discovery guarantee.

Per-channel errors continue to the next channel. Authorization, project quota and service
errors gate all subsequent Data API calls, including membership and retries. A rejected access
token permits one refresh/retry. Rejected grants require reconnect. Quota waits until Pacific
midnight; transient service limits wait at least 60 seconds or the full numeric/HTTP-date Retry-After deadline. Gates and usage survive restart.
Errors are visible separately from an empty healthy scan.

Every request attempt costs one locally recorded unit for the four list methods, including
pagination, details and failures/retries. The local daily guard defaults to 10,000 and is
configurable with `EDISON_YOUTUBE_API_DAILY_BUDGET`. It cannot measure Google's actual remaining
project quota or other devices' usage. The ledger resets on Pacific calendar days.

For C included channels and S subscriptions, the stated healthy minimum is
`288*C + C + 4*max(1,ceil(S/50))` units/day: five-minute uploads scans, one daily uploads-cache
lookup per channel, and six-hour membership pages. A new-video detail batch in every channel
on every pass adds `288*C`; retries and explicit refresh add more. Thus even 35 channels can
exceed the default local daily budget. The interface exposes counts by endpoint, assumptions,
local cap, unknown project balance and overcapacity. It never silently widens the polling
interval or claims full five-minute coverage beyond the actual bounds.

Official references:
- https://developers.google.com/youtube/v3/determine_quota_cost
- https://developers.google.com/youtube/v3/docs/playlistItems
- https://developers.google.com/youtube/v3/docs/videos

The browser E2E suite `youtube-api.spec.ts` exercises real OAuth/host/workspace behavior with
external Google, captions and model fixtures and a controlled clock. It covers ordinary
processing, blocked models, caption cooldown, pause, channel failure, global failure/recovery,
uncertain timing and incomplete coverage.
