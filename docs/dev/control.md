# Playback control

Every interface can control every other interface. The mechanisms are
**OS signals** for live players, a **command file** for the web player, and
**`status.json`** as the shared "what's playing" source of truth.

## Signal protocol

Signal numbers are defined in `backend/config.py`:

| Signal | Constant | Meaning |
| ------ | -------- | ------- |
| `SIGUSR1` | `SIG_STOP` | Toggle play/pause |
| `SIGUSR2` | `SIG_NEXT` | Next track |
| `SIGRTMIN+2` | `SIG_PREV` | Previous track |
| `SIGRTMIN+3` | `SIG_SEEK_FWD` | Seek forward |
| `SIGRTMIN+4` | `SIG_SEEK_BWD` | Seek backward |
| `SIGRTMIN+5` | `SIG_REPEAT` | Toggle repeat |
| `SIGRTMIN+6` | `SIG_SHUFFLE` | Toggle shuffle |
| `SIGRTMIN+7` | `SIG_STOP_ALL` | Stop |

Handler installation:

- **Background VLC** — `backend/Online/player.py` and
  `backend/Offline/player.py` both call `setup_nav_signals()` when playback
  starts (play/pause, next, prev, stop, seek).
- **TUI** — `tui/main.py` installs the full set (pause, next, prev, repeat,
  shuffle, stop, seek) and dispatches them onto the Textual event loop via
  `loop.call_soon_threadsafe`.

### Sending control

`flow` translates CLI flags into signals in `cli.main`:

- `--pause` → `SIGUSR1`, `--next` → `SIGUSR2`, `--previous` → `SIGRTMIN+2`.
- `--seek N` / `--seekb N` first write the delta in milliseconds to
  `~/.flow/seek.txt` (clamped via `write_seek`), then raise
  `SIGRTMIN+3`/`+4`. The receiver reads and clears `seek.txt` and shifts the
  VLC position (or the simulated clock in the TUI).

`_send_control` aims the signal at the pid in `~/.flow/vlc.pid`; if that pid
is gone, it falls back to `POST /api/control` on the web player
(`~/.flow/web.pid`/`web_port`). `flow-tui` uses `~/.flow/tui.pid` first and
then the VLC pid (`tui/__init__.py`).

## Pid slots

- `~/.flow/vlc.pid` holds the pid of the background VLC player.
  `save_pid_if_free()` refuses to overwrite a still-live player, so a second
  background player doesn't steal the slot; `clear_pid_if()` removes it only
  when it belongs to the exiting process.
- `~/.flow/tui.pid` tracks a running TUI so its repeat/shuffle toggles can
  be sent `--repeat`/`--shuffle` (which require a TUI, not just VLC).
- `~/.flow/web.pid` + `~/.flow/web_port` are written by `flow-web`'s fork
  parent and used by `_send_control` and `flow --status` to reach the web
  player.

## status.json

Written by every player on track start/pause (fields: `title`, `duration`,
`playing`, `thumbnail`, `ts`). Read by:

- `flow --status` / `flow-tui --status` — renders the status card
  (title/artist/album from the library lookup, thumbnail, total duration,
  freshness).
- `flow --resume` — replays the last track, choosing the mode from the
  thumbnail.
- `flow --like/--unlike/--download` — act on the current track.
- Plugins (`flow_api.current_track()`) and the web UI home screen.

Freshness matters: `status._fresh()` treats an entry older than
`max(120, duration + 30)` seconds as stale, so "playing" from a crashed
player doesn't linger.

## MPRIS

`backend/mpris.py` exposes the current track to desktop media keys via
D-Bus, using `dbus-python` + PyGObject with a `dbus-fast` fallback. It
publishes track metadata (`load_track`: title, artist, album, artwork,
position getter) and play state (`set_status`: Playing/Paused/Stopped) on
the standard MPRIS service name. Both the background player
(`_attach_vlc_events` forwards VLC state changes) and the TUI use it.

## Web player control

The web player is a separate process, so signals aren't used — control goes
through a command file, `~/.flow/web_command.json`:

- `backend/control.py::send(command, delta)` writes
  `{"command": ..., "ts": ..., "delta": ...}` atomically. Valid commands:
  `stop`, `next`, `previous`, `seek`, `seekb`.
- The browser polls `GET /api/control/poll`; `control.take()` atomically
  `rename()`s the file to a `.consumed` sibling before reading, so a command
  written mid-read can't be lost and concurrent pollers can't double-consume.
- `flow --pause/--next/--previous/--seek` POST to
  `POST /api/control` when the web player is the active one; the browser's
  next poll picks it up and acts on the in-page player.

One consequence of this split: online/offline CLI playback is signal-driven,
web playback is file-driven, and the TUI publishes enough state
(status.json + pid) to be driven by either.