# Share a durable cooldown across YouTube acquisition

**Status: accepted.** A subtitle HTTP 429 previously marked one video unavailable and immediately allowed the next video to make requests. The workbench now shares persistent pacing and cooldown across RSS discovery, Shorts classification, and yt-dlp metadata/subtitle acquisition, because an access restriction can affect the entire session or network exit rather than an individual video.

Top-level requests are spaced by at least two seconds and video acquisitions by at least fifteen seconds. A 429 starts a fifteen-minute cooldown, doubling on repeated throttles to a six-hour policy maximum; a later server `Retry-After` deadline always takes precedence, including HTTP-date values. These are conservative product defaults, not official YouTube quotas or guarantees. Only a successful caption acquisition resets the throttle streak; successful RSS or metadata requests do not.

Cooldown is retained across restart and cannot be bypassed by refresh, resume, regeneration, or retry. A video receives at most three automatic retries after its initial throttled attempt before requiring manual action. Pauses, exclusions, cancellation, and manuscript retention continue to apply. Legacy subtitle-429 records are migrated once from unavailable to rate-limit waiting; genuinely missing captions and cancelled assets are left alone.

Metadata is extracted once and reused to download the chosen subtitle language. The workbench owns retry timing rather than allowing hidden immediate yt-dlp retries. The scope is this local workspace's workbench traffic; it cannot coordinate unrelated applications sharing the same network exit.
