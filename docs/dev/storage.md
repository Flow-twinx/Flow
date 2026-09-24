# Storage

All persistent state lives in `~/.flow/`. Most files are plain JSON written
atomically (write to a `.tmp` sibling, `os.replace` onto the target) so a
crash mid-write can never truncate them.

```
~/.flow/
├── config.json            # settings (backend/config.py)
├── library.json           # per-song data, keyed by video id (backend/library.py)
├── library.lock           # flock guard for library.json read-modify-write
├── status.json            # current/last track (backend/status.py)
├── shortcuts.json         # command aliases (backend/shortcuts.py)
├── ignore.txt             # filler words stripped from titles
├── seek.txt               # pending seek delta in milliseconds
├── players.json           # live-player registry (backend/registry.py)
├── vlc.pid                # legacy mirror: pid of the background VLC player
├── tui.pid                # legacy mirror: pid of a running TUI
├── web.pid                # legacy mirror: pid of the web server
├── web_port               # legacy mirror: port of the web server
├── web_command.json       # pending control command for the web player
├── web_ui.json            # web UI settings (download format)
├── downloads/             # downloaded audio (named by video id)
│   ├── .cache/            #   thumbnails  <video_id>.jpg
│   └── liked songs/       #   copies of liked songs
├── music/                 # album folders browsable as albums
├── playlists/             # one JSON file per playlist (schema v2)
│   └── .lock              # flock guard for playlist ops
├── playlists.json         # legacy single-file store (migrated once → .bak)
├── playlist/              # target folder for `playlist download`
├── plugins/               # installed plugins + repo caches
│   ├── <name>/            #   plugin.json, flow_api.py, entry source
│   ├── _repo/             #   clone of the default plugin repo
│   └── _src/              #   clones of other repos
└── LOGS/                  # flow2.log rotating log (dev mode only)
```

## config.json

Loaded at import by `config._load_config()` and saved on every change; keys
are validated against ranges. See the [user configuration
guide](../user/configuration.md) for the full key list. `format` may be
`opus|m4a|mp3|webm` (non-webm requires ffmpeg, which is auto-detected at
startup unless explicitly configured).

## library.json

Top-level object keyed by YouTube video id:

```json
{
  "AbCdEf12345": {
    "liked": true,
    "downloaded": true,
    "title": "Song title",
    "song": "/home/you/.flow/downloads/AbCdEf12345.webm",
    "thumbnail": "/home/you/.flow/downloads/.cache/AbCdEf12345.jpg",
    "artist": "...",
    "album": "...",
    "duration": 214,
    "speed_dial": true
  }
}
```

Notes:

- `song` is only present for downloads; `speed_dial` marks web-UI favorites.
- Every write goes through `library._mutate(fn)`, which takes an exclusive
  `flock` on `~/.flow/library.lock`, loads, applies `fn`, and saves when the
  function reports a change. This makes cross-process read-modify-write safe
  (TUI, web server, and CLI all touch the same file).
- `save()` truncates titles (`_truncate_title`) and purges a denylist of
  metadata keys (`track`, `uploader`, `channel`, `upload_date`,
  `release_date`, `view_count`, `like_count`, `url`) — only
  artist/album/duration are kept.

## status.json

The single "what's playing" source, written by every player (CLI VLC, TUI,
web frontend via `/api/now-playing`):

```json
{ "title": "...", "duration": 214, "playing": true, "thumbnail": "<url or path>", "ts": 1740000000.0 }
```

`ts` is a Unix timestamp; state is only considered current while
`time.time() - ts <= max(120, duration + 30)` (`status._fresh`). The
thumbnail encodes the mode: an `http(s)` URL means the track came from
online, a local path (`.cache/` or under `~/.flow`) means offline — used by
`--resume` and `--like/--unlike/--download`.

## Playlists

`backend/playlist.py` stores one JSON file per playlist in `playlists/`:

```json
{
  "version": 2,
  "name": "roadtrip",
  "description": "",
  "created": 1740000000,
  "modified": 1740000000,
  "tracks": [
    {
      "id": "AbCdEf12345",
      "title": "Song",
      "source": "youtube",
      "ref": "https://www.youtube.com/watch?v=...",
      "local_path": null,
      "duration": 214,
      "added": 1740000000,
      "thumb": "/home/you/.flow/downloads/.cache/AbCdEf12345.jpg"
    }
  ]
}
```

- Filenames are slugified display names (`_slugify`), disambiguated with
  numeric suffixes as needed.
- Name lookups are case-insensitive; `resolve_name()` falls back to
  prefix/substring matching when the query isn't exact.
- All mutations run under an exclusive `flock` on `playlists/.lock` and
  bump `modified`. `add_track` de-duplicates by track `id`. `reorder`
  requires the new id list to be an exact permutation.
- A legacy single-file store (`~/.flow/playlists.json`, pre-v2) is migrated
  on first use — entries are split into per-file stores and the legacy file
  is renamed to `playlists.json.bak`.
- `liked` is a reserved name; `playlist download` writes into
  `~/.flow/playlist/<slug>`.

## Shortcuts

`shortcuts.json` is `{alias: command}` and merges over the built-in defaults
in `backend/shortcuts.py` (pl→play, sh→search, rd→radio, svn→savan, ...).
Loaded by `shortcuts.load()` in `cli.main`; aliases starting with `-` in
shell mode and bare aliases in the prompt are resolved through
`shortcuts.resolve()`.

## Ephemeral control files

- `players.json` — the live-player registry (see [Playback
  control](control.md)). Keyed by kind (`vlc`, `tui`, `web`), each record has
  `pid` + `ts` (and `port` for `web`). Written atomically
  (`backend/registry.py`). Routing reads it first.
- `vlc.pid` / `tui.pid` / `web.pid` + `web_port` — **legacy mirrors** of the
  same state, still written so pre-registry readers keep working.
  `vlc.pid` is the "player slot" (`save_pid_if_free` refuses to overwrite a
  live player's pid); cleared on exit.
- `seek.txt` — `--seek N` writes `N*1000`, `--seekb N` writes `-N*1000`
  (milliseconds); the receiver reads and clears it.
- `web_command.json` — see [Playback control](control.md).