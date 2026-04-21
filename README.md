# YouTube StrataRead

🌐 中文 · [English](README.en.md)

一个终端工具，把任意 YouTube 视频转成一份「可思考、可深读」的 Bionic Reading 知识文档。

1. **抓取**：一条命令从 YouTube 下载原始 SRT 字幕。
2. **整理**：调用你自己的大模型 API（BYOK），用**一份可自定义的 prompt** 一次性完成翻译 + 去冗 + 分层标题化，生成只含正文的 Markdown。**全部 provider 默认启用深度思考**。
3. **阅读**：在终端以 Bionic Reading（词首字母加粗）风格逐句阅读；读完一个叶子自动跳到下一个，父标题自动打钩，并实时显示底部总进度条。

支持四类 Provider：**OpenAI**、**Anthropic (Claude)**、**Google Gemini**、**Compat（任意 OpenAI 兼容的第三方中转）**。仅支持 YouTube URL，本版本暂不支持本地字幕文件。

---

## 1. 系统要求

- macOS / Linux（Windows 建议用 WSL）。
- Python 3.10+（推荐 3.11）。
- 网络可访问 YouTube 以及你选择的 Provider 的 API。
- 无需 `ffmpeg`（只下载字幕）。

---

## 2. 安装

### 推荐：pipx（全局安装，无需手动管理虚拟环境）

```bash
pipx install youtube-strataread
by --help
```

### 从 GitHub 安装（最新开发版）

```bash
pipx install "git+https://github.com/v6582374-netizen/YouTube-StrataRead.git"
```

### 本地开发

```bash
# 使用 uv
uv venv --python 3.11 .venv
uv pip install -e '.[dev]'

# 或使用 pip
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'

source .venv/bin/activate
by --help
```

---

## 3. 先看一眼内置样例

不用配任何 key 就能体验阅读器：

```bash
by example                  # 默认 manual 模式（Tab 推进）
by example --mode stream    # 自动流式阅读
by example --path           # 打印样例路径
```

样例是一份预处理好的采访节目 Markdown（来自一个 YouTube 视频），展示完整的分层结构、Bionic Reading 效果，以及新的高亮/进度交互。

---

## 4. 配置 Provider

### 四种 Provider

| Provider    | 说明                                     | 需要配置               |
| ----------- | ---------------------------------------- | ---------------------- |
| `openai`    | OpenAI 官方 API                           | `--key`                |
| `anthropic` | Anthropic Claude                         | `--key`                |
| `gemini`    | Google Gemini                            | `--key`                |
| `compat`    | 任意 OpenAI 兼容的第三方中转 / 代理       | `--key` + `--base-url` |

### 命令

```bash
by config set openai --key sk-...
by config set anthropic --key sk-ant-...
by config set gemini --key AIza...
by config set compat --key sk-... --base-url https://your-relay/v1
# 可选：改默认模型
by config set anthropic --key sk-ant-... --model claude-sonnet-4-5-20250929

by config use openai        # 切换默认 Provider（初始为 anthropic）
by config show              # 查看全部 Provider 当前配置（key 脱敏）
by config get gemini        # 查看单个 Provider
```

### 密钥存储（优先级从高到低）

1. 系统 **keyring**（macOS Keychain / Linux Secret Service）。
2. 环境变量 `BY_OPENAI_API_KEY`、`BY_ANTHROPIC_API_KEY`、`BY_GEMINI_API_KEY`、`BY_COMPAT_API_KEY`。
3. 配置文件 `~/Library/Application Support/youtube-strataread/config.toml`（macOS）/ `~/.config/youtube-strataread/config.toml`（Linux）。

### 深度思考（全部 Provider 默认开启）

每家 Provider 都自动走各自的「长思考」路径：

- **OpenAI**：对 o-series / GPT-5 / 任何命中启发式的推理模型，自动传 `reasoning_effort="high"`。
- **Anthropic**：Claude 系列自动传 `thinking={"type": "enabled", "budget_tokens": 16000}`，`max_tokens=32000`，强制 `temperature=1.0`（官方硬性要求）。
- **Gemini**：Gemini 2.5 系列自动附加 `thinking_config(thinking_budget=-1)`（动态：模型自主决定思考时长）。
- **Compat**：按模型名启发式，命中 `o1/o3/o4/gpt-5/deepseek-reasoner/thinking/r1` 即加 `reasoning_effort="high"`；不命中则保持原样。

