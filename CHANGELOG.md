# Changelog

All notable changes to **heimdallr** are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [SemVer](https://semver.org/).

## [0.2.0] — 2026-05-01

### Added

- **In-TUI settings screen** (`s`). Sectioned modal — Display, Filters,
  Sessions, Resume, Transfer, Notifications, Keybindings, Diagnostics —
  with live-apply and per-section reset to defaults. Themes repaint
  instantly; filter changes refresh the list without a restart.
- **TOML settings layer** at `~/.config/heimdallr/config.toml`. Schema is
  forgiving — missing keys fall back to defaults; malformed files don't
  crash the app.
- **Smart resume**. Pressing Enter on a session that's already running
  walks the agent's process tree to find the host terminal (iTerm2,
  Terminal.app, WezTerm, Alacritty, kitty, Ghostty, Tabby, …) and brings
  that window forward via `osascript`. Falls back to the attached IDE
  PID. heimdallr stays open across all paths.
- **New-window resume**. When the session isn't running, heimdallr spawns
  a fresh terminal window via `osascript` (auto-detecting the user's
  terminal from `$TERM_PROGRAM`) and continues running. The CLI no
  longer replaces its shell on macOS.
- **claude-mem filter**. Sessions under `~/.claude-mem/` are hidden by
  default — toggle with `m` or the new `mem` filter chip.
- **Structured session preview**. Header (running pill + duration) +
  identity (agent · cwd · id) + activity metrics (turn counts, code
  blocks, age, last activity) + initial prompt + latest exchange +
  query-match excerpt.
- **Logo widget** in the title bar — rendered via `textual-image`
  (Sixel under iTerm2). Source PNG ships with the package and is
  alpha-keyed so the surface colour shows through.
- **Shift+Enter** resumes in YOLO mode (Claude
  `--dangerously-skip-permissions`). Enter no longer pops a confirmation
  modal.

### Changed

- **Layout flipped**: ~10-row session list as entry point, structured
  summary fills the rest of the screen. Preview is no longer "compact."
- **Resume flow**: never spawns a duplicate of an already-running
  session; never closes hmd unintentionally.
- README updated with new keybindings, settings section, and refreshed
  screenshot.

### Removed

- The YOLO confirmation modal (`tui/modal.py`). Replaced by the
  Shift+Enter binding and the `resume.yolo_default` setting.
- Preview-pane resize bindings (`+` / `-`). The preview is now the
  dominant pane; manual sizing isn't useful.

### Internal

- New `running/terminal.py` (parent-walk + spawn).
- New `settings.py` with `Settings`, `DisplaySettings`,
  `FilterSettings`, `ResumeSettings`, `TransferSettings`,
  `NotificationSettings`, `KeybindingSettings` and `current()`,
  `update()`, `reset_section()` API.
- New widgets: `LogoWidget`, `SettingsModal`, `KeyCaptureModal`.
- 36 new tests across settings round-trip, terminal-pid walk, search
  filter, preview rendering, resume-action wiring, settings-modal
  mount/persistence, and reactive seeding. Total suite: 83 passed,
  1 skipped.

## [0.1.0] — 2026-04-28

Initial public release: Textual TUI, Tantivy index, running detection,
context transfer, pin/bookmark state.
