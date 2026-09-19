from __future__ import annotations

import asyncio
import os
import pathlib
import random
import signal
import threading
import time
from dataclasses import dataclass

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    Static,
)

from backend import config, library, sponsor, status
from backend.Offline import file as offline_file
from backend.Online import youtube


@dataclass
class Track:
    title: str
    ref: str
    kind: str = "local"
    duration: int | None = None
    video_id: str | None = None


def local_tracks() -> list[Track]:
    tracks: list[Track] = []
    for path in offline_file.get_songs():
        tracks.append(
            Track(
                title=offline_file.display_name(path) or path.stem,
                ref=str(path),
                kind="local",
            )
        )
    return tracks


def stream_tracks(query: str, limit: int = 10) -> list[Track]:

    tracks: list[Track] = []
    for info, title, duration in youtube.search(query, limit=limit):
        url = (
            info.get("webpage_url")
            or info.get("original_url")
            or info.get("url")
            or (
                f"https://www.youtube.com/watch?v={info['id']}"
                if info.get("id")
                else ""
            )
        )
        tracks.append(
            Track(
                title=title or "Unknown",
                ref=url,
                kind="stream",
                duration=int(duration) if duration else None,
                video_id=info.get("id"),
            )
        )
    return tracks


def format_time(seconds: int | None) -> str:
    if seconds is None:
        return "–:–"
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


class TrackItem(ListItem):
    def __init__(self, index: int, track: Track) -> None:
        super().__init__()
        self.index = index
        self.track = track

    def compose(self) -> ComposeResult:
        yield Label(self._row(), classes="track-row")

    def _row(self) -> str:
        t = self.track
        return f"[b]{t.title}[/b]  [dim]{format_time(t.duration)}[/dim]"

    def set_duration(self, seconds: int) -> None:
        self.track.duration = seconds
        self.query_one(Label).update(self._row())


class NowPlaying(Static):
    position: reactive[int] = reactive(0)
    total: reactive[int] = reactive(0)
    playing: reactive[bool] = reactive(False)
    shuffle: reactive[bool] = reactive(False)
    repeat: reactive[bool] = reactive(False)
    volume: reactive[int] = reactive(80)

    def __init__(self, track: Track) -> None:
        super().__init__()
        self.track = track

    def compose(self) -> ComposeResult:
        with Vertical(id="np-info"):
            yield Label(self._title_line(), id="np-title")
            yield ProgressBar(
                total=max(1, self.total or 1), show_eta=False, id="np-progress"
            )
            yield Label(self._time_line(), id="np-time")
        yield Label(self._status_line(), id="np-status")

    def _title_line(self) -> str:
        icon = "" if self.playing else ""
        return f"{icon}  [b]{self.track.title}[/b]"

    def _time_line(self) -> str:
        total = self.total or None
        return f"{format_time(self.position)} / {format_time(total)}"

    def _status_line(self) -> str:
        flags = []
        flags.append("shuffle: on" if self.shuffle else "shuffle: off")
        flags.append("repeat: on" if self.repeat else "repeat: off")
        flags.append(f"vol: {self.volume}%")
        return "  |  ".join(flags)

    def set_track(self, track: Track) -> None:
        self.track = track
        self.position = 0
        self.total = track.duration or 0
        self.query_one("#np-title", Label).update(self._title_line())
        bar = self.query_one("#np-progress", ProgressBar)
        bar.total = max(1, self.total or 1)
        bar.progress = 0
        self.query_one("#np-time", Label).update(self._time_line())

    def set_total(self, seconds: int | None) -> None:
        if seconds and seconds > 0:
            self.total = seconds
            self.query_one("#np-progress", ProgressBar).total = max(1, seconds)
            self.query_one("#np-time", Label).update(self._time_line())

    def watch_position(self, value: int) -> None:
        if not self.is_mounted:
            return
        try:
            self.query_one("#np-progress", ProgressBar).progress = value
            self.query_one("#np-time", Label).update(self._time_line())
        except Exception:
            pass

    def watch_total(self, value: int) -> None:
        if not self.is_mounted:
            return
        try:
            bar = self.query_one("#np-progress", ProgressBar)
            bar.total = max(1, value or 1)
            self.query_one("#np-time", Label).update(self._time_line())
        except Exception:
            pass

    def refresh_playing_icon(self) -> None:
        self.query_one("#np-title", Label).update(self._title_line())

    def tick(self, seconds: int = 1) -> bool:
        self.position += seconds
        self.query_one("#np-progress", ProgressBar).progress = self.position
        self.query_one("#np-time", Label).update(self._time_line())
        return bool(self.total) and self.position >= self.total

    def refresh_status(self) -> None:
        self.query_one("#np-status", Label).update(self._status_line())


