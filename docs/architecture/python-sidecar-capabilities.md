# Python sidecar capability contract

The Tauri renderer and host ask the Python sidecar for typed capabilities; they never access the local SQLite workspace, yt-dlp or Automic Vault directly.

The sidecar exposes six capability families:

- **Connection**: inspect, configure, authorize and disconnect the user-owned Google OAuth client.
- **Collection**: report subscriptions and start or observe the automatic OAuth-import and RSS-discovery cycle.
- **Library**: query local assets, move them between Inbox, To Read and Read, inspect provenance, create a new manuscript version and delete an entire asset.
- **Documents**: return raw Markdown for copying and prepare a stable local document reference for the host to open with the operating system's default application.
- **Activity**: expose a unified stream and snapshot of batch, acquisition, generation and retry work, including progress, bounded cost/volume facts and terminal failure causes. The host may request retry for one asset, retry all failed assets, or a drain pause.
- **Diagnostics**: expose the batch ledger and safe-to-display operational facts without exposing credentials or raw provider internals.

A batch runs automatically. Failed assets remain visible and are retried only by explicit user action. A drain pause prevents new work from beginning after the current asset reaches a stable terminal state. The activity center and individual library cards are two views of the same sidecar-owned job state.
