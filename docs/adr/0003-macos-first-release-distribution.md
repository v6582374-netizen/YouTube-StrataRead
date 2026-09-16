# Release first on Apple Silicon macOS through GitHub Releases

**Status: accepted.** The first supported desktop release targets Apple Silicon Macs running macOS 14 Sonoma or later. It ships as a signed and notarized DMG through GitHub Releases, with a signed Tauri update manifest; the application discovers an update but installs it only after the person confirms. This gives the local-first product a trustworthy release path without multiplying Python-sidecar validation across Intel, Windows and Linux or introducing an independent distribution service.
