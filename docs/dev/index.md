# Architecture

Flow is a terminal music player with online (streaming) and offline (local
library) modes. The backend holds all logic; thin entry points in `cli/`,
`tui/`, and `web/` launch it in one of three shapes: an interactive shell, a
Textual TUI, or a Flask web app.

## Entry points

Declared in `pyproject.toml` `[project.scripts]`:

| Command | Function | What you get |
| ------- | -------- | ------------ |
| `flow` | `cli.main:main` | Interactive command shell (readline-style prompt) plus one-shot flags |
| `flow-tui` | `tui:main` | Full-screen Textual UI |
| `flow-web` | `web.main:main` | Daemonized Flask web server |
| `flow daemon` | `backend/daemon.py` | Resident RPC host for plugins (`~/.flow/flow.sock`) |

## Package layout

```
cli/                   # `flow` entry point
  main.py              #   argument parsing, mode detection, input loop
  tui.py               #   banner + prompt chrome (imported as cli.tui)
backend/               # all logic
  config.py            #   settings, colors, signal constants, pid/seek helpers
  status.py            #   ~/.flow/status.json + status card printer
  library.py           #   ~/.flow/library.json (likes, downloads, metadata)
  playlist.py          #   per-playlist JSON store + ops
  plist_cli.py         #   playlist command-line parsing
  control.py           #   ~/.flow/web_command.json (web player control)
  registry.py          #   ~/.flow/players.json (live-player registry/routing)
  shortcuts.py         #   ~/.flow/shortcuts.json aliases
  ping.py              #   is_connected() connectivity probe
  mpris.py             #   MPRIS D-Bus integration
  visualizer.py        #   audio-reactive spectrum bars (sounddevice/numpy)
  lyrics.py            #   synced lyrics (ytmusicapi)
  sponsor.py           #   SponsorBlock segment skip / cut
  plugins.py           #   plugin install/run/update
  daemon.py            #   resident RPC host (socket owner, plugin lifecycle)
  rpc.py               #   typed plugin method surface + capability gating
  cli_raw.py           #   gated raw-CLI bridge for the daemon
  plugin_api/          #   flow_api.py — self-contained v3 plugin client
  help_detail.py       #   `help -i` text
  Hyprland/island.qml  #   optional quickshell widget (--setup-island)
  Online/              # online mode
    commands.py        #   command dispatch + COMMANDS dict
    player.py          #   streaming playback (VLC), display loop, signals
    youtube.py         #   yt-dlp search/download/radio/get_entry
  Offline/             # offline mode
    commands.py        #   command dispatch + COMMANDS dict, readline completion
    player.py          #   local playback (VLC), display loop, signals
    file.py            #   local file scanning, liked-songs dir
tui/                   # `flow-tui` entry point
  __init__.py          #   argparse, control flags
  main.py              #   Textual App
web/                   # `flow-web` entry point
  main.py              #   port selection, daemonization, stop commands
  app.py               #   routes, search/download/library/playlist APIs
  devlog.py            #   DEV_MODE request logging
  templates/           #   index.html, script.js, style.css
```

## How a `flow` launch works

1. `cli.main.main()` parses arguments. Plugin/host commands
   (`plugins`, `install`, `uninstall`/`remove`, `run`, `update`, `daemon`)
   are handled globally before anything else and exit — they don't need VLC
   or a mode. `flow run` lazily starts the daemon (`_ensure_daemon`).
2. `_check_vlc()` imports `python-vlc` and exits with install hints if missing.
3. `--check`, `--status`, `--setup-island` short-circuit.
4. Control flags (`--pause`, `--next`, `--previous`, `--seek SEC`,
   `--seekb SEC`) are translated into signals — raised against the pid in
   `~/.flow/vlc.pid`, or POSTed to the web player's `/api/control` when the
   web server is running instead. Seek flags first write the delta (ms) to
   `~/.flow/seek.txt`.
5. `--like`, `--unlike`, `--download` act on the *current* track by reading
   `status.json` (`_act_current`), then dispatch into the right mode module.
6. `--resume` replays the last track from `status.json`, picking the mode
   from the stored thumbnail (remote URL → online, cache/home path →
   offline). `--play-off`/`--radio-off` force offline; `--play N`/`--rd N`
   imply online.
7. Otherwise the mode is decided by `backend.ping.is_connected()`: an HTTPS
   fetch (and TCP fallback on port 80) to `1.1.1.1` with a spinner. The
   result sets the module-level `config.Mode` ("Online"/"Offline").
8. `_load_commands()` picks `backend.Online.commands` or
   `backend.Offline.commands`; either way `commands.run(cmd, extra, args)`
   executes. There is no streaming → local hand-off within one command; each
   mode module implements its own versions of play/radio/search/etc.
9. With no command, `show_banner()` runs and the interactive loop reads input
   from the prompt chrome (`cli.tui`), resolves shortcuts, checks plugin
   commands, and dispatches through the mode module. Commands play in the
   foreground; `-bg` forks a background player and breaks the loop. In shell
   mode, commands implied by `--rd`/`--radio-off`/`--play-off`/`--resume`,
   plus `radio`/`savan` itself (`SHELL_AUTO_BG`), background themselves.

## Mode switching

`backend/config.py` keeps `Mode` as a plain module global. `switch` calls
into the other mode's commands (online's `switch` goes offline, offline's
`switch` re-checks the connection), and `cli.main` reloads the command module
afterward. The TUI keeps its own `mode` string and re-populates the track
list on `Tab`.

## Testing

`tests/` is a pytest suite that runs against a scratch `HOME` (set in
`tests/conftest.py`), so it never touches the real `~/.flow`. It covers the
player registry (live-process registration, pid-file fallback, prune) and
the daemon RPC surface (typed dispatch, `PLUGIN_SAFE_KEYS` gating, raw gating,
`players`), plus a real socket E2E against `flow daemon`:

```sh
uv run pytest        # or: .venv/bin/python -m pytest
```

## Concurrency

Multiple players may exist at once (background VLC, a TUI, a web player), so
shared state is coordinated through files under `~/.flow/`:

- `library.json` and playlists are written atomically (tmp file + `rename`)
  and guarded by `flock` locks (`~/.flow/library.lock`, `.lock` in
  `playlists/`).
- `status.json` is a plain "latest writer wins" file; each interface updates
  it opportunistically.
- `players.json` (`backend/registry.py`) is the live-player registry — every
  interface registers on start and unregisters on exit, and routing resolves
  "who is live" through it (legacy pid files remain as mirrors).
- Player control is delegated to OS signals or a command file, never shared
  memory (see [Playback control](control.md)).
- Plugin traffic goes over the resident daemon's typed RPC socket
  (`~/.flow/flow.sock`, one thread per connection, 1 MiB frame cap) — the
  daemon is the only process that spawns `flow` for plugins (and only behind
  the gated `raw_cli` capability).

See [Storage](storage.md) for the file formats.