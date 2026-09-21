# Publish manually installed macOS releases

**Status: accepted (2026-09-21).** The owner requested committing and pushing every workspace change, including unrelated work, and publishing the first GitHub Release. This supersedes ADR 0004's source-only GitHub policy.

The first Edison release uses the existing desktop version **0.2.1** and targets Apple Silicon on macOS 14 or later. Release assets contain a locally built application, a drag-to-Applications DMG and SHA-256 checksums. Installation and future upgrades are manual; this does not introduce an updater service.

The application is ad-hoc signed, without Apple Developer ID notarization. The release notes disclose this limitation. A GitHub release does not imply Apple notarization or compatibility with Intel Macs, Windows or Linux.

The legacy PyPI workflow becomes manually triggered. A desktop release tag must not implicitly publish the renamed Python package to a separate distribution channel.
