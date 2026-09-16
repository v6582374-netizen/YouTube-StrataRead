# Desktop runtime and local-service boundaries

**Question.** Which thin desktop hosts can turn the existing Python YouTube-transcript CLI into a cross-platform, local-first knowledge workspace without creating a second application core?

**Scope.** This is a technology-selection brief, not a runtime decision. It assesses only hosts that can retain the present Python implementation of downloading, transcript processing, credential access and local storage. The current project already depends on `yt-dlp`, `keyring`, `platformdirs` and Python 3.10+; it is therefore a poor fit for a rewrite-first desktop strategy.

## The architectural constraint

The product should have one owner of knowledge-work state: a **Python core process**. It owns jobs, cancellation, transcript and annotation data, migrations, paths and access to credentials. The desktop host owns window lifecycle, a bundled web UI, desktop installation and update checks. The UI has a deliberately small capability API: submit/import a video, observe a job, read/write workspace entities, request an export, and ask for a user-mediated file selection.

Persist workspace data in a per-user SQLite file. Python's standard `sqlite3` module addresses a disk-backed database without a separate server process, which matches a local-first single-user workspace.[^sqlite] Keep provider tokens in the current `keyring` abstraction; its supported backends include macOS Keychain, Windows Credential Locker and Linux Secret Service/KWallet.[^keyring] This prevents a shell change from becoming a credential migration.

The preferred boundary is **IPC/bridge first, loopback HTTP only when it creates a concrete benefit**. A bundled UI has no need to discover a listening port or carry browser-style authentication simply to call its own core. Tauri can spawn a packaged Python sidecar; pywebview exposes a Python/JavaScript bridge and can serve static assets from its built-in server; Electron can supervise a child Python process.[^tauri-sidecar][^pywebview-architecture][^electron-process] If a later local API enables extensions or external automations, bind it to loopback only, require a launch-generated bearer capability, and treat it as an opt-in adapter rather than the core boundary.

## Viable thin hosts

| Host | Fit for this product | Operational shape | Main cost | Update and release story |
| --- | --- | --- | --- | --- |
| **Tauri 2 + packaged Python sidecar** | Strong product candidate | HTML/TypeScript UI in the system webview; Rust host launches a platform-specific frozen Python core and bridges explicit commands/events. | Two build ecosystems and per-target Python-sidecar packaging. | Tauri's updater supports static JSON or an update server and signed update artifacts.[^tauri-updater] |
| **pywebview + packaged Python application** | Strong migration candidate | One Python application hosts a native system webview, bundled frontend assets and a narrow JS API. | Web-engine behavior and packaging vary by OS; application must supply update policy. | pywebview documents py2app for macOS and PyInstaller for Windows/Linux; this makes installers possible but does not itself provide a managed updater.[^pywebview-freezing] |
| **Electron + packaged Python child process** | Viable only if Chromium consistency is an explicit product requirement | Chromium renderer and Node main process supervise a frozen Python core over IPC. | The largest runtime and three operational domains: Node, Chromium and Python. | Electron has a native updater for macOS and Windows but directs Linux distribution to the system package manager.[^electron-updater] |

### Tauri 2 + Python sidecar

Tauri is designed for HTML rendered in a webview with a Rust host and message passing between the webview and system-facing code.[^tauri-architecture] Its official sidecar model explicitly calls out bundled Python CLI applications or API servers, and `externalBin` packages a target-specific executable.[^tauri-sidecar] This preserves a modern transcript-reading and video-adjacent web UI while keeping `yt-dlp`, enrichment and persistence in the language that already owns them.

It is the best balance where the product needs a polished native desktop release but should remain local-first. The material complexity is real: each desktop target needs a compatible frozen Python executable, and Rust/Tauri becomes a release concern. This option earns that cost only if the team wants a durable desktop shell, controlled update flow and a clear capability boundary.

### pywebview + packaged Python application

