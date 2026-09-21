# Exclude platform Shorts before manuscript preparation

**Status: accepted.** Edison excludes YouTube-classified Shorts from new preparation, including the existing pending queue, while retaining ordinary short videos and all existing manuscripts. Because public YouTube metadata has no authoritative Shorts flag, uncertain classifications wait and retry rather than acquire subtitles or generate manuscripts; this deliberately trades availability for preventing unwanted automatic processing.

Duration, aspect ratio, title hashtags and the spelling of an incoming URL are not authoritative classifications. Platform page signals remain an external dependency and cannot justify an unconditional promise of perfect classification. Retained exclusion decisions prevent a subscription refresh or restart from reintroducing a known Short; exclusion is distinct from user cancellation, failure and deletion.

The check precedes subtitle acquisition. Pending classifications retry no sooner than 15 minutes later while automatic processing is running, respect pauses and channel exclusions, and remain cancellable. Existing manuscripts stay readable and can still be explicitly regenerated.

Sources: [YouTube Shorts rules](https://support.google.com/youtube/answer/15424877?hl=en), [YouTube video resource](https://developers.google.com/youtube/v3/docs/videos), [search duration filters](https://developers.google.com/youtube/v3/docs/search/list).
