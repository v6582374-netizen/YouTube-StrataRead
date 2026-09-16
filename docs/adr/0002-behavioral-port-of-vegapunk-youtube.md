# Reimplement the Vegapunk YouTube slice by behavior

**Status: accepted.** The product reimplements only Vegapunk's verified Google OAuth, subscription-import and RSS-discovery behavior, preserving its protocol semantics, failure cases, contract tests and nested MIT attribution. It does not copy the OpenWorker host, FastAPI transport, old SQLite model, caption retrieval, translation path or UI. This keeps the new Python sidecar authoritative over the local workspace, Automic Vault and yt-dlp while retaining the upstream evidence that makes the YouTube integration trustworthy.
