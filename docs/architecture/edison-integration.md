# Edison: one desktop host, independent YouTube library

Edison uses Openworker's `surfaces/gui` Tauri client and `coworker.server` process. The root repository now includes the upstream source directly; it is not a nested checkout. Import provenance and MIT attribution are retained in `docs/upstream/openworker`.

The YouTube sidebar entry uses the YouTube brand mark. Its main view is `YouTubeView`, not an embedded browser or the old independent application shell. All library, connection, activity and document actions travel through the host's existing launch-token authenticated API at `/v1/youtube/capability`. This supersedes the separate stdin sidecar transport for the Edison client; there is no additional server or listening port.

`HostManuscripts` calls the host's `SessionManager.provider_complete` using its current model. Provider selection, API keys, custom endpoints and model switching remain owned by the host. YouTube keeps queued assets pending when that model is not configured. Google OAuth still uses the existing Automic Vault adapter. No model secret is copied into the YouTube workspace.

YouTube retains its original workspace path and SQLite/file model, so opening Edison finds existing assets. The worker is started lazily on first YouTube access, continues across sidebar navigation and stops taking new work during shutdown. Its workload remains bounded and drain-pausable. The UI polls sequentially without overlapping requests. The main host authentication applies equally to the new endpoint.

The app is named Edison and uses the official mymind thinking-guy icon selected by the owner. The upstream auto-update channel is disabled to prevent an Openworker release from replacing Edison. Local rebuilds are the update path.