pywebview is the shortest path from the present program because the desktop host and core stay in Python. It can use a JS API bridge with its own local asset server, avoiding a separately managed application server.[^pywebview-architecture] It also supports frontend build output from React or Vue as packaged data.[^pywebview-freezing]

It is a serious candidate for an early desktop release, especially if preserving delivery velocity matters more than strict rendering uniformity. The trade-off is platform variance: pywebview relies on WKWebView on macOS, WebKit2 on GTK Linux, and WebView2/other selectable renderers on Windows; WebView2 can require a runtime installation or redistribution.[^pywebview-web-engine] Treat testing across target operating systems as part of its cost, rather than assuming the browser surface behaves identically.

### Electron + Python child process

Electron offers the most predictable embedded Chromium surface for a rich web transcript interface. Its main process owns lifecycle and native APIs while each `BrowserWindow` has a separate renderer process, a natural place to keep the UI isolated from the Python worker.[^electron-process] It also exposes `safeStorage`, backed by platform cryptography: Keychain on macOS, DPAPI on Windows and Linux secret-store integrations where available.[^electron-safe-storage]

Those capabilities do not justify moving secrets out of Python: Electron documents a plaintext fallback where no Linux secret store exists, while the existing `keyring` boundary already centralizes this concern.[^electron-safe-storage][^keyring] Electron should enter the final comparison only if a controlled Chromium version, a Node desktop ecosystem, or web-media behavior proves decisive. Otherwise it adds the most runtime surface while leaving Python essential.

## Recommended shortlist for the next decision

1. **Tauri 2 with a frozen Python sidecar** — the leading candidate for a long-lived product shell. It supports a contemporary web interface, an explicit least-authority host/core boundary and a first-party signed-update path.
2. **pywebview with the Python core in-process** — the leading candidate for the smallest credible migration. It validates the workspace experience before committing to a Rust/TypeScript release system.

Electron remains a deliberately held reserve candidate, not a default. Its case should be made by a concrete media/UI compatibility requirement discovered in a prototype, not familiarity.

## Decisions the next ticket must make

- Whether the first release values minimum migration risk (pywebview) or a product-grade shell and updater from day one (Tauri).
- Whether the core runs in-process for the first release or is always a separately supervised process. Use an explicit service interface either way so the choice remains reversible.
- Which platform releases are supported at launch, and how each binary is signed, notarized and updated.
- Whether embedded YouTube playback is a required first-release workflow. This determines the amount of platform-webview compatibility testing needed before a runtime is selected.

[^sqlite]: [Python `sqlite3` documentation](https://docs.python.org/3/library/sqlite3.html), accessed 2026-09-16.
[^keyring]: [keyring backend documentation](https://keyring.readthedocs.io/en/latest/#using-keyring), accessed 2026-09-16.
[^tauri-architecture]: [Tauri Architecture](https://v2.tauri.app/concept/architecture/), accessed 2026-09-16.
[^tauri-sidecar]: [Tauri: Embedding External Binaries](https://v2.tauri.app/develop/sidecar/), accessed 2026-09-16.
[^tauri-updater]: [Tauri Updater](https://v2.tauri.app/plugin/updater/), accessed 2026-09-16.
[^pywebview-architecture]: [pywebview Application architecture](https://pywebview.flowrl.com/guide/architecture), accessed 2026-09-16.
[^pywebview-freezing]: [pywebview Freezing](https://pywebview.flowrl.com/guide/freezing), accessed 2026-09-16.
[^pywebview-web-engine]: [pywebview Web engine](https://pywebview.flowrl.com/guide/web_engine), accessed 2026-09-16.
[^electron-process]: [Electron Process Model](https://www.electronjs.org/docs/latest/tutorial/process-model), accessed 2026-09-16.
[^electron-safe-storage]: [Electron `safeStorage`](https://www.electronjs.org/docs/latest/api/safe-storage), accessed 2026-09-16.
[^electron-updater]: [Electron `autoUpdater`](https://www.electronjs.org/docs/latest/api/auto-updater), accessed 2026-09-16.
