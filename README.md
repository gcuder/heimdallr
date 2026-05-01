<p align="center">
  <img src="src/heimdallr/assets/logo.png" alt="heimdallr" width="120"/>
</p>

# heimdallr

A terminal watchman for your parallel sessions of any agentic AI CLI — monitor, remember, document.

A TUI that lists every Claude Code and Codex CLI session on your machine, lets you search across them, badges the ones that are currently running, and resumes any of them with a single keypress (or transfers their context into a brand new session).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚔  heimdallr v0.2.0                              42 sessions · ● 3 running │
│                                                                             │
│ 🔍 Search titles & messages.  agent:claude  date:today        [12.4ms]      │
│ [All] [Running] [Recent]   │   [claude] [codex]   │   [mem]                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Agent       Title                          Directory       Turns   Date     │
│ ● claude    ★ Heimdallr architecture plan  ~/repos/heim..   12   2 min ago  │
│ ● codex     Refactor adapter registry      ~/repos/cf       8    14 min ago │
│ ● claude    Fix flaky test in scanner      ~/repos/cf       43   17:02      │
│   claude    Plan rollout for v0.3.0        ~/repos/heim..   5    yesterday  │
├─────────────────────────────────────────────────────────────────────────────┤
│ ● Heimdallr architecture plan                  running · 23m · iTerm2       │
│ claude · ~/repos/heimdallr · ad81f9c2                                       │
│ ─────                                                                       │
│ 12 user · 30 asst · 8 code blocks · 18,402 chars                            │
│ started 3 hours ago · last activity 2 minutes ago · ★ pinned                │
│ ─────                                                                       │
│ Initial prompt                                                              │
│   refactor TUI so list is entry-point, summary fills screen…                │
│ ─────                                                                       │
│ Latest exchange                                                             │
│   » move on to the next thing                                               │
│   ● claude  Got it — switching to the resume flow now…                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Install

```sh
# from a clone of this repo
uv tool install --from . heimdallr

# or run without installing
uv run hmd
```

heimdallr requires Python ≥ 3.12. The `sqlite3` CLI is needed for self-PID tracking; if it's missing, `hmd doctor` will tell you and that one feature is silently disabled.

## Usage

```sh
hmd                    # open the TUI (default)
hmd ls "agent:claude"  # list sessions in the terminal, no TUI
hmd stats              # index statistics
hmd doctor             # verify paths, lockfiles, prerequisites
hmd tui --rebuild      # force a full reindex from disk before opening
```

## Features

### Session list & resume

heimdallr scans `~/.claude/projects/*/*.jsonl` and `~/.codex/sessions/YYYY/MM/DD/*.jsonl` and keeps a Tantivy full-text index in `~/.cache/heimdallr/tantivy/`. First run takes a few seconds for a thousand sessions; subsequent runs are instant via incremental mtime-based reindex.

The session list is the **entry point** — a compact ~10-row table at the top. The bulk of the screen is a structured summary of the highlighted session: header (running pill + duration), identity, activity metrics (turn counts, code blocks, age, last activity), the original prompt, and the latest exchange.

**Resume is smart**: pressing **enter** does the right thing depending on whether the session is already running.

- If a `claude` / `codex` process for the session is alive, heimdallr walks its parent process tree to find the host terminal (iTerm2, Terminal.app, WezTerm, Alacritty, kitty, Ghostty, …) and brings that window forward via `osascript`. Falls back to the attached IDE window if no terminal ancestor is found. heimdallr stays open.
- If the session isn't running, heimdallr opens a **new terminal window** in the session's original directory (auto-detecting your terminal app from `$TERM_PROGRAM`) and continues running so you can launch the next one.

Press **shift+enter** to resume in YOLO mode (Claude `--dangerously-skip-permissions`).

### Running detection

A background detector ticks every 2s and merges four signals:

