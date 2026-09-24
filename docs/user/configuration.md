# Configuration

## You don't actually need this most of the time use `config` for an interactive one.

## The `config` command

Inside the `flow` shell, `config` changes settings. Run it bare for an
interactive wizard, `config -h` for the full list of targets and available
color names, or `config <target> <value>` for one-off changes.

| Target            | Description                                | Values                                               |
| ----------------- | ------------------------------------------ | ---------------------------------------------------- |
| `primary` (pri)   | Color for online songs                     | any color name                                       |
| `secondary` (sec) | Color for offline songs                    | any color name                                       |
| `tertiary` (ter)  | Color for labels                           | any color name                                       |
| `display`         | Playback display mode                      | `none`, `bars`, `lyrics`                             |
| `barwidth`        | Number of bars in the visualizer           | 4–80                                                 |
| `barheight`       | Height of bars                             | 10–90                                                |
| `barspacing`      | Space between bars                         | 0–4, or `min` / `fit` / `max`                        |
| `barchar`         | Bar character                              | `dot`, `block`, `circle`, or any single char         |
| `sensitivity`     | Visualizer sensitivity                     | 0.5–5.0                                              |
| `format`          | Default download format                    | `opus`, `m4a`, `mp3`, `webm` (non-webm needs ffmpeg) |
| `ad_skip`         | Skip SponsorBlock segments during playback | `true` / `false`                                     |
| `down_on_like`    | Auto-download when liking an online track  | `true` / `false`                                     |
| `max_search`      | Max YouTube search results                 | 1–20 (default 5)                                     |
| `max_radio`       | Max radio mix tracks                       | 1–50 (default 35)                                    |

`sponsor_categories` (which SponsorBlock segment types are skipped) is set as
a list in the config file — `sponsor`, `selfpromo`, `intro`, `outro` by
default.

Settings persist to `~/.flow/config.json`:

```json
{
  "primary": "cyan",
  "secondary": "purple",
  "tertiary": "blue",
  "display": "bars",
  "bar_width": 20,
  "bar_height": 40,
  "bar_spacing": 1,
  "bar_char": "█",
  "sensitivity": 1.0,
  "dev": false,
  "ffmpeg": true,
  "ad_skip": true,
  "sponsor_categories": ["sponsor", "selfpromo", "intro", "outro"],
  "down_on_like": true,
  "format": "webm",
  "max_search": 5,
  "max_radio": 35
}
```

## Where Flow stores things

Everything lives under `~/.flow/`.

| Path                                        | Purpose                                                            |
| ------------------------------------------- | ------------------------------------------------------------------ |
| `config.json`                               | Settings above                                                     |
| `library.json`                              | Per-song data, keyed by YouTube video id                           |
| `status.json`                               | Current/last played track                                          |
| `downloads/`                                | Downloaded audio, named by video id (e.g. `TucWbkH5WX0.webm`)      |
| `downloads/.cache/`                         | Thumbnails (`<video_id>.jpg`)                                      |
| `downloads/liked songs/`                    | Copies of liked songs (offline liked list)                         |
| `music/`                                    | Album folders browsable as albums in the web UI                    |
| `playlists/`                                | One JSON file per playlist (schema v2)                             |
| `playlist/`                                 | Folder used by `playlist download`                                 |
| `shortcuts.json`                            | User command shortcuts                                             |
| `ignore.txt`                                | Filler words stripped from titles (edit freely; `#` lines ignored) |
| `plugins/`                                  | Installed plugins and plugin repo caches                           |
| `players.json`                             | Live-player registry (`kind`, `pid`, `port` for the web player)    |
| `vlc.pid`, `tui.pid`, `web.pid`, `web_port` | Legacy pid/port mirrors of `players.json` (kept for compat)        |
| `seek.txt`                                  | Pending seek delta (milliseconds) for `--seek`/`--seekb`           |
| `web_command.json`                          | Pending control command for the web player                         |
| `web_ui.json`                               | Web UI settings (e.g. chosen download format)                      |
| `library.lock`                              | Lock guarding `library.json` writes                                |

### library.json entry

Each entry is keyed by the video id and holds:

```json
{
  "liked": true,
  "downloaded": true,
  "title": "Song name",
  "song": "/home/you/.flow/downloads/abc123.webm",
  "thumbnail": "/home/you/.flow/downloads/.cache/abc123.jpg",
  "artist": "...",
  "album": "...",
  "duration": 214,
  "speed_dial": true
}
```

`liked`, `downloaded`, and `speed_dial` are flags; `song` is the local file
path of a download. Entries are truncated to a clean title whenever saved
(extra metadata like uploader/channel/view counts is dropped intentionally).

### Title cleanup

Names shown for downloaded tracks come from `library.json` titles. Extra
words like "official", "lyrics", "video" are stripped using the word list in
`~/.flow/ignore.txt` — edit it to customize what gets removed.

## Backups

`flow export` zips `~/.flow` into `~/Downloads/flow_backup.zip`, skipping the
bulk directories (`downloads/`, `playlist/`, `playlists/`, `LOGS/`) and
`vlc.pid`. Use `playlist export <name>` to get a single playlist as `.m3u`.