所有 Provider 都使用**流式**请求，进度条实时显示已接收字符数，不会误以为卡死。

---

## 5. 核心工作流

### 5.1 一键跑完：`by run`

```bash
by run https://www.youtube.com/watch?v=XXXXXXXXXXX
```

会依次弹出三级交互式菜单：
1. **Provider** — 从 4 种里选。
2. **Model** — 每家都列出常见模型 + 「自定义」。
3. **Prompt** — 列出 `prompts/` 目录下所有 `.md` 文件，默认 `prompts.md` 排第一位。

选完后下载字幕 → 跑 AI → 进入阅读器。加 `--mode stream` 走自动流式阅读。

### 5.2 只抓字幕：`by fetch`

```bash
by fetch https://www.youtube.com/watch?v=XXXXXXXXXXX
# 产物：<当前目录>/<视频标题-slug>/raw.srt
```

### 5.3 下载 + AI 处理：`by process`

```bash
by process https://www.youtube.com/watch?v=XXXXXXXXXXX
```

产物：

```
<当前目录>/<视频标题-slug>/
├── raw.srt              # 原始字幕
└── <视频标题-slug>.md   # AI 终稿
```

常用参数：

- `--provider openai|anthropic|gemini|compat`（会跳过交互）
- `--model <名称>`
- `--lang en`（指定源字幕语言）
- `--overwrite` / `--suffix`（目录冲突策略）

### 5.4 阅读：`by read`

```bash
by read <slug 目录>/                    # 自动找里面的 .md
by read <slug 目录>/<slug>.md           # 直接传 md
by read <slug>.md --mode stream         # 自动流式
by read <slug>.md --mode stream --cpm 500
```

---

## 6. 阅读器操作说明

两种模式都使用同一套「层级下钻选择器」，并都带 Bionic Reading（词首字母加粗）渲染。

### 6.0 本次阅读器增强

- 底部常驻总进度条：按整篇文档的可见字符数实时推进。
- 鼠标悬停句子会变灰，左键点击可切换高亮。
- 键盘 `h` 可作为无鼠标环境下的高亮快捷键。
- 退出阅读器时，如存在高亮，会在当前文档目录自动生成 `highlights.md` 摘录文件。
- 中英/CJK 断句规则更细，逗号、分号、引号等场景阅读节奏更自然。

### 6.1 层级选择（共享）

```
(root)

▶ 1) [ ] 为什么 AI 是可承载的投资主题？
  2) [✓] 如何识别信号与噪声？

↑/↓ 或数字键选, Enter/Tab 进入, Esc/b 返回, h 回根, q 退出
```

- 数字键 `1..9`：直接选择。
- `↑ / ↓`：移动光标。
- `Enter / Tab`：进入当前节点；若为叶子则进入正文阅读。
- `Esc / b`：返回上一级。
- `h`：回根。
- `q`：退出并保存阅读进度。
- `[✓]` 表示该节点的**所有**叶子后代都已读完（父标题也会自动打钩）。

### 6.2 自动推进

- 进入任意叶子开始阅读后，读完该叶子会**自动跳到 DFS 顺序的下一个叶子**——不需要回菜单手动选。
- 到达本层最后一个叶子并读完时，自动跨越到上一层的下一个兄弟分支。
- 读完整份文档时弹回根菜单，所有节点都是 `[✓]`。
- 按 `Esc / b` 退出自动推进，回到当前叶子的父菜单。

### 6.3 Mode A：手动 Tab 推进（默认）

- `Tab`：显示下一句（逐字符浮现 + Bionic 粗体）。
- `Shift+Tab`：回看上一句。
- `Space`：跳到本小节末句。
- `h`：高亮当前悬停句子。
- 鼠标移动：悬停句子。
- 鼠标左键：切换句子高亮。

### 6.4 Mode B：自动流式输出

