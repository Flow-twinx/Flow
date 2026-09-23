# Interfaces

## TUI (`tui/main.py`)

`Flow(App)` is a single Textual screen composed of two panels: the
playlist/search panel and the Now Playing panel, with a footer binding bar.

### Track model

Tracks are `Track` dataclasses (`title`, `ref`, `kind`,
`duration`, `video_id`), where `kind` is `"local"` or `"stream"`.

- Offline lists come from `offline_file.get_songs()` with display titles
  resolved through `library.json`.
- Online lists come from `stream_tracks(query)` → `youtube.search(query,
  limit=10)`. Search responses are tagged with a monotonic `_search_seq`;
  stale responses (a newer query landed first) are dropped.

### Playback

- A VLC instance is created with `--no-video --quiet`; if `python-vlc` is
  unavailable, playback gracefully falls back to *simulated mode* — the UI
  clocks run on a 1 s interval timer instead of VLC positions.
- `_vlc_play()` starts a media, waits briefly for a real playback state, and
  retries once with a fresh media before giving up; returns
  `"vlc"`/`"sim"`/`""`.
- Durations for local tracks are probed in a background thread using
  `vlc.Media.parse`/`parse_with_options`.
- `_on_tick` polls VLC every second: position/total drive the progress bar
  and MPRIS position; reaching the end advances (`_advance`) unless repeat
  is on (VLC is seeked to 0); VLC `Error` state triggers `_recover_playback`
  (fresh media retry, then simulated mode).

### Sharing state

The TUI participates in Flow's control plane fully:

- `config.save_pid_if_free(os.getpid())` + `config.save_tui_pid(...)` claim
  the player slots on mount; both are cleared on quit.
- `_update_status()` writes `status.json` with a thumbnail resolved to the
  local cache path (offline) or the remote URL (online).
- All control signals are installed and dispatched onto the asyncio loop
  (`_install_signals`, `_signal_action`), so `flow --pause --next` etc. work
  against the TUI.
- MPRIS metadata is built from the library entry (`artist`, `album`,
  `artwork`) with `load_track`, plus a live position getter.

## Web app (`web/app.py`)

A single-file Flask app; the root and every unmatched path render
`templates/index.html` (SPA) with static assets served from the same
directory. In `DEV_MODE` it injects Flask/Werkzeug logging into the rotating
`LOGS/flow2.log` via `devlog.py`.

### Lookup pipeline

- `_entry_to_dict()` normalizes an yt-dlp entry into `{title, video_id,
  stream_url, thumbnail, channel, duration, segments}`. Thumbnails are
  upgraded to `maxresdefault` when available.
- **Search cache** — `_cached_search()` keeps the last 50 queries in memory.
- **Play cache** — `_get_full_entry()` caches full entries for 20 minutes,
  triggering a background SponsorBlock segment fetch (`_ensure_segments`).
- **Segment cache** — segments are cached 20 minutes; each video fetches
  once (a `_seg_inflight` set prevents duplicate concurrent fetches).

### Routes

| Route | Purpose |
| ----- | ------- |
| `GET /search?q=&limit=` | YouTube search (limit ≤ 25) |
| `GET /trend` | Trending search results |
| `GET /recommend?video_id=&limit=` | Radio mix from a video (limit ≤ 50) |
| `GET /play?video_id=&fresh=` | Playable entry (fresh=1 bypasses cache) |
| `GET /api/segments` | SponsorBlock segments for a video |
| `GET /offline` | Scan `~/.flow/downloads/` for local songs |
| `POST /download` | Download audio (`save_dir`, `format`), 3 attempts, registers in library + thumbnail + notify |
| `GET /api/is-downloaded`, `/api/downloaded-ids` | Library download state |
| `GET /api/library` | Full library listing (liked/downloaded/speed_dial flags) |
| `GET/POST /api/speed-dial` | Get/set home-screen favorites |
| `GET /api/home` | Last played + speed dials |
| `POST /api/delete-download` | Delete via library entry or file path (path-validated) |
| `POST /api/now-playing` | Browser → `status.update()` |
| `POST /api/control` + `GET /api/control/poll` | Web control bridge (see control.md) |
| `GET/POST /api/playlists`, `/api/playlist`, `/api/playlist/*` | Playlist CRUD, reorder, dedupe, export `.m3u`, save |
| `GET /local/<path>` | Serve local media/thumbnails — resolves to a real path, rejects anything outside `$HOME` and non-media extensions |
| `GET /api/albums`, `/api/album/<name>` | Albums from `~/.flow/music/` |
| `GET /api/local-search` | Substring search over downloads + music dirs |
| `GET /api/liked`, `POST /api/like`, `GET /api/is-liked` | Liked UI; like triggers a background auto-download thread when `down_on_like` |
| `GET /thumb/<video_id>` | Cached thumbnail |
| `GET/POST /api/settings` | Web settings persisted to `web_ui.json`, format via `config.set_format` |

Downloads go through `_download_audio()`: yt-dlp with sponsor
post-processors, optional `FFmpegExtractAudio` for non-webm formats,
retries, then `library.track_download()` + `download_thumbnail()`.

### Server process (`web/main.py`)

- Port selection scans 5000–5005 (`BUSY_PORTS`) for a free one
  (`_first_free_port`), or uses `--port PORT`.
- `flow-web` forks; the parent writes `web.pid`/`web_port` and prints the
  URL, the child serves `127.0.0.1` with the reloader off. `DEV_MODE` runs
  in the foreground for logs.
- `--stop [PORT]` kills the tracked/default port; `--stop-all` kills every
  Flow web server on 5000–5005 and clears the tracking files.

## Visualizer (`backend/visualizer.py`)

The `bars` display mode:

- Captures the system audio monitor through `sounddevice` (`AudioInputStream`
  with `numpy`), computes an FFT, and maps magnitude into `BarWidth`
  log-spaced bins. Bars render at `BarHeight` with `BarSpacing` gap;
  `sensitivity` scales the signal.
- ANSI colors are mapped to curses colors for the full-screen draw.
- It temporarily switches the default recording source to the monitor device
  and restores it on stop, so audio flows whichever way your mixer was set.
- Falls back to drawing `none`-style output when stdout isn't a TTY.

## Lyrics (`backend/lyrics.py`)

The `lyrics` display mode fetches timed lines through `ytmusicapi`:

- `fetch_lyrics(video_id, title)` → `get_watch_playlist(video_id)` to find
  the lyrics browse id, then `get_lyrics(browse_id, timestamps=True)`; if
  that fails, it searches for the title and tries the first 3 song results.
- Lines are normalized to `{text, start, end}` in seconds; `♪` separators
  are dropped.
- `find_line(lyrics, elapsed)` returns the line whose `start <= elapsed <
  end`, so `_display_loop` can scroll lyrics with the song.

## SponsorBlock (`backend/sponsor.py`)

Toggles via `config.AD_SKIP` (`ad_skip`) and `sponsor_categories`
(default sponsor/selfpromo/intro/outro):

- `fetch_segments(video_id)` queries `https://sponsor.ajay.app` directly and
  degrades to `[]` on failure.
- `stream_url()`/`stream_info()` rewrite a watch URL into a downloadable
  audio URL and stitch segments in as `sponsorblock_chapters` so the
  in-page web player can seek past them.
- `download_postprocessors()` cuts sponsor segments out of downloads with
  ffmpeg (`remove_sponsor_segments`) when available and enabled.
- The background player runs a `SponsorBlockPoller` that watches the VLC
  position and seeks over segments as they arrive, remembering skipped ids.