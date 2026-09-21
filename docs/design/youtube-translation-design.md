# YouTube Translation — design interview

Status: superseded in part by the owner's subsequent source-preservation requirement. 2026-09-19.

## Governing integration decision

The owner requires actual reuse of the complete upstream implementation, business modules and contracts, with native relocation allowed. The original bounded-context/glossary/JSON-unit implementation is removed. Round 2 Q4 below records historical agreement only: upstream now owns tokenization, splitting, full-source context, stage ordering and plain-text output. The remaining product requirements still apply. No independent root checkout remains; see [source provenance and relocation](../upstream/translation-agent/README.md).

## Established intent

- Integrate the locally supplied `translation-agent` into the YouTube workflow.
- Make its built-in translation instructions human-editable; consider a dedicated YouTube Translation area in Settings.
- Retain the established Edison model/configuration ownership and Simplified-Chinese manuscript target unless the owner explicitly changes them.
- Preserve source material and existing manuscript versions.

## Verified starting point

At the start of the interview, the host made one model call combining translation and manuscript composition (`coworker/server/youtube.py`, `HostManuscripts.generate`). That editable instruction was therefore not translation-only.

The supplied upstream checkout is `e0fc605acbb5d78cb7a58a98bc8bd8f0056df49c`. Its README describes initial translation, reflection and revision. It explicitly calls itself an immature demonstration and reports mixed evaluation outcomes. More steps are a testable quality hypothesis, not a guarantee of better translation.

Read-only upstream inspection located the workflow and built-in prompts in `src/translation_agent/utils.py`. Single-chunk translation uses three model calls. Long inputs use three calls per chunk with full-source context, creating significant token/context implications for long videos. The complete core source has been read: three unique system templates and eight user-template variants cover the three stages, chunking and region-specific review. Templates are hardcoded; there is no editing/version store. The provider is a global OpenAI client using OPENAI_API_KEY and a gpt-4-turbo default. There is no built-in coverage/truncation validation or resumable-stage storage. Reuse must retain the MIT attribution (Andrew Ng, 2024).

## Round 1 — accepted by the owner

- Preserve a complete faithful translation separately from the final reading manuscript.
- Retain manuscript composition, limited to removing spoken filler and adding hierarchical headings; do not summarize away content or reorder the argument.
- Judge improvement by completeness and preservation of meaning, numbers and terminology first, then natural Chinese. Compare the old and new workflows on the same real subtitle material rather than assuming more calls mean better results.
- Prioritize quality and accept additional latency and model cost, subject to explicit resource boundaries. Numeric limits and enforcement were settled in subsequent rounds and implementation calibration.

See ADR-0005 for the durable translation/manuscript boundary.

## Round 2 — accepted by the owner

- Q4: Segment long videos into continuous semantic units in source order. Use bounded neighboring context and a document-wide terminology glossary with initial translation, review and revision; avoid repeating the full transcript for each chunk/stage.
- Q5: Pure Simplified-Chinese input skips translation and receives limited manuscript composition. Non-Chinese and mixed-language input follows translation. Traditional Chinese converts to Simplified Chinese without discretionary rewriting.
- Q6: Settings has a dedicated YouTube Translation section grouped into initial translation, review, revision and manuscript composition. All active system/user templates are editable, with required-placeholder validation and restore-default support. The existing generation-rules entry opens this same configuration.
- Q7: On exceeding the resource budget, discard rather than pause and request more budget. The owner explicitly rejected the pause-and-resume recommendation. Discard/retry scope is settled in round 3 below; numerical defaults are calibrated during implementation.

## Round 3 — accepted by the owner; shared understanding confirmed

- Define discard as abandoning the current attempt and its incomplete output, preserving source subtitles and previous successful versions, displaying an exceeded-budget status, and preventing automatic retry of that attempt.
- Set editable per-video resource limits; use model-call/token limits rather than currency estimates because configured providers may not expose reliable prices. Owner accepts determining concrete defaults through measurement on representative long material during implementation.
- Bound transient network/rate-limit retries; never publish truncated or incomplete output as a completed manuscript. Completed stages survive ordinary failures.
- Snapshot prompts/model selection when an attempt starts. Settings changes affect future attempts; existing manuscripts do not regenerate automatically. Preserve legacy custom generation rules as manuscript-composition instructions, subject to the accepted fidelity boundary.
- Validate on the same real transcripts: a short English video, a long interview, mixed Chinese/English, and Simplified/Traditional Chinese. Evaluate completeness, numbers, names and terminology, then readability; a visibly truncated manuscript fails acceptance.

## Decision tree

1. Desired outcome: faithful translated speech versus a structured reading manuscript; relationship between the two.
2. Acceptance: errors that must improve, representative source material and comparison criteria.
3. Priority: quality versus processing time and cost.
4. After 1–3: long-video segmentation/context policy, treatment of Chinese input, and which stages use which model settings.
5. After stage ownership: editable prompt catalog, structural placeholders, defaults, saving/versioning and how it relates to the existing generation-rules entry.
6. After workflow and budget: failure/retry semantics, retained intermediate results, and rollout to old/new documents.

See [delivery and validation](youtube-translation-delivery.md) for the current implementation, budget limits and remaining live-provider limitation.

The owner confirmed the shared understanding and authorized implementation. The durable translation/manuscript boundary is recorded in ADR-0005; reversible UI choices do not receive separate ADRs.

Ordinary retries preserve the attempt’s prompt/model snapshot; explicit regeneration starts with current settings. Interrupted attempts become visibly failed on host restart, retaining completed stages for manual retry.
