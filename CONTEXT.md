# Context: YouTube Reading Workbench

## Glossary

- **Subscription source**: A YouTube channel feed imported from the person's connected YouTube account and refreshed locally; a manually managed channel list may become a later supplement.
- **Candidate**: A newly discovered subscription update that has not yet earned the user's reading time.
- **Batch manuscript preparation**: The deliberate choice to acquire content and generate a full Chinese deep-reading manuscript for every discovered update before the person chooses what to read.
- **Manual queue review**: The first-release selection model: a person browses prepared manuscripts and decides which deserve attention; no autonomous relevance ranking is applied.
- **Triage**: A later, optional AI-assisted prioritization of prepared manuscripts. It may suggest priorities but never decides what the person must read.
- **Inbox**: The complete local set of newly prepared manuscripts awaiting a person's review.
- **Reading queue**: The set of manuscripts the person deliberately moves from the inbox to read later; opening one begins reading and completing it preserves it as read history.
- **Reading state**: One of inbox, to-read, reading or read; it organizes attention without controlling retention.
 The short, human-approved set of candidates that deserve deeper attention.
- **Retention**: Every prepared manuscript and its source materials remain locally until the person explicitly deletes them; the system never purges assets by age, unread status or storage policy.
- **Knowledge asset**: A locally owned record derived from a selected YouTube video, containing the source identity, timed transcript, deep-reading manuscript, generation record and reading state.
- **Acquisition**: Bringing a selected YouTube video's metadata and transcript into the local library.
- **Enrichment**: Optional AI-assisted transformations of a knowledge asset, such as cleaning, translating, structuring, summarizing, or indexing. Enrichment never replaces the source transcript.
- **Deep-reading manuscript**: The primary user-facing enrichment of a selected knowledge asset: a coherent, layered document designed for sustained reading and thought, rather than a raw transcript or a summary card. It faithfully removes spoken redundancy, translates and structures the source without adding facts or opinions. It is presented in Simplified Chinese by default, translating non-Chinese sources automatically.
- **Source trace**: The preserved link between a deep-reading manuscript and its original video and timed transcript, allowing the reader to verify a passage on demand.
- **Manuscript version**: An immutable deep-reading manuscript produced for one knowledge asset. A person may manually create a later version while retaining earlier versions for comparison and rollback.
- **Generation record**: The retained account of how a manuscript was produced, distinct from its source materials and current manuscript output.
- **Local-only workspace**: A single-machine knowledge store. No product cloud copy or synchronization service exists; all durable assets remain under the person's local control.
- **Credential boundary**: OAuth and model credentials reside only in the local Automic Vault. They are outside the local workspace and excluded from its assets and exports.
- **Workspace**: The local, desktop-facing environment in which a person monitors subscriptions, prepares manuscript batches, chooses a reading queue, and reads or annotates knowledge assets.
- **Migration boundary**: The smallest self-contained YouTube capability that can move from Vegapunk into this product without importing unrelated research-agent behavior.
- **Preparation state**: The operational state of a discovered update: discovered, queued, acquiring, generating, ready, unavailable or failed. An unavailable or failed asset remains visible with its reason; no manuscript is fabricated without a source transcript.
- **Deletion**: An explicit terminal action that permanently removes the entire local video asset, including every manuscript version, transcript and source record.
- **Markdown handoff**: The workbench does not embed a document reader. Each prepared manuscript is stored as Markdown and can be copied as raw Markdown or opened with the operating system's default application.
