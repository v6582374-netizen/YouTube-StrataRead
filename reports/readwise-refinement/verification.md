# YouTube reading interface refinement — 2026-09-21

The app starts with Update paused, including when the previous session left it enabled. Automatic discovery and queue processing wait for manual resumption. Account subscription synchronization remains independent, and the explicit check-for-updates action still works.

Progress is the first and initially selected page. The heartbeat orb and its inner circle use radii 1.5 times their original size (reduced from the initial 2× adjustment after review); reduced-motion behavior remains intact. The separator above the queue tabs is removed.

Documents uses a continuous reading list beside an inline inspector, inspired by the supplied Readwise reference. Titles, excerpts, source metadata, dates, thumbnails (with document-cover fallbacks), and blue selection markers share a consistent hierarchy. The inspector retains source links, opening, copying, reading state, regeneration, and confirmed deletion. Narrow windows switch between the list and inspector.

## Verification

- Reproduced the startup problem in a real-host browser E2E test before the fix: persisted Update enabled caused immediate processing instead of a paused heading.
- Python host integration tests: 7 passed.
- Document metadata unit tests: 13 passed.
- Real-host progress flows: 4 passed across Chromium and WebKit at 800 / 1440 px, including manual resume, cancellation, pause after the current document, connectivity recovery, and reduced motion.
- Document inspector flows: 4 passed across Chromium and WebKit at 800 / 1440 px, including opening, marking read, confirmed deletion, and no horizontal overflow.
- Existing shared-view/settings and progress regressions: 5 passed at 800 / 1100 / 1440 px.
- Production frontend and local macOS application builds passed. Bundled privacy smoke and deep code-signature verification passed.
- Light/dark screenshots inspected and refined. The preview uses fixture documents; production thumbnails use the real video ID.

## Previews

- [Light](documents-light.png)
- [Dark](documents-dark.png)
