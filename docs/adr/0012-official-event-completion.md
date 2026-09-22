# 0012 — Gate live streams and Premieres on official completion evidence

Status: accepted for issue #32 (2026-09-22).

## Decision

An identified live stream or YouTube Premiere becomes eligible for automatic first work only after official video details establish completion. Its rolling, inclusive 72-hour start window uses `liveStreamingDetails.actualEndTime`. Ordinary videos continue to use corroborated public publication time. Neither discovery nor format classification counts as commencement.

Keep publication time, actual start/end, scheduled start, first uploads-list observation, local discovery and the latest official timing check separately. Never derive an end from duration, a scheduled end, subtitle availability or the local clock. A check timestamp describes evidence acquisition; it is not the event's end.

The completion gate requires a matching source channel, public/processed video, `snippet.liveBroadcastContent = none`, timezone-aware actual start/end, and `start <= end <= now`. Explicit `live` or `upcoming` without contradictory actual times waits for completion. Missing or contradictory evidence waits for timing verification. A valid future schedule is retained. A previously identified event cannot revert to publication-based admission when later details omit event fields.

The existing five-minute discovery scheduler revisits pending details with at most 50 video IDs per source pass, prioritizing the oldest checks. Previously discovered pending videos remain eligible for these checks after leaving the first uploads page. Existing authorization, request backoff, local budget, channel exclusions and Auto Update gates still apply. This does not add deep-page discovery or an alternative discovery service. A discovered waiting event is not itself an incomplete list scan; missing details and bounded list coverage remain separately reported.

The claim boundary and first subtitle/translation boundary apply the same age rule. Once real work has commenced, interruption retains age eligibility. Manual regeneration is age-exempt but still needs reliable event completion. Cancellation is never revived by discovery; restoration rechecks eligibility. Existing transcripts, translations and manuscript versions are retained.

## Official evidence and limits

The [Google YouTube v3 discovery schema](https://youtube.googleapis.com/$discovery/rest?version=v3) was retrieved on 2026-09-22. The relevant verbatim properties and schema revision are retained in [the evidence extract](../evidence/youtube-event-fields.json).

- `actualEndTime`: “The time that the broadcast actually ended. This value will not be available until the broadcast is over.”
- `actualStartTime`: “The time that the broadcast actually started. This value will not be available until the broadcast begins.”
- `scheduledEndTime` describes a scheduled end, including indefinite broadcasts; it is not an actual end.
- `liveBroadcastContent` distinguishes upcoming/active from `none`. `none` alone does not prove an identified event has finished.
- The schema says `liveStreamingDetails` is present for upcoming, live or completed broadcasts. It provides no dedicated Premiere discriminator and no guarantee that every historical Premiere exposes a complete broadcast record. We therefore do not label a video as a Premiere based on its title, duration or URL. Known events without reliable official evidence wait. There is no claim of universal retrospective Premiere detection.

Evidence here is official schema documentation, not an authenticated sample of every event category. E2E tests exercise controlled official response shapes through the real host; they do not establish universal platform field availability.

The existing platform Shorts classifier remains a separate gate. Its established player/canonical evidence is still required, including for short ordinary videos. It may flag possible event content but cannot supply or infer an official end time. Officially completed events may pass historical `isLiveContent` / `was_live` markers; active/upcoming player or subtitle metadata still defers work. No new webpage discovery or timing scrape is introduced.

## Verification

The real-host API E2E starts with UI OAuth/import and Auto Update, then follows official uploads discovery into a temporary durable workspace. Only external Google/keyring, platform responses, subtitle retrieval, the model and the clock are controlled. Coverage includes old announcements with recent actual ends, future/active events, missing/conflicting/future end times, off-page pending rechecks, the exact 72-hour boundary, Shorts uncertainty/exclusion, retained old documents, and crash recovery beyond the age window. The initial completed-event scenario reproduced the defect with zero prepared manuscripts before this change.
