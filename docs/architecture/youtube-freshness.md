# Automatic preparation: admission and completion

Automatic preparation has three independent conditions: current permission, age admission,
and runnable prerequisites. Auto Update defaults off. Its last explicit choice is saved in
SQLite before acknowledgement and retained through normal exit and crashes. Turning it off
stops further automatic claims and discovery passes; active work drains normally. Explicit
regeneration remains a content-specific manual request, never inferred from an old queue.

Ordinary videos enter automatic work only within the inclusive rolling 72 hours from their
public publication time. The timezone-aware public timestamp and retained numeric timestamp
must agree. Missing, contradictory and future times remain visible awaiting verification;
expiry retains the asset. Queue admission and the first real processing boundary both check
age. A reservation, classification, metadata probe or request pacing wait is not commencement.

The downloader records `commenced_at` immediately before its first actual subtitle request,
after metadata, subtitle selection and request pacing. With a usable retained transcript,
the boundary is the start of translation/composition. A matching transcript requires its
video-owned path, stored bytes, language and parseable content to agree. Live and premiere
sources without a reliable completion policy wait; this slice does not invent end times.

A commenced automatic task retains its completion eligibility through failure, cooldown,
ordinary retry and restart. Restart requeues interrupted commenced work, while every new
claim still requires Auto Update and obeys cooldown/retry limits. Cancellation and explicit
regeneration end the old task's eligibility. Existing manuscript versions and source assets
are never deleted by expiry, waiting or migration. Translation's existing source and request
fingerprints determine checkpoint reuse; incompatible output is not reported as recovered.

The repeatable startup migration treats legacy tasks as automatic. Old reservation timestamps
and stage labels cannot establish commencement. A verifiable video-matched usable transcript
can establish prior work for an unfinished task; an older completed manuscript does not grant
an unrelated regeneration exemption. Legacy cached format checks are revalidated. Migration
and its completion marker commit together, and reopening does not regrant cancelled work.

Discovery now uses only the official Data API; see [discovery](youtube-discovery.md).
Final live/premiere completion rules and fair cross-channel pagination remain subsequent work.

## Verification

`surfaces/gui/e2e/youtube-freshness.spec.ts` drives the real UI, authenticated host and temporary
persistent workspace. Only external discovery, YouTube metadata/captions and model responses
are controlled. Captions traverse real yt-dlp and local HTTP. A controlled domain clock covers
72h − 1s / 72h / 72h + 1s, admission versus first work, 100-hour recovery, every toggle/restart
combination, conservative legacy evidence, cancellation and checkpoint reuse. The existing
YouTube progress, Shorts, rate-limit and document suites remain regression coverage.
