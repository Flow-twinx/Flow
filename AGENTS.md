# AGENTS.md

High-signal instructions for working on Flow. Keep changes consistent with repo patterns.

## Quick setup

```bash
uv sync          # install deps (Python 3.14+)
uv run flow --check  # verify environment (needs VLC installed)
```

Requires [VLC](https://www.videolan.org/vlc/) for playback (`python-vlc`). ffmpeg optional for non-webm downloads.

## Entry points (scripts)

Defined in `pyproject.toml`:

- `flow` → `cli.main:main` (interactive shell + one-shot flags)
- `flow-tui` → `tui:main` (Textual TUI)
- `flow-web` → `web.main:main` (Flask web server on port 5000)
- `flow daemon` → `backend/daemon.py` (RPC socket at `~/.flow/flow.sock`)

### Run tests (isolated)

```bash
uv run pytest
# or
.venv/bin/python -m pytest
```

Tests use a scratch `HOME` (set by `tests/conftest.py`) via temp dir; they never touch `~/.flow`. They cover player registry and daemon RPC surface, plus a real socket E2E against `flow daemon` when the `flow` binary is available.

### Run single test / focused

```bash
uv run pytest tests/test_daemon_rpc.py -v
uv run pytest -q -k registry
```

### Try the app locally

```bash
uv run flow                        # interactive CLI shell
uv run flow-tui                   # TUI
uv run flow-web                   # web GUI (http://127.0.0.1:5000)
uv run flow --status              # show current track
uv run flow --pause --next --seek 30  # control running player
```

## Architecture essentials

- **Backend is source of truth** (`backend/`). CLI/TUI/Web are thin entry points.
- **Mode system**: `backend/config.py` holds global `Mode` ("Online"/"Offline"). `is_connected()` (HTTPS to 1.1.1.1 with TCP fallback) decides default mode. Switching calls the other mode's `switch` command; modes don't hand off mid-command.
- **Package boundaries**: `cli/`, `backend/` (core + `Online/`, `Offline/`), `tui/`, `web/`. Excludes built artifacts (`build/`, `dist/`, `*.egg-info/`).
- **Control flow**: control flags (`--pause/--next/--prev/--seek/--seekb`) signal the running player via PID in `~/.flow/vlc.pid` or POST to web `/api/control` if web server is up. Seek writes delta to `~/.flow/seek.txt` first.

## Key quirks & constraints

- **Test isolation is critical**: all state under `~/.flow`. Tests override `HOME` in `tests/conftest.py` before importing backend; subprocesses (e.g. `flow daemon`) inherit it. Don't assume real home.
- **Multi-process state**:
  - `library.db`, `history.db` SQLite in WAL mode, connections per call, `BEGIN IMMEDIATE` on RMW ops
  - `players.json` via `backend/registry.py` is the live registry (pid files mirror)
  - `playlists/*.json` written atomically (tmp+rename) with `flock` on `.lock`
  - `status.json` is "latest writer wins"; files under `~/.flow/` coordinate, not shared memory
- **Daemon RPC**: socket at `~/.flow/flow.sock`, typed dispatch in `backend/rpc.py` with capability gating (`PLUGIN_SAFE_KEYS`, `raw_cli` requires explicit capability). The daemon spawns `flow` for plugins and only allows `raw_cli` behind gating.
- **Plugin commands**: plugin/host commands (`plugins`, `install`, `uninstall/remove`, `run`, `update`, `daemon`) are handled before mode/VLC checks and may exit early. `flow run` lazily starts daemon.
- **Seek mechanism**: flags write delta (ms) to `~/.flow/seek.txt` before signaling; the player reads it. Preserve this behavior if modifying control path.
- **No enforced lint/typecheck**: repo has no ruff/mypy/CI configs present. Don't add generic tooling unless necessary; stick to existing patterns and commands.

## When editing

- Respect existing module boundaries (Online/Offline split; backend owns logic).
- Prefer targeted `edit` over full rewrites; preserve surrounding indentation/style.
- If a change could affect multi-process coordination (registry, db, atomic writes, socket), check the relevant backend module first.
- Docs in `docs/` are the source of truth for deeper details (architecture, control, storage).
- Don't add comments except one liner docstring in def and clases briefly explaning what is does.

If something undocumented is critical (team conventions, release process), ask once via `question` tool; do not ask for anything the repo already makes clear but still if your are unsure always ask never add what is not asked.
