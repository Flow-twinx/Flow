# Plugins

Plugins are the one place where Flow deliberately runs third-party code, and
does so with hard isolation. The implementation lives in
`backend/plugins.py`; the user-facing side is documented in the [user
plugins guide](../user/plugins.md).

## Process model

Installed plugins are **external processes**, never imported code:

- `flow install` clones a plugin repo, copies the plugin's source folder
  into `~/.flow/plugins/<name>/`, and writes two files: `plugin.json`
  (metadata from the repo manifest) and `flow_api.py` (copied from
  `backend/plugin_api/flow_api.py`, so it always matches this Flow).
- `flow run <name>` executes
  `[sys.executable, <entry>, *args]` with `cwd` set to the plugin folder and
  four env vars: `FLOW_PLUGIN_NAME`, `FLOW_PLUGIN_HOME`, `FLOW_BIN`,
  `FLOW_PLUGIN_BG`. Runs go to the **background by default** (`Popen` +
  `start_new_session`, `FLOW_PLUGIN_BG=1`); `-t` forces a foreground temp
  run, and `dev.mode` (`dev: true`) makes foreground the default. Pid files
  are written to `~/.flow/plugins/_pids/<name>.pid` so `plugin kill` can
  stop background runs.
- `FLOW_BIN` points at the `flow` entry point (`shutil.which("flow")`, else
  `python -m cli.main`), which is the _only_ way a plugin can affect Flow:
  `flow_api.control("--pause", ...)` shells out to it as a subprocess.

The generated `flow_api.py` is the entire API surface. Version 2 exposes:

- `current_track()` → reads `~/.flow/status.json`; `{}` when nothing is
  playing or the file is missing. `is_playing()` is a boolean wrapper.
- `control(*flow_args)` → runs a `flow` CLI command, returns its exit code.
- Config reads/writes: `get_config(key)`, `get_configs()` (read
  `flow --config-get`, which resolves aliases and in-memory state),
  `set_config(key, value)` → `(ok, message)` via `flow --config-set`, which
  goes through `config.apply_config()` — the same validated setters the
  `config` shell command uses, restricted to `PLUGIN_SAFE_KEYS`.
- `set_theme(name)`, `list_themes()`, `set_spinner(chars)` — thin wrappers
  over `set_config`/`--theme`; themes and the spinner are stored in the
  config file and take effect on the next Flow launch.
- Player wrappers: `pause()`, `next()`, `previous()`, `seek(sec)`,
  `seek_back(sec)`, `like()`, `unlike()`, `download()`, `status_card()`.
- `library_stats()` → `{songs, liked, duration}` from `~/.flow/library.json`.
- `plugin_info()` → `{api_version, name, home, background, flow_bin, python}`.

Configuration from a plugin is external-process safe: the only mutating
paths are the new `cli.main` flags `--config-get`, `--config-set`, `--theme`
and `--spinner`, all handled before mode detection and the VLC check, and
all reusing validated setters.

The shim carries a docstring saying exactly this — plugins must not import
Flow internals; everything they may do goes through the module.

## Repo resolution

Reference forms handled by `_resolve_ref(ref)`:

- `name` → default repo `https://github.com/Twinx015/flow-plugins.git`
- `owner/name` → `https://github.com/owner/name.git`
- a git URL / `git@...` / local path → used directly
- `ref#select` → `select` picks which plugin in the repo to install, and
  defaults to the repo's last path component

Repos are cached: the default repo under `~/.flow/plugins/_repo/`, any other
repo under `~/.flow/plugins/_src/<sha256-prefix>/`. `_ensure_repo()` clones
shallow (`--depth 1`) or `git pull --ff-only` when a clone already exists. A
cache that has a `.git` dir but **no commits** (e.g. cloned while the remote
was empty) is wiped and re-cloned on demand — `plugins list` refreshes
automatically when the manifest is missing, and `plugins refresh` does so
for every cached repo.

## Manifest

The repo root must contain `manifest.json`:

```json
{
  "plugins": [
    {
      "name": "my-plugin",
      "version": "1.0.0",
      "description": "...",
      "entry": "main.py",
      "deps": ["pyside6"],
      "gui": false
    }
  ]
}
```

`entry` defaults to `main.py`; `deps` are printed at install time but never
auto-installed; `gui` is informational. A plugin's sources live under
`<repo>/plugins/<name>/`.

## Commands

