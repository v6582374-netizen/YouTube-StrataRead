# YouTube StrataRead

🌐 [中文](README.md) · English

A terminal tool that turns any YouTube video into a "deep-readable" Bionic
Reading knowledge document.

1. **Fetch** the raw SRT subtitles from YouTube.
2. **Outline** them with AI (BYOK) via a **single user-editable prompt** that
   handles translation, redundancy cleanup, and hierarchical outlining in one
   shot — producing a Markdown with just the body text. **Deep thinking is
   enabled by default across every provider.**
3. **Read** the result in the terminal with Bionic Reading emphasis (first
   letters of each word bolded). After finishing one leaf you are auto-advanced
   to the next; parents get a check mark once all descendants are read, and a
   sticky bottom progress bar tracks the whole document.

Four provider families are supported: **OpenAI**, **Anthropic (Claude)**,
**Google Gemini**, and **Compat** (any OpenAI-compatible third-party relay).
Only YouTube URLs are supported in this version; local subtitle files are not.

---

## 1. Requirements

- macOS / Linux (Windows works via WSL).
- Python 3.10+ (3.11 recommended).
- Network access to YouTube and your chosen provider's API.
- `ffmpeg` is **not** required — we only download subtitles.

---

## 2. Installation

### Recommended: pipx (global install, no manual venv)

```bash
pipx install youtube-strataread
by --help
```

### From GitHub (latest dev version)

```bash
pipx install "git+https://github.com/v6582374-netizen/YouTube-StrataRead.git"
```

### Local development

```bash
# using uv
uv venv --python 3.11 .venv
uv pip install -e '.[dev]'

# or plain pip
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'

source .venv/bin/activate
by --help
```

---

## 3. Try the bundled sample first (no API key needed)

```bash
by example                  # manual mode (Tab-to-advance)
by example --mode stream    # auto streaming mode
by example --path           # print the sample location on disk
```

The sample is a pre-processed interview outline bundled inside the package —
ideal for evaluating the reader UX, including the new bottom-anchored layout
and breadcrumb/progress footer, without touching any cloud API.

---

## 4. Configure a provider

### The four flavours

| Provider    | Purpose                                      | Required config          |
| ----------- | -------------------------------------------- | ------------------------ |
| `openai`    | OpenAI's own API                             | `--key`                  |
| `anthropic` | Anthropic Claude                             | `--key`                  |
| `gemini`    | Google Gemini                                | `--key`                  |
| `compat`    | Any OpenAI-compatible third-party relay      | `--key` + `--base-url`   |

### Commands

```bash
by config set openai --key sk-...
by config set anthropic --key sk-ant-...
by config set gemini --key AIza...
by config set compat --key sk-... --base-url https://your-relay/v1
# optional: override the default model
by config set anthropic --key sk-ant-... --model claude-sonnet-4-5-20250929

by config use openai        # switch default provider (initial: anthropic)
by config show              # inspect every provider (keys are masked)
by config get gemini        # inspect one provider
```

### Where keys live (priority order)

1. System **keyring** (macOS Keychain / Linux Secret Service).
2. Environment variables: `BY_OPENAI_API_KEY`, `BY_ANTHROPIC_API_KEY`,
   `BY_GEMINI_API_KEY`, `BY_COMPAT_API_KEY`.
3. Config file: `~/Library/Application Support/youtube-strataread/config.toml`
   (macOS) / `~/.config/youtube-strataread/config.toml` (Linux).

### Deep thinking (on by default for every provider)

Each provider is wired to its own "think hard" path:

- **OpenAI** — for o-series / GPT-5 / anything the heuristic recognises as a
  reasoning model, `reasoning_effort="high"` is passed automatically.
- **Anthropic** — Claude models auto-receive
  `thinking={"type": "enabled", "budget_tokens": 16000}` with
  `max_tokens=32000` and a forced `temperature=1.0` (Anthropic requirement).
- **Gemini** — Gemini 2.5 models include
  `thinking_config(thinking_budget=-1)` (dynamic budget; the model decides).
