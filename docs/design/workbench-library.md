# Workbench library design

The workbench is a local Markdown library for YouTube manuscripts. Its purpose is to make a large subscription feed scannable and to preserve the person's attention for deliberate choices.

The main workspace has four library views: Inbox, To Read, Read, and All Manuscripts. Inbox is the default surface for newly prepared documents; moving an item to To Read is an explicit commitment of attention. Each document card shows source channel, preparation time, manuscript state and a short non-authoritative excerpt. The inspector shows provenance and document status, never embeds the manuscript as a second reader.

Manuscripts are portable Markdown documents. The two primary document actions are Copy Markdown Source and Open with Default Application. The workbench retains source links and timed transcript provenance so the document can lead back to YouTube when the person needs to verify it.

The visual language follows normal desktop conventions: neutral system materials, light and dark modes, system typography, restrained blue for selection and action, and no themed color cast. The interface uses translucent structural chrome for hierarchy and immediate press feedback; it respects reduced-motion preferences.

The workbench excludes embedded long-form reading, note-taking, annotation, and cloud synchronization.

## Search and retrieval

Default search covers manuscript title, channel identity and Markdown text. Timed raw transcripts stay outside ordinary search and are included only by an explicit user choice. Results rank by textual relevance and then publication time.

The complete first-release filter set is reading state, channel, publication time and preparation state. Every result card shows channel, publication time, reading state, preparation state and manuscript version. Selecting a result returns the person to that asset in the library and exposes its inspection and Markdown-handoff actions; it never opens an external application automatically.