| Layer | Signal | Confidence |
| --- | --- | --- |
| **self** | heimdallr launched this session itself (PID recorded by the resume wrapper) | high |
| **psutil** | a `claude --resume <id>` or `codex resume <id>` process is alive | high |
| **psutil cwd** | a bare `claude` / `codex` process is running in the session's cwd | medium |
| **lock** | `~/.claude/ide/<port>.lock` says an IDE has the session's directory open | upgrades to high, surfaces IDE name |
| **mtime** | the session's JSONL was modified in the last 5 minutes | low |

In the table:

- `●` (green) — high-confidence running
- `◌` (dim yellow) — low-confidence (mtime only — recent activity, no live process)
- (no dot) — not running

### Context transfer

Press **t** to compact the highlighted session and inject it into a new one. The modal lets you choose:

- **Strategy**
  - *Summary* (~200 tokens) — title + first/last user message
  - *Hybrid* (~1-3k tokens) — summary + last 4 turns
  - *Full* (capped at 50k tokens) — the entire transcript
- **Target tool** — claude or codex (cross-tool transfer is supported)

heimdallr decides automatically whether to inline the context (`claude -p ...` or `codex exec ...`) or write a `.heimdallr-context-<ts>.md` file in the target directory and reference it. Every transfer is recorded in `~/.local/share/heimdallr/state.db` (table `transfers`).

### Pin sessions

Press **p** to mark a session as pinned. Pinned sessions are prefixed with **★** and rank first under the "pinned" sort mode. Pins persist across runs (table `bookmarks`).

### Settings

Press **s** to open the settings screen — a sectioned modal with live-apply (no Save button; every change writes to `~/.config/heimdallr/config.toml` immediately).

| Section | Knobs |
| --- | --- |
| **Display** | Theme, show logo in title bar, default sort mode, preview pane visible by default |
| **Filters** | Hide claude-mem sessions, default agent filter, hidden directory prefixes (multi-line) |
| **Sessions** | Default view (all / running / recent) |
| **Resume** | Terminal app override, YOLO by default, prefer IDE over terminal when jumping |
| **Transfer** | Target IDE preference for context injection |
| **Notifications** | Default + error timeout (seconds), auto-dismiss errors |
| **Keybindings** | Per-action capture override; effective on next launch |
| **Diagnostics** | Version + every path heimdallr touches, with "reveal in Finder" buttons |

Each section has a **Reset section** button. The whole screen closes with `Esc` without quitting hmd.

### Hide claude-mem observer sessions