- `Space`：暂停 / 继续。
- `+ / -`：调速（×0.5 / ×0.75 / ×1 / ×1.5 / ×2）。
- `Tab`：立即跳到当前句末并进入下一句。
- `Esc`：终止回上级。
- `h`：高亮当前悬停句子。
- 鼠标移动：悬停句子。
- 鼠标左键：切换句子高亮。
- `--cpm N` / `--wpm N`：自定义速度（默认 300 CPM）。

### 6.5 阅读进度

自动保存在：

```
~/Library/Application Support/youtube-strataread/state/progress/<docHash>.json   # macOS
~/.local/state/youtube-strataread/progress/<docHash>.json                        # Linux
```

### 6.6 高亮摘录

如果你在阅读过程中点亮了任意句子，退出阅读器后会在当前 Markdown 所在目录生成：

```text
highlights.md
```

文件会按章节分组，按你的点击顺序整理高亮句子，方便后续回顾或二次摘录。

---

## 7. Prompt 系统

### 7.1 单 Prompt、一次到位

YouTube StrataRead 使用**一份** system prompt + 一次 LLM 调用完成全部分析。模型拿到整段字幕后自行完成翻译、去冗、分层标题化。不做分步、不做校验、不做自修复。

### 7.2 可编辑、可切换

- prompt 文件位于：`~/Library/Application Support/youtube-strataread/prompts/`（可用 `BY_PROMPTS_DIR` 覆盖）。
- 默认文件是 `prompts.md`，内容就是作者原始写的那份分析思路（首次运行自动生成）。
- **想新增 prompt 类型**：直接在该目录里放一个新的 `.md`（比如 `podcast.md`、`lecture.md`）——下一次 `by run` 就会自动在菜单里看到它，让你选择。

### 7.3 命令

```bash
by prompts path       # 打印 prompts.md 路径
by prompts show       # 打印当前 prompts.md 内容
by prompts reset      # 恢复默认 prompt
open "$(dirname $(by prompts path))"   # 用 Finder 打开目录
```

---

## 8. 命令速查表

| 命令                                               | 说明                                       |
| -------------------------------------------------- | ------------------------------------------ |
| `by example [--mode stream]`                       | 读取内置样例（无需 key）                   |
| `by fetch <URL>`                                   | 仅下载字幕                                 |
| `by process <URL>`                                 | 下载 + AI（交互式选 Provider/Model/Prompt）|
| `by run <URL>`                                     | `process` + `read` 一条龙                  |
| `by read <MD 或 slug 目录>`                        | 进入阅读器                                 |
| `by config set <provider> --key X [--base-url Y]`  | 配置 provider key / base_url / model       |
| `by config use <provider>`                         | 切换默认 Provider                          |
| `by config show`                                   | 查看所有 Provider 配置                     |
| `by prompts path \| show \| reset`                 | 管理 prompt 文件                           |

全局 flag：`-v/--verbose`、`--no-color`、`--config PATH`。

---

## 9. 产物位置一览

- **AI 产物**：`<当前目录>/<视频-slug>/{raw.srt, <slug>.md}`
- **配置文件**：`~/Library/Application Support/youtube-strataread/config.toml`
- **Prompt 目录**：`~/Library/Application Support/youtube-strataread/prompts/`
- **阅读进度**：`~/Library/Application Support/youtube-strataread/state/progress/`
- **崩溃日志**：`<slug>/.by-crash-<timestamp>.log`（仅当 AI 处理失败时）
- **内置样例**：`by example --path` 直接打印位置

---

## 10. FAQ

**Q: `zsh: command not found: by`** — 未安装或虚拟环境未激活。推荐 `pipx install youtube-strataread`，或 `source .venv/bin/activate`。

**Q: `missing API key for provider 'xxx'`** — 运行 `by config set <provider> --key <KEY>`，或设置 `BY_<PROVIDER>_API_KEY` 环境变量。

**Q: `compat provider needs a base_url`** — 跑 `by config set compat --key ... --base-url https://your-relay/v1`。

**Q: 视频没有字幕** — 工具会提示 `no subtitles ...` 并优雅退出，不创建产物目录。

**Q: AI 处理失败但 `raw.srt` 已下载** — 在产物目录里会出现 `.by-crash-<时间戳>.log`；加 `--overwrite` 重跑即可。

---

## 11. License

MIT。
