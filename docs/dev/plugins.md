# Plugins

Plugins are the one place where Flow deliberately runs third-party code, and
does so with hard isolation. The implementation lives in
`backend/plugins.py` (install/run lifecycle) plus the resident host
(`backend/daemon.py`) and the typed RPC surface (`backend/rpc.py`). The
user-facing side is documented in the [user plugins
guide](../user/plugins.md).

## Process model

Installed plugins are **external processes**, never imported code:

- `flow install` clones a plugin repo, copies the plugin's source folder
  into `~/.flow/plugins/<name>/`, and writes two files: `plugin.json`
  (metadata from the repo manifest) and `flow_api.py` (copied from
  `backend/plugin_api/flow_api.py`, so it always matches this Flow).
- `flow run <name>` executes
  `[sys.executable, <entry>, *args]` with `cwd` set to the plugin folder and
  env vars `FLOW_PLUGIN_NAME`, `FLOW_PLUGIN_HOME`, `FLOW_BIN`,
  `FLOW_PLUGIN_BG`, `FLOW_SOCKET` and `FLOW_PLUGIN_RAW`. Runs go to the
  **background by default** (`Popen` + `start_new_session`,
  `FLOW_PLUGIN_BG=1`); `-t` forces a foreground temp run, and `dev.mode`
  (`dev: true`) makes foreground the default. Pid files are written to
  `~/.flow/plugins/_pids/<name>.pid` so `plugin kill` can stop background
  runs. Before launching, `flow run` makes sure the daemon is up
  (`_ensure_daemon`).

Plugins talk to Flow over **local typed IPC** — a line-delimited JSON-RPC
socket owned by the resident daemon (`~/.flow/flow.sock`, mode 0600). A
plugin never spawns the `flow` CLI for reads, controls, or config; all of
those go over the socket to host-validated methods. The generated
`flow_api.py` is the entire client surface (API v3, `API_VERSION = 3`):

- state    `current_track()` / `is_playing()` / `status_card()` /
           `library_stats()`      (cheap file reads of status/library JSON)
- player   `pause()` / `resume()` / `next()` / `previous()` / `seek(sec)` /
           `seek_back(sec)` / `like()` / `unlike()` / `download()`
           (host-routed player control, same routing the CLI uses)
- players  `players()` — live players as `[{kind, pid, port?}]`
           (CLI player/TUI/web currently registered and alive)
- config   `get_config(key)` / `get_configs(keys)` / `set_config(key, val)`
           (`PLUGIN_SAFE_KEYS` enforced host-side — unsafe keys are rejected
           by the daemon, never applied)
- ui       `set_theme(name)` / `list_themes()` / `set_spinner(chars)`
- raw      `raw_cli(*flow_args)` — the single gated escape hatch, only when
           the daemon grants `raw` to this plugin (see below)

The old generic `control(*flow_args)` flag passthrough is **not** the
default surface anymore. It is deprecated; the module still ships a
subprocess fallback so pre-v3 plugins keep working, but it emits a
`DeprecationWarning`, requires the socket to be down, and is always less
capable (and slower) than the typed methods.

## Daemon

A single resident host owns the plugin socket. It is the "always-on" owner
of `~/.flow/flow.sock` (the bind is the lock — a launcher that can't bind
simply connects to the running host), writes its pid to
`~/.flow/flowd.pid`, and is started/stopped with:

- `flow daemon start [-f]` — start (daemonized by default; `-f` foreground,
  useful for debugging)
- `flow daemon quit` — stop it
- `flow daemon status` — running pid + socket path, or "not running"
- `flow daemon socket` — print the socket path (for scripts)

`flow run` starts the daemon automatically when it isn't running, so
plugins and the daemon can be treated as one unit. Stale pid/socket files
are cleaned up on the next start (`_cleanup_stale` uses `_alive()` on the
pid).

Concurrency and framing:

- Each connection is handled in its own thread (`_handle_conn`) so one
  slow/broken plugin can't stall others; connections and frames are capped
  (`MAX_FRAME = 1 MiB`).
- Requests are one JSON object per line: `{"method": ..., "params": {...}}`.
  Responses are `{"result": ...}` or `{"error": "..."}`. Reserved `event`
  push frames are not yet emitted.
- The handshake is a `hello` frame carrying `FLOW_PLUGIN_NAME` (the plugin
  identity); the daemon stamps it onto the connection and uses it for
  capability gating. The plugin *cannot* self-grant capabilities by editing
  its copy of `flow_api.py` — the daemon validates against the installed
  manifest on disk.

## Raw capability (gated)

`raw_cli(*flow_args)` runs arbitrary `flow` CLI flags through the real CLI
(`backend/cli_raw.py`). It is the **only** generic flag passthrough left,
and it is gated daemon-side:

- The daemon reads the plugin's **installed** `plugin.json`
  (`~/.flow/plugins/<name>/plugin.json`) on every connection.
- `raw` is granted only when that manifest says `"raw": true`, or when the
  plugin was installed with `FLOW_PLUGIN_RAW=1` at install time (which
  persists `"raw": true` into the installed manifest).
- Without the grant, `raw_cli` returns an error immediately — regardless of
  what flags the plugin passes.