class Flow(App):
    CSS = """
    Screen {
        layout: vertical;
    }

    #body {
        height: 1fr;
    }

    #playlist-panel {
        width: 60%;
        border: round $accent;
        padding: 1;
    }

    #now-playing-panel {
        width: 40%;
        border: round $primary;
        padding: 1;
    }

    .track-row {
        padding: 0 1;
    }

    ListView {
        height: 1fr;
    }

    ListView:focus > ListItem.--highlight {
        background: $accent 30%;
    }

    ListItem.--highlight {
        background: $panel;
    }

    #search {
        margin: 0 0 1 0;
    }

    #controls {
        height: auto;
        align: center middle;
        padding: 1 0 0 0;
    }

    #controls Button {
        margin: 0 1;
        min-width: 8;
    }

    #np-mode {
        padding-bottom: 1;
        color: $text-muted;
    }

    #message {
        min-height: 1;
        color: $text-muted;
        padding-bottom: 1;
    }

    #np-status {
        color: $text-muted;
        padding-top: 1;
    }

    #np-title {
        padding-bottom: 1;
    }

    #np-info {
        width: 1fr;
    }
    """

    BINDINGS = [
        ("space", "toggle_play", "Play/Pause"),
        ("n", "next_track", "Next"),
        ("p", "prev_track", "Prev"),
        ("s", "toggle_shuffle", "Shuffle"),
        ("r", "toggle_repeat", "Repeat"),
        ("+", "volume_up", "Vol +"),
        ("-", "volume_down", "Vol -"),
        Binding("tab", "switch_mode", "Mode", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self, mode: str | None = None, repeat: bool = False, shuffle: bool = False
    ) -> None:
        super().__init__()
        self.mode = mode or "Offline"
        config.Mode = self.mode
        self.library: list[Track] = []
        self._online_results: list[Track] = []
        self._current: Track | None = None
        self.current_index = 0
        self.is_playing = False
        self._timer: Timer | None = None
        self._vlc = None
        self._vlc_player = None
        self._vlc_state = None
        self._media = None
        self._streaming = False
        self._resume_position: int | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._shuffle = shuffle
        self._repeat = repeat

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="playlist-panel"):
                yield Label(id="panel-title")
                yield Input(
                    placeholder="Search YouTube… and press Enter",
                    id="search",
                )
                yield ListView(id="playlist")
            with Vertical(id="now-playing-panel"):
                yield Label("[b]Now Playing[/b]")
                yield Label(id="np-mode")
                yield Label(id="message")
                yield NowPlaying(Track("Nothing selected", "", "", ""))
                with Horizontal(id="controls"):
                    yield Button("󰒮", id="btn-prev")
                    yield Button("", id="btn-play")
                    yield Button("󰒭", id="btn-next")
        yield Footer()

    def on_mount(self) -> None:
        self._init_vlc()
        self._apply_launch_modes()
        self._update_mode_ui()
        self._reload_library()
        self._loop = asyncio.get_running_loop()
        config.save_pid_if_free(os.getpid())
        config.save_tui_pid(os.getpid())
        self._install_signals()

    def _apply_launch_modes(self) -> None:
        np = self.now_playing
        if self._repeat:
            np.repeat = True
        if self._shuffle:
            np.shuffle = True
        if self._repeat or self._shuffle:
            np.refresh_status()

    def _install_signals(self) -> None:
        for sig, action in (
            (signal.SIGUSR1, "pause"),
            (signal.SIGUSR2, "next"),
            (config.SIG_PREV, "prev"),
            (config.SIG_REPEAT, "repeat"),
            (config.SIG_SHUFFLE, "shuffle"),
        ):
            try:
                signal.signal(sig, lambda *_, a=action: self._signal_dispatch(a))
            except (ValueError, OSError):
                pass

    def _signal_dispatch(self, action: str) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(self._signal_action, action)

    def _signal_action(self, action: str) -> None:
        try:
            if action == "pause":
                self.action_toggle_play()
            elif action == "next":
                self.action_next_track()
            elif action == "prev":
                self.action_prev_track()
            elif action == "repeat":
                self.action_toggle_repeat()
            elif action == "shuffle":
                self.action_toggle_shuffle()
        except Exception:
            pass

    def _init_vlc(self) -> None:
        try:
            import vlc

            self._vlc = vlc.Instance("--no-video --quiet")
            self._vlc_player = self._vlc.media_player_new()
            self._vlc_state = vlc.State
            self._streaming = True
        except Exception:
            self._vlc = None
            self._vlc_player = None
            self._vlc_state = None
            self._streaming = False
            self._status("python-vlc unavailable — simulated playback")

    @property
    def now_playing(self) -> NowPlaying:
        return self.query_one(NowPlaying)

    def action_quit(self) -> None:
        try:
            if self._vlc_player is not None:
                self._vlc_player.stop()
        except Exception:
            pass
        config.clear_pid_if(os.getpid())
        config.clear_tui_pid_if(os.getpid())
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self.exit)
        else:
            self.exit()

    def action_switch_mode(self) -> None:
        self.mode = "Online" if self.mode == "Offline" else "Offline"
        config.Mode = self.mode
        self._update_mode_ui()
        self._reload_library()

    def _update_mode_ui(self) -> None:
        online = self.mode == "Online"
        self.query_one("#panel-title", Label).update(
            "[b]Search — Online[/b]" if online else "[b]Library — Offline[/b]"
        )
        self.query_one("#np-mode", Label).update(f"Mode: [b]{self.mode}[/b]")
        self.query_one("#search", Input).display = online
        if not online:
            self.query_one("#search", Input).value = ""

    def _reload_library(self) -> None:
        if self.mode == "Offline":
            self.library = local_tracks()
            self._populate()
            self._status(f"{len(self.library)} tracks in local library")
            self._probe_durations_async()
        else:
            self.library = list(self._online_results)
            self._populate()
            if not self._online_results:
                self._status("Type a query and press Enter to search YouTube")
            else:
                self._status(
                    f"{len(self._online_results)} results — Enter a new query to search again"
                )

    def _populate(self) -> None:
        lv = self.query_one("#playlist", ListView)
        lv.clear()
        for i, track in enumerate(self.library):
            lv.append(TrackItem(i, track))
        if self.library:
            self.current_index = min(self.current_index, len(self.library) - 1)
            lv.index = self.current_index

    def _probe_durations_async(self) -> None:
        tracks = [t for t in self.library if t.duration is None]
        if self.mode != "Offline" or not tracks:
            return
        threading.Thread(target=self._probe_worker, args=(tracks,), daemon=True).start()

    def _probe_worker(self, tracks: list[Track]) -> None:
        try:
            import vlc

            inst = vlc.Instance("--no-video")
            for track in tracks:
                try:
                    media = inst.media_new(track.ref)
                    duration_ms = None
                    try:
                        media.parse()
                        duration_ms = media.get_duration()
                    except Exception:
                        media.parse_with_options(vlc.MediaParseFlag.local, 5000)
                        duration_ms = media.get_duration()
                    media.release()
                    if duration_ms and duration_ms > 0:
                        self._call(self._set_duration, track, duration_ms // 1000)
                except Exception:
                    continue
            inst.release()
        except Exception:
            pass

    def _set_duration(self, track: Track, seconds: int) -> None:
        for item in self.query_one("#playlist", ListView).query(TrackItem):
            if item.track is track:
                item.set_duration(seconds)
                break
        if self._current is track:
            self.now_playing.set_total(seconds)
            self._update_status(self.is_playing)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.mode != "Online":
            return
        query = event.value.strip()
        if not query:
            return
        self._status("Searching YouTube…")
        threading.Thread(target=self._search_worker, args=(query,), daemon=True).start()

    def _search_worker(self, query: str) -> None:
        try:
            tracks = stream_tracks(query)
        except Exception as exc:
            self._call(self._status, f"Search failed: {exc}")
            return
        self._call(self._apply_search, tracks)

    def _apply_search(self, tracks: list[Track]) -> None:
        self._online_results = tracks
        if self.mode == "Online":
            self.library = tracks
            self._populate()
            n = len(tracks)
            self._status(
                f"{n} result{'s' if n != 1 else ''} — Enter a new query to search again"
                if n
                else "No results — try a different query"
            )

    def action_toggle_play(self) -> None:
        if self._current is None:
            return
        np = self.now_playing
        if self.is_playing:
            self._pause()
            return
        # Resume an existing (paused) VLC media if present.
        if self._vlc_player is not None and self._vlc_player.get_media() is not None:
            try:
                self._vlc_player.play()
            except Exception:
                pass
            self.is_playing = True
            np.playing = True
            np.refresh_playing_icon()
            self.query_one("#btn-play", Button).label = ""
            self._ensure_timer()
            self._update_status(True)
            return
        # Simulated resume: pick up where we paused.
        if self._vlc_player is None and self._resume_position is not None:
            np.position = self._resume_position
            self._resume_position = None
            self.is_playing = True
            np.playing = True
            np.refresh_playing_icon()
            self.query_one("#btn-play", Button).label = ""
            self._ensure_timer()
            self._update_status(True)
            return
        self._play(self._current)

    def _pause(self) -> None:
        np = self.now_playing
        self.is_playing = False
        np.playing = False
        np.refresh_playing_icon()
        self.query_one("#btn-play", Button).label = ""
        if (
            self._vlc_player is not None
            and self._vlc_player.get_media() is not None
        ):
            try:
                self._vlc_player.pause()
            except Exception:
                pass
        else:
            self._resume_position = np.position
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._update_status(False)

    def action_next_track(self) -> None:
        self._advance(1)

    def action_prev_track(self) -> None:
        self._advance(-1)

    def action_toggle_shuffle(self) -> None:
        np = self.now_playing
        np.shuffle = not np.shuffle
        np.refresh_status()

    def action_toggle_repeat(self) -> None:
        np = self.now_playing
        np.repeat = not np.repeat
        np.refresh_status()

    def action_volume_up(self) -> None:
        np = self.now_playing
        np.volume = min(100, np.volume + 5)
        np.refresh_status()
        self._apply_volume()

    def action_volume_down(self) -> None:
        np = self.now_playing
        np.volume = max(0, np.volume - 5)
        np.refresh_status()
        self._apply_volume()

    def _apply_volume(self) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.audio_set_volume(self.now_playing.volume)
            except Exception:
                pass

    def _ensure_media(self, track: Track) -> bool:
        try:
            media = self._vlc_player.get_media()
            if media is not None:
                return True
            source = track.ref
            if track.kind == "stream":
                entry = youtube.get_entry(track.ref) or {}
                source = (
                    sponsor.stream_url(entry) or entry.get("webpage_url") or track.ref
                )
            self._media = self._vlc.media_new(source)
            if self._media is None:
                return False
            self._vlc_player.set_media(self._media)
            return True
        except Exception:
            return False

    def _vlc_play(self, track: Track, fresh: bool = False) -> str:
        """Start VLC playback; returns ``"vlc"``, ``"sim"`` or ``""`` (failed)."""
        if self._vlc_player is None:
            return "sim"
        try:
            if fresh:
                self._reset_media()
            if not self._ensure_media(track):
                return "sim"
            self._vlc_player.play()
            for _ in range(20):
                st = self._vlc_player.get_state()
                if st == self._vlc_state.Error:
                    break
                if st not in (
                    self._vlc_state.NothingSpecial,
                    self._vlc_state.Opening,
                ):
                    return "vlc"
                if self._media_advancing():
                    return "vlc"
                time.sleep(0.05)
            # Retry once with a fresh media before giving up.
            self._reset_media()
            if not self._ensure_media(track):
                return "sim"
            self._vlc_player.play()
            for _ in range(20):
                st = self._vlc_player.get_state()
                if st == self._vlc_state.Error:
                    return "sim"
                if st not in (
                    self._vlc_state.NothingSpecial,
                    self._vlc_state.Opening,
                    self._vlc_state.Ended,
                ):
                    return "vlc"
                if self._media_advancing():
                    return "vlc"
                time.sleep(0.05)
            return "sim"
        except Exception:
            return "sim"

    def _media_advancing(self) -> bool:
        try:
            t = self._vlc_player.get_time()
            return bool(t and t > 0)
        except Exception:
            return False

    def _play(self, track: Track) -> None:
        """Select a track and begin playback (VLC or simulated fallback)."""
        np = self.now_playing
        self._current = track
        np.set_track(track)
        self._reset_media()

        result = self._vlc_play(track)
        if result == "vlc":
            self.is_playing = True
        elif result == "sim":
            if track.duration:
                self.is_playing = True
                self._status("Simulated playback (VLC unavailable/failed)")
            else:
                self.is_playing = False
                np.playing = False
                np.refresh_playing_icon()
                self.query_one("#btn-play", Button).label = ""
                self._status("Could not play: no stream and no known duration")
                return
        else:
            self.is_playing = False
            np.playing = False
            np.refresh_playing_icon()
            self.query_one("#btn-play", Button).label = ""
            self._status("Could not play this track")
            return

        np.playing = True
        np.refresh_playing_icon()
        self.query_one("#btn-play", Button).label = ""
        self._ensure_timer()
        self._update_status(True)

    def _ensure_timer(self) -> None:
        if self._timer is None:
            self._timer = self.set_interval(1.0, self._on_tick)

    def _reset_media(self) -> None:
        if self._vlc_player is not None:
            try:
                self._vlc_player.stop()
                self._vlc_player.set_media(None)
            except Exception:
                pass
        self._media = None

    def _start(self, track: Track) -> None:
        """Select a track without starting playback."""
        self._current = track
        self.now_playing.set_track(track)
        self._reset_media()

    def _advance(self, step: int) -> None:
        if not self.library:
            return
        np = self.now_playing
        if np.shuffle and step:
            self.current_index = random.randrange(len(self.library))
        else:
            self.current_index = (self.current_index + step) % len(self.library)
        track = self.library[self.current_index]
        self.query_one("#playlist", ListView).index = self.current_index
        if self.is_playing:
            self._play(track)
        else:
            self._start(track)

    def _on_tick(self) -> None:
        np = self.now_playing
        if (
            self._streaming
            and self._vlc_player is not None
            and self._vlc_player.get_media() is not None
            and self.is_playing
        ):
            try:
                if self._vlc_player.get_state() == self._vlc_state.Error:
                    self._recover_playback()
                    return
                ms = self._vlc_player.get_time()
                if ms and ms >= 0:
                    np.position = int(ms) // 1000
                length_ms = self._vlc_player.get_length()
                total = (
                    int(length_ms) // 1000
                    if length_ms and length_ms > 0
                    else (self._current.duration if self._current else None)
                )
                if total:
                    if total != np.total:
                        np.set_total(total)
                        if self._current is not None:
                            self._current.duration = total
                            self._update_status(self.is_playing)
                    if np.position >= total:
                        if np.repeat:
                            try:
                                self._vlc_player.set_time(0)
                            except Exception:
                                pass
                            np.position = 0
                        else:
                            self._advance(1)
            except Exception:
                pass
            return

        if (
            not self.is_playing
            or self._current is None
            or self._current.duration is None
        ):
            return
        finished = np.tick(1)
        if finished:
            if np.repeat:
                np.position = 0
                np.query_one("#np-progress", ProgressBar).progress = 0
            else:
                self._advance(1)

    def _recover_playback(self) -> None:
        if not self.is_playing or self._current is None:
            return
        result = self._vlc_play(self._current, fresh=True)
        if result == "vlc":
            self._status("Playback recovered")
            return
        if self._current.duration:
            self._status("VLC playback failed — simulated playback")
        else:
            self.is_playing = False
            np = self.now_playing
            np.playing = False
            np.refresh_playing_icon()
            self.query_one("#btn-play", Button).label = ""
            self._update_status(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-play":
            self.action_toggle_play()
        elif event.button.id == "btn-next":
            self.action_next_track()
        elif event.button.id == "btn-prev":
            self.action_prev_track()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, TrackItem):
            self.current_index = item.index
            self._play(item.track)

    def _thumb_for(self, track: Track) -> str | None:
        """Status-card thumbnail: local cache path or remote YouTube URL."""
        try:
            if track.kind == "local":
                vid = track.video_id or pathlib.Path(track.ref).stem
                p = pathlib.Path(library.thumbnail_path(vid))
                return str(p) if p.exists() else None
            if track.video_id:
                return library.thumbnail_url_for(track.video_id)
        except Exception:
            return None
        return None

    def _update_status(self, playing: bool = True) -> None:
        try:
            if self._current is None:
                return
            status.update(
                self._current.title,
                duration=self._current.duration or 0,
                playing=playing,
                thumbnail=self._thumb_for(self._current),
            )
        except Exception:
            pass

    def _status(self, message: str) -> None:
        try:
            self.query_one("#message", Label).update(message)
        except Exception:
            pass

    def _call(self, fn, *args) -> None:
        try:
            self.call_from_thread(fn, *args)
        except Exception:
            pass


if __name__ == "__main__":
    Flow().run()