- **Compat** — if the model name matches `o1/o3/o4/gpt-5/deepseek-reasoner/
  thinking/r1`, `reasoning_effort="high"` is forwarded; otherwise we leave
  things alone so strict relays don't 400.

Every provider streams the response, so the progress bar ticks in real time
and you can see deltas arrive instead of staring at a frozen spinner.

---

## 5. Core workflow

### 5.1 One-shot: `by run`

```bash
by run https://www.youtube.com/watch?v=XXXXXXXXXXX
```

Three interactive menus appear in order:
1. **Provider** — pick one of the four.
2. **Model** — a per-provider catalog plus a "custom..." entry.
3. **Prompt** — every `.md` file under the prompts directory (default
   `prompts.md` pinned first).

After that: SRT download → AI → reader. Pass `--mode stream` for auto
streaming.

### 5.2 Only download: `by fetch`

```bash
by fetch https://www.youtube.com/watch?v=XXXXXXXXXXX
# produces: <cwd>/<video-slug>/raw.srt
```

### 5.3 Download + AI: `by process`

```bash
by process https://www.youtube.com/watch?v=XXXXXXXXXXX
```

Layout:

```
<cwd>/<video-slug>/
├── raw.srt              # yt-dlp original subtitle
└── <video-slug>.md      # AI final draft
```

Useful flags:

- `--provider openai|anthropic|gemini|compat` (skips the interactive picker)
- `--model <name>`
- `--lang en` (preferred source subtitle language)
- `--overwrite` / `--suffix` (folder collision strategy)

### 5.4 Read: `by read`

```bash
by read <slug-folder>/                  # auto-discovers the .md inside
by read <slug-folder>/<slug>.md         # or pass the .md directly
by read <slug>.md --mode stream         # auto streaming
by read <slug>.md --mode stream --cpm 500
```

---

## 6. Reader controls

Both modes share the same hierarchical picker and both apply Bionic Reading
(first-letter-bold) styling.

### 6.0 What's new in the reader

- The bottom of the terminal is now a three-row reserved area: aurora progress bar on the last row, breadcrumb above it, and one fixed spacer row above both.
- The body is bottom-anchored above that reserved area: the active sentence always hugs the spacer row and older content is pushed upward.
- Body output is now append-only. Auto-advance, jump-reading, revisits, and re-reading all keep stacking visible text upward instead of clearing prior content.
- Entering a new section writes the Markdown heading itself into the body stream, so sequential reading gradually reconstructs more of the original md structure.
- The active sentence is rendered in champagne; once you move on, the previous sentence returns to the terminal's default foreground.
- Sentence splitting is more natural for English and CJK punctuation, including commas, semicolons, and closing quotes.

### 6.1 Shared hierarchical selector

```
(root)

▶ 1) [ ] Why is AI a durable investment theme?
  2) [✓] How to separate signal from noise?

↑/↓ or digits to pick, Enter/Tab to enter, Esc/b to go up, h to root, q to quit
```

- Digit keys `1..9`: jump directly.
- `↑ / ↓`: move cursor.
- `Enter / Tab`: descend; if leaf, enter body reading.
- `Esc / b`: step up one level.
- `h`: jump to root.
- `q`: quit (progress is saved).
- `[✓]` marks a node whose entire leaf subtree has been read (parents bubble
  up automatically).

### 6.2 Auto-advance

- After you finish a leaf, the navigator **automatically yields the next leaf
  in DFS order** — no menu in between.
- When the last sibling at one level is done, it crosses the boundary up to
  the next parent sibling.
- After the whole document is read you are bounced back to the root menu with
  everything `[✓]`.
- Press `Esc / b` during reading to exit auto-advance and return to the
  parent menu of the current leaf.
- The menu lives on an alternate screen, so opening it never erases the
  accumulated body history on the main reading screen.

### 6.3 Mode A — manual Tab (default)

- `Tab` — reveal the next sentence (typed out char-by-char + Bionic bold).
- `Shift+Tab` — re-show the previous sentence.
- `Space` — jump to the last sentence of the current leaf.