If you use the [claude-mem](https://github.com/thedotmack/claude-mem) plugin, your `~/.claude/projects/` likely contains thousands of short observer sub-sessions. heimdallr hides anything under `~/.claude-mem/` by default. Press **m** (or toggle the `mem` chip in the filter bar) to show them again. Persistent — controlled by `filters.hide_claude_mem` in the config.

### Jump to attached IDE

If a session is attached to PyCharm / WebStorm / VSCode (heimdallr knows because of the IDE lockfile), press **i** to bring that IDE app to the foreground. macOS uses `osascript` targeting by PID; Linux falls back to `wmctrl`.

### Search syntax

The search box accepts free text plus keyword filters:

| Keyword | Effect |
| --- | --- |
| `agent:claude` | Show only Claude sessions |
| `agent:claude,codex` | OR multiple agents |
| `-agent:codex` | Exclude an agent |
| `dir:project` | Substring match on session directory |
| `date:today` | Today / yesterday / week / month |
| `date:<1h` | Within the last hour. Also `<2d`, `<30m`, `>1w` |

Filter buttons at the top sync with the query — clicking `[claude]` adds `agent:claude` to the query, and vice versa.

### Views & sort

- **1** — All (default)
- **2** — Only sessions detected as running
- **3** — Only sessions modified in the last 24h
- **o** — Cycle sort: recent → running first → pinned first → by project

### IDE lockfile insight

heimdallr reads `~/.claude/ide/<port>.lock` files to know which IDE has Claude attached and to which workspaces. The detail pane shows `attached to PyCharm` (or whichever IDE) for sessions whose directory matches an open IDE workspace.

## Keybindings

| Key | Action |
| --- | --- |
| `enter` | Resume — jump to running terminal/IDE, or spawn a new terminal window |
| `shift+enter` | Resume in YOLO mode (Claude `--dangerously-skip-permissions`) |
| `c` | Copy resume command to clipboard |
| `t` | Open transfer modal |
| `p` | Pin / unpin highlighted session |
| `m` | Toggle visibility of claude-mem observer sessions |
| `s` | Open the settings screen |
| `i` | Bring the attached IDE window to the front |
| `r` | Force a full rescan + reindex |
| `1` `2` `3` | View modes: All / Running / Recent |
| `o` | Cycle sort mode |
| `↑` `↓` `j` `k` | Navigate |
| `PgUp` `PgDn` | Page (≈10 rows) |
| `/` | Focus search box |
| `escape` | Defocus search (or quit if already defocused) |
| `q` `ctrl+c` | Quit |
| `ctrl+\`` | Toggle preview pane |
| `tab` | Accept search autocomplete |
| `?` | Open the help overlay inside the TUI |

Keybindings can be overridden in **Settings → Keybindings** (effective on next launch). The same list is available inside the app via `?`.

## Configuration

heimdallr follows the XDG base-dir spec:

| Path | Contents |
| --- | --- |
| `~/.config/heimdallr/config.toml` | User settings (themes, filters, resume, keybindings) |
| `~/.cache/heimdallr/tantivy/` | Tantivy full-text index |
| `~/.local/share/heimdallr/state.db` | SQLite — bookmarks, spawned PIDs, transfer history |
| `~/.local/state/heimdallr/heimdallr.log` | Parse-error log |

Override the location of any of these by setting `XDG_CONFIG_HOME` / `XDG_CACHE_HOME` / `XDG_DATA_HOME` / `XDG_STATE_HOME`.

`config.toml` is normally edited via the in-TUI settings screen (`s`), but it's plain TOML if you want to hand-edit:

```toml
[display]
theme = "nord"
show_logo = true
sort_mode = "recent"
show_preview = true

[filters]
hide_claude_mem = true
hide_directories = ["~/scratch"]
default_agent = ""        # "" = all agents
default_view = "all"

[resume]
terminal = ""             # "" = auto-detect from $TERM_PROGRAM
yolo_default = false
prefer_ide = false

[transfer]
target_ide = ""           # "" = auto

[notifications]
default_timeout_s = 3.0
error_timeout_s = 5.0
auto_dismiss_errors = true

[keybindings.overrides]
# action = "key", e.g. resume_session = "ctrl+r"
```

Missing keys or sections fall back to defaults; malformed TOML is ignored without crashing the app.

## Troubleshooting

```sh
hmd doctor      # show every path heimdallr touches + whether it exists
hmd stats       # session counts, date range, top directories
hmd tui --rebuild   # nuke the index and reindex from scratch
```

If the resume wrapper isn't tracking PIDs, `doctor` reports a missing `sqlite3` binary. Install via your package manager (`brew install sqlite3` on macOS, etc.).

If a session never shows the green running dot even though `claude` is actively running in another terminal, check that the `claude` process appears in `ps -ef | grep claude` and that its cwd matches the session's recorded directory.

## How it works (under the hood)

- **Tantivy** owns search (titles, content, agent, directory, timestamp).
- **SQLite** owns user-flag state (pins, transfer history, spawned-pid tracking).
- Adapters parse JSONL into `Session` objects; the index is rebuilt incrementally based on file mtimes.
- The detector runs on a background thread, posts `RunningSnapshot` messages to the TUI every 2s.
- Resume goes through `running/resume_wrapper.sh`, a tiny POSIX shell script that records its own PID (`$$`) into `spawned_pids` and then `exec`s the agent. Because POSIX preserves the PID across `exec`, the recorded PID *is* the agent's PID.

## Built on

- [Textual](https://textual.textualize.io/) for the TUI
- [Tantivy](https://github.com/quickwit-oss/tantivy-py) for full-text search
- Patterns and parsing logic from `fast-resume` (the resume UX) and `contextforge` (the adapter shape and transfer flow).

## License

MIT