So a plugin can't reach arbitrary flags by accident or by editing its own
client copy; `raw: true` is a host-side decision recorded in the installed
manifest. Repo manifests may declare it; users can force it per install.

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
      "gui": false,
      "raw": false,
      "bg": false
    }
  ]
}
```

`entry` defaults to `main.py`; `deps` are printed at install time but never
auto-installed; `gui` is informational. `raw: true` marks a plugin that may
use the gated `raw_cli()` surface. `bg` decides how `flow run` launches it:
`true` backgrounds it (stdout/stderr → `~/.flow/plugins/_logs/<name>.log`,
stop with `plugin kill <name>`), `false` runs it in the foreground
(Ctrl-C stops it) — the right choice for console plugins like `nowplaying`
that don't work detached. When `bg` is absent, `flow run` falls back to its
default (background, or foreground in dev mode); explicit `-bg` / `-t`
flags always win. A plugin's sources live under `<repo>/plugins/<name>/`.

## Commands

`dispatch(cmd, extra, args)` is the single entry used both by
`cli.main` (top-level: `flow install ...`, `flow run ...`, `flow plugins
list`, `flow daemon ...`) and inside the interactive prompt
(`plugins.dispatch` returns `None` for non-plugin commands so normal
dispatch continues).

- `plugins list` (default subcommand) reads the cached default-repo
  manifest and prints available plugins, right-aligned dim `[installed]` /
  `[installed vX→update]` markers — fast and offline, cloning the repo first
  only if it isn't cached, refreshing if the manifest is missing.
- `install [ref...] [--force]` — bare `install` opens a `questionary`
  checkbox multi-select (space toggles, enter installs). Multiple refs
  install in order; an already-installed plugin is refused without
  `--force`. Setting `FLOW_PLUGIN_RAW=1` in the environment at install time
  writes `raw: true` into the installed manifest.
- `uninstall` / `remove <name>` — deletes the plugin folder and any pid
  file.
- `run <name> [args...] [-t]` — foreground/background semantics above; the
  plugin's pid is written before running so `plugin kill` can stop it.
- `kill [name|all]` (also `plugin kill`) — stops plugins via `_kill_pid`
  (SIGTERM, then SIGKILL after ~5 s), cleaning `_pids/<name>.pid`; bare
  `kill` shows a `questionary` select of running plugins (+ All/Cancel).
- `update` — pulls every cached repo clone and diffs installed versions
  against the manifest (update via `install <name> --force`).
- `refresh` — force-pulls/reclones every cached repo via `_ensure_repo`,
  which repairs empty or broken caches.
- `daemon start|quit|status|socket` — manage the resident host (see above).

## Failure modes

- A bad clone raises inside `_ensure_repo` and is reported; the failed cache
  dir is removed so a retry gets a clean clone.
- Install fails when the requested plugin isn't in the manifest (the
  available names are listed), and when `plugins/<name>/` doesn't exist in
  the repo.
- `run` fails when there's no `plugin.json` or the entry file is missing;
  a `KeyboardInterrupt` returns 130 and prints "Stopped plugin". If the
  daemon can't be started, `run` refuses to launch the plugin.
- `cmd_run` never tries to catch the plugin's own exceptions — they surface
  as its exit code, which `flow` propagates.

## Plugin API (client contract)

The bundled `flow_api.py` (API v3) is self-contained: no Flow internals are
imported; everything goes over the daemon socket or cheap file reads. All
writes go through host-validated methods, so invalid config values are
rejected daemon-side before anything is saved.

```python
import flow_api

track = flow_api.current_track()        # {} if nothing is playing
flow_api.is_playing()

flow_api.get_config("spinner")          # -> "|-/\\"
flow_api.get_configs(["primary", "theme"])  # -> dict of readable config keys
flow_api.set_config("primary", "red")   # (ok: bool, message: str)
flow_api.set_theme("sunset")            # curated color presets
flow_api.list_themes()                  # -> ["fire", "forest", ...]
flow_api.set_spinner("⠋⠙⠹")            # custom loading spinner

flow_api.pause(); flow_api.resume(); flow_api.next(); flow_api.previous()
flow_api.seek(30); flow_api.seek_back(10)
flow_api.like(); flow_api.unlike(); flow_api.download()

flow_api.raw_cli("--status")            # gated: only when the daemon granted raw
```

Writable config keys (host-enforced `PLUGIN_SAFE_KEYS`): `primary`,
`secondary`, `tertiary`, `theme`, `spinner`, `display`, `barwidth`,
`barheight`, `barspacing`, `barchar`, `sensitivity`, `format`,
`max_search`, `max_radio`, `ad_skip`, `down_on_like`. Everything else is
readable but not writable from plugins (`dev`, `ffmpeg`,
`sponsor_categories`).

### Deprecated v2 surface

`control(*flow_args)` and the subprocess fallback still exist for backward
compatibility: they warn loudly and are only used when no daemon socket is
available. New plugins must use the typed methods above.

## Write a plugin

Create a plugin folder with a `main.py` entry point. In your code, use the
bundled `flow_api.py` (do not copy it; it is regenerated on install):

```python
import flow_api

track = flow_api.current_track()   # {} if nothing is playing
if track:
    print("Now playing:", track.get("title"))

flow_api.pause()                   # typed control over the daemon socket
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
      "gui": false,
      "raw": false
    }
  ]
}
```

`gui: true` marks GUI plugins (still run with `flow run <name>`; the label is
informational). `deps` are printed at install time, not installed for you.
`raw: true` opts into the gated `raw_cli()` surface.

Environment variables available to running plugins: `FLOW_PLUGIN_NAME`,
`FLOW_PLUGIN_HOME` (the plugin directory), `FLOW_BIN` (the `flow`
executable used by the deprecated subprocess fallback), `FLOW_PLUGIN_BG`
(`"1"` when running in the background, else `"0"`), `FLOW_SOCKET` (the
daemon socket path) and `FLOW_PLUGIN_RAW` (`"1"` when the daemon granted
`raw`, else `"0"`).