### 6.4 Mode B — auto stream

- `Space` — pause / resume.
- `+` / `-` — speed tier (×0.5 / ×0.75 / ×1 / ×1.5 / ×2).
- `Tab` — skip to the end of the current sentence and move on.
- `Esc` — terminate and go back up.
- `--cpm N` / `--wpm N` — override the base speed (default 300 CPM).

### 6.5 Progress persistence

Progress is saved at:

```
~/Library/Application Support/youtube-strataread/state/progress/<docHash>.json   # macOS
~/.local/state/youtube-strataread/progress/<docHash>.json                        # Linux
```

### 6.6 Footer breadcrumb

- The breadcrumb has its own dedicated row and shows the current leaf path, for example `Parent / Current`.
- When the terminal is narrow, truncation happens from the left so the current section stays visible.
- The progress bar sits on a separate row, so narrow windows do not force the breadcrumb and progress to compete for width.

---

## 7. The prompt system

### 7.1 One prompt, one call

YouTube StrataRead feeds the full transcript to the LLM **once** with a single
system prompt. The model handles translation, denoising, and hierarchical
outlining in one shot — no validators, no self-repair, no multi-step
orchestration.

### 7.2 Editable and switchable

- Prompts live at `~/Library/Application Support/youtube-strataread/prompts/`
  (override via `BY_PROMPTS_DIR`).
- The default file `prompts.md` is materialised on first run — its content is
  the author's original analysis blueprint, byte-for-byte.
- **Adding a new prompt**: drop any `.md` file (e.g. `podcast.md`,
  `lecture.md`) into the directory. The next `by run` will list it in the
  picker automatically — no CLI step required.

### 7.3 Commands

```bash
by prompts path       # print the full path of prompts.md
by prompts show       # dump the current prompts.md
by prompts reset      # restore defaults
open "$(dirname $(by prompts path))"   # open the directory in Finder
```

---

## 8. Command cheatsheet

| Command                                             | Purpose                                      |
| --------------------------------------------------- | -------------------------------------------- |
| `by example [--mode stream]`                        | Read the bundled sample (no API key needed) |
| `by fetch <URL>`                                    | Download subtitles only                      |
| `by process <URL>`                                  | Download + AI (interactive picker)           |
| `by run <URL>`                                      | `process` + `read` in one shot               |
| `by read <MD-or-slug>`                              | Open the reader                              |
| `by config set <provider> --key X [--base-url Y]`   | Save key / base_url / model for a provider   |
| `by config use <provider>`                          | Change the default provider                  |
| `by config show`                                    | Inspect every provider                       |
| `by prompts path \| show \| reset`                  | Manage the prompt file                       |

Global flags: `-v/--verbose`, `--no-color`, `--config PATH`.

---

## 9. Artefact locations

- **AI output**: `<cwd>/<video-slug>/{raw.srt, <slug>.md}`
- **Config file**: `~/Library/Application Support/youtube-strataread/config.toml`
- **Prompts dir**: `~/Library/Application Support/youtube-strataread/prompts/`
- **Reader progress**: `~/Library/Application Support/youtube-strataread/state/progress/`
- **Crash log**: `<slug>/.by-crash-<timestamp>.log` (only on AI failure)
- **Bundled sample**: `by example --path` prints its location

---

## 10. FAQ

**Q: `zsh: command not found: by`** — not installed or venv not active.
Recommended: `pipx install youtube-strataread`, or `source .venv/bin/activate`.

**Q: `missing API key for provider 'xxx'`** — run
`by config set <provider> --key <KEY>` or export
`BY_<PROVIDER>_API_KEY`.

**Q: `compat provider needs a base_url`** — run
`by config set compat --key ... --base-url https://your-relay/v1`.

**Q: The video has no subtitles** — the tool prints
`no subtitles ...` and exits cleanly; no output directory is created.

**Q: AI fails but `raw.srt` is already on disk** — a
`.by-crash-<timestamp>.log` lands in the output folder; re-run with
`--overwrite`.

---

## 11. License

MIT.
