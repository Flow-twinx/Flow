# Plugins

Flow can install and run plugins from git repositories. Plugins are small
packages that let you extend the player without touching its internals.

## How plugins run

Installed plugins live in `~/.flow/plugins/<name>/`. Each one contains:

- `plugin.json` — metadata copied from the repo manifest (name, version, entry point, deps).
- `flow_api.py` — **provided by Flow**; the entire API surface a plugin may use.
- the plugin's own source (entry point defaults to `main.py`).

Plugins run as **external processes** (`python <entry> [args...]`, working
directory set to the plugin folder), and talk to Flow over a local typed
IPC socket owned by Flow's resident daemon. A plugin can:

- read the current-track status via `flow_api.current_track()` /
  `flow_api.is_playing()`,
- control the player via typed calls like `flow_api.pause()` / `next()` /
  `seek(30)`,
- read and set a small set of config values via `flow_api.get_config()` /
  `set_config()` (only keys Flow marks safe for plugins).

Plugins never import Flow internals; everything goes through `flow_api`,
and the daemon validates every call host-side. The old
`flow_api.control("--pause", ...)` subprocess passthrough is deprecated;
use the typed methods instead.

Plugins are managed and the daemon is started automatically by `flow run`.
You can also manage the daemon explicitly:

```bash
flow daemon start      # start the resident daemon
flow daemon status     # is it running?
flow daemon quit       # stop it
```

`flow run <name>` goes to the **background by default** (it returns
immediately and the plugin keeps running). Use `flow run <name> -t` for a
foreground "temp" run, or set `dev: true` in the config to always keep runs
in the foreground. Background plugins are tracked by pid and can be stopped
with `flow plugin kill`.

## Install a plugin

```bash
flow plugins list              # list available plugins (reads the cached repo, fast/offline)
flow plugins refresh           # force-pull all plugin repos (repairs empty caches)
flow install                   # interactive picker (space to toggle, enter to install)
flow install thumbnail-circle  # by name, from the default repo
flow install Twinx015/harpy    # owner/repo, from GitHub
flow install <git-url>         # any git repository
flow install <local-path>      # a local directory
flow install a b c             # several plugins at once
flow install <name> --force    # reinstall (or upgrade)
```

Reference forms:

- `name` — looked up in the default repo (`github.com/Twinx015/flow-plugins`)
- `owner/name` — resolved to `github.com/owner/name`
- a git URL or local path — used directly
- `name#entry` and `owner/name` select a specific plugin in the repo

At install time Flow prints any declared dependencies, e.g.
`pip install pyside6`.

## Run and manage

```bash
flow run thumbnail-circle      # run a plugin in the background (extra args pass through)
flow run <name> [args...]      # -t = foreground temp run
flow plugin kill               # interactive picker of running plugins
flow plugin kill <name>        # stop one plugin
flow plugin kill all           # stop every running plugin
flow uninstall thumbnail-circle
flow plugins update            # pull all cached repos, show available updates
flow plugins refresh           # force-reclone/pull every repo cache
```

`plugins update` compares installed versions against the repo manifest and
lists plugins with updates available (install them with `--force`).
