# Reimplement the Vegapunk YouTube slice by behavior

**Status: partially superseded by #31 (discovery and credential storage).** The original decision reimplemented only Vegapunk's verified Google OAuth, subscription-import and RSS-discovery behavior, preserving its protocol semantics, failure cases, contract tests and nested MIT attribution. It does not copy the OpenWorker host, FastAPI transport, old SQLite model, caption retrieval, translation path or UI. This kept the Python sidecar authoritative over the local workspace, Automic Vault and yt-dlp while retaining the upstream evidence that makes the YouTube integration trustworthy.

**Discovery decision superseded by issue #31.** Production discovery now uses only the official YouTube Data API uploads playlist and video details. The RSS implementation and fallback are removed. OAuth read-only scope and upstream attribution remain. See [official discovery](../architecture/youtube-discovery.md).
