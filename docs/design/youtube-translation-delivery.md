# YouTube Translation delivery

Current implementation: the original pinned translation-agent runs inside Edison. This replaces the earlier independently implemented bounded-context/glossary/JSON workflow. See [provenance and contract mapping](../upstream/translation-agent/README.md).

## Product and execution

The host calls the original `translate()` using Edison's selected model. Upstream owns the original initial → reflection → revision workflow, tiktoken counting, chunk sizing, full-source context and plain-text output. Its 1000-token splitting threshold and existing chunk-size behavior are retained. There is no new provider configuration in the desktop.

Settings → YouTube Translation exposes all 13 active templates: three upstream system templates, eight single/multichunk and regional task variants, and two host composition templates. Original `{variable}` placeholders are validated. Country selects the original regional review branch. Restore changes remain drafts until saved. “生成规则” opens the same settings.

A complete translation, reading manuscript and provenance are stored in each immutable manuscript-version directory. Composition follows translation and adds headings/removes filler; it must not summarize content away. Chinese-only source uses deterministic OpenCC conversion before composition; mixed-language source follows upstream translation. Existing documents are not regenerated automatically.

## Durability and budgets

Attempts freeze model/settings and persist completed requests plus cumulative usage. Ordinary retries resume that snapshot. Explicit regeneration starts with current settings and reuses retained subtitles. Interrupted jobs become visibly failed; source material and old documents remain intact.

V1 JSON templates are retained as an inspectable archive. Their composition instruction and budgets migrate; incompatible translation templates use upstream defaults. V1 checkpoints are retained until the user explicitly regenerates, never misread as an upstream attempt.

Defaults remain 240 host invocations and 1,500,000 cumulative budget tokens. The earlier replacement-workflow calibration is obsolete. Upstream repeats full-source context, so long videos can exhaust the budget or provider context window sooner. Settings permit changing the budget; the workflow does not silently truncate source context to fit. Admission reserves conservative input/output usage; actual reported usage reconciles the ledger. Missing usage stays conservative. This is not an exact price limit.

Budget exhaustion discards the current unfinished checkpoint, prevents automatic retry and preserves subtitles and old documents. Transient failures receive at most two workflow retries; HTTP 402 is visible without retry. Router/SDK retries remain provider-owned. Empty, visibly shortened and provider-truncated outputs are rejected; composition checks Arabic-number retention. These heuristics cannot prove semantic completeness.

## Packaging and validation

The shared translation package and prompt data are in Edison's wheel and frozen sidecar. The cl100k tokenizer cache and OpenCC dictionaries are bundled for offline startup. No root clone or runtime source archive is used. The optional original Gradio UI is retained as a compatibility module; its conflicting dependencies are isolated from the desktop.

Validation covers upstream source preservation and request/result parity, shared model routing, every prompt variant, short/long and regional flows, failure/retry/budget behavior, settings migration, translation retention, and browser settings/document flows at three widths. The frozen-sidecar smoke scenario uses a local model fixture with isolated workspace/state, not personal credentials.

Real linguistic quality remains unverified. The earlier real-provider comparison received HTTP 402 from the configured model; successful fixture runs do not establish quality improvement. Resume same-source comparison with a usable provider, inspecting omissions, numbers, names, negations and terminology before readability.

Validated on 2026-09-19: 58 related backend checks, 12 React component checks and three browser viewport scenarios passed. The frozen sidecar processed short English, multichunk English and Traditional Chinese through 17 local-fixture model requests, saving complete translation artifacts. The optional original UI returned HTTP 200. Python wheel/sdist and the macOS release bundle built successfully; the restarted Edison process has a visible native window and a responding bundled backend.