`dispatch(cmd, extra, args)` is the single entry used both by
`cli.main` (top-level: `flow install ...`, `flow run ...`, `flow plugins
list`, ...) and inside the interactive prompt (`plugins.dispatch` returns
`None` for non-plugin commands so normal dispatch continues).

- `plugins list` (default subcommand) reads the cached default-repo
  manifest and prints available plugins, right-aligned dim `[installed]` /
  `[installed vX→update]` markers — fast and offline, cloning the repo first
  only if it isn't cached, refreshing if the manifest is missing.
- `install [ref...] [--force]` — bare `install` opens a `questionary`
  checkbox multi-select (space toggles, enter installs). Multiple refs
  install in order; an already-installed plugin is refused without `--force`.
- `uninstall` / `remove <name>` — deletes the plugin folder and any pid file.
- `run <name> [args...] [-t]` — foreground/background semantics above; the
  plugin's pid is written before running so `plugin kill` can stop it.
- `kill [name|all]` (also `plugin kill`) — stops plugins via
  `_kill_pid` (SIGTERM, then SIGKILL after ~5 s), cleaning `_pids/<name>.pid`;
  bare `kill` shows a `questionary` select of running plugins (+ All/Cancel).
- `update` — pulls every cached repo clone and diffs installed versions
  against the manifest (update via `install <name> --force`).
- `refresh` — force-pulls/reclones every cached repo via `_ensure_repo`,
  which repairs empty or broken caches.

## Failure modes

- A bad clone raises inside `_ensure_repo` and is reported; the failed cache
  dir is removed so a retry gets a clean clone.
- Install fails when the requested plugin isn't in the manifest (the
  available names are listed), and when `plugins/<name>/` doesn't exist in
  the repo.
- `run` fails when there's no `plugin.json` or the entry file is missing;
  a `KeyboardInterrupt` returns 130 and prints "Stopped plugin".
- `cmd_run` never tries to catch the plugin's own exceptions — they surface
  as its exit code, which `flow` propagates.

## Plugin API

The bundled `flow_api.py` provides more than the CLI flags: safe config
writes, themes, the spinner, and player-control wrappers. All writes go
through Flow's validated config setters, so invalid values are rejected
before anything is saved.

```python
import flow_api

track = flow_api.current_track()        # {} if nothing is playing
flow_api.is_playing()

flow_api.get_config("spinner")          # -> "|-/\\"
flow_api.get_configs()                  # -> dict of readable config keys
flow_api.set_config("primary", "red")   # (ok: bool, message: str)
flow_api.set_theme("sunset")            # curated color presets
flow_api.list_themes()                  # -> ["fire", "forest", ...]
flow_api.set_spinner("⠋⠙⠹")            # custom loading spinner

flow_api.pause(); flow_api.next(); flow_api.previous()
flow_api.seek(30); flow_api.seek_back(10)
flow_api.like(); flow_api.unlike(); flow_api.download()
flow_api.status_card()                  # runs `flow --status`

flow_api.library_stats()                # {songs, liked, duration}
flow_api.plugin_info()                  # {name, home, background, flow_bin, ...}
flow_api.control("--pause")             # raw: run any flow CLI command
```

Writable config keys: `primary`, `secondary`, `tertiary`, `theme`,
`spinner`, `display`, `barwidth`, `barheight`, `barspacing`, `barchar`,
`sensitivity`, `format`, `max_search`, `max_radio`, `ad_skip`,
`down_on_like`. Everything else is readable but not writable from plugins
(`dev`, `ffmpeg`, `sponsor_categories`).

## Write a plugin

Create a plugin folder with a `main.py` entry point. In your code, use the
bundled `flow_api.py` (do not copy it; it is regenerated on install):

```python
import flow_api

track = flow_api.current_track()   # {} if nothing is playing
if track:
    print("Now playing:", track.get("title"))

flow_api.control("--pause")        # run `flow --pause`
```

Publish it in a repo with a `manifest.json`:

```json
{
  "plugins": [
    {
      "name": "my-plugin",
      "version": "1.0.0",
      "description": "What it does",
      "entry": "main.py",
      "deps": ["pyside6"],
      "gui": false
    }
  ]
}
```

`gui: true` marks GUI plugins (still run with `flow run <name>`; the label is
informational). `deps` are printed at install time, not installed for you.

Environment variables available to running plugins: `FLOW_PLUGIN_NAME`,
`FLOW_PLUGIN_HOME` (the plugin directory), `FLOW_BIN` (the `flow`
executable used by `control()`), and `FLOW_PLUGIN_BG` (`"1"` when running in
the background, else `"0"`).
