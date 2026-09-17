from __future__ import annotations

import random
from dataclasses import dataclass

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    Static,
)


@dataclass
class Track:
    title: str
    artist: str
    album: str
    duration: int  # seconds


LIBRARY: list[Track] = [
    Track("Midnight Drive", "Nova Kestrel", "Neon Horizon", 214),
    Track("Paper Boats", "The Quiet Static", "Low Tide", 187),
    Track("Glass Orchard", "Wren & Ivy", "Glass Orchard", 251),
    Track("Static Bloom", "Nova Kestrel", "Neon Horizon", 198),
    Track("Copper Skies", "Harlow Bay", "Copper Skies EP", 172),
    Track("Afterglow", "The Quiet Static", "Low Tide", 233),
    Track("Fault Lines", "Wren & Ivy", "Glass Orchard", 205),
    Track("Slow Static", "Harlow Bay", "Copper Skies EP", 160),
]


def format_time(seconds: int) -> str:
    seconds = max(0, int(seconds))
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


class TrackItem(ListItem):
    def __init__(self, index: int, track: Track) -> None:
        super().__init__()
        self.index = index
        self.track = track

    def compose(self) -> ComposeResult:
        t = self.track
        yield Label(
            f"[b]{t.title}[/b]  [dim]{t.artist} — {t.album}[/dim]"
            f"  [dim]{format_time(t.duration)}[/dim]",
            classes="track-row",
        )


class NowPlaying(Static):
    position: reactive[int] = reactive(0)
    playing: reactive[bool] = reactive(False)
    shuffle: reactive[bool] = reactive(False)
    repeat: reactive[bool] = reactive(False)
    volume: reactive[int] = reactive(80)

    def __init__(self, track: Track) -> None:
        super().__init__()
        self.track = track

    def compose(self) -> ComposeResult:
        yield Label(self._title_line(), id="np-title")
        yield Label(self._meta_line(), id="np-meta")
        yield ProgressBar(total=self.track.duration, show_eta=False, id="np-progress")
        yield Label(self._time_line(), id="np-time")
        yield Label(self._status_line(), id="np-status")

    def _title_line(self) -> str:
        icon = "▶" if self.playing else "⏸"
        return f"{icon}  [b]{self.track.title}[/b]"

    def _meta_line(self) -> str:
        return f"{self.track.artist}  ·  {self.track.album}"

    def _time_line(self) -> str:
        return f"{format_time(self.position)} / {format_time(self.track.duration)}"

    def _status_line(self) -> str:
        flags = []
        flags.append("shuffle: on" if self.shuffle else "shuffle: off")
        flags.append("repeat: on" if self.repeat else "repeat: off")
        flags.append(f"vol: {self.volume}%")
        return "  |  ".join(flags)

    def set_track(self, track: Track) -> None:
        self.track = track
        self.position = 0
        self.query_one("#np-title", Label).update(self._title_line())
        self.query_one("#np-meta", Label).update(self._meta_line())
        bar = self.query_one("#np-progress", ProgressBar)
        bar.total = track.duration
        bar.progress = 0
        self.query_one("#np-time", Label).update(self._time_line())

    def refresh_playing_icon(self) -> None:
        self.query_one("#np-title", Label).update(self._title_line())

    def tick(self, seconds: int = 1) -> bool:
        """Advance position by `seconds`. Returns True if track finished."""
        self.position += seconds
        self.query_one("#np-progress", ProgressBar).progress = self.position
        self.query_one("#np-time", Label).update(self._time_line())
        return self.position >= self.track.duration

    def refresh_status(self) -> None:
        self.query_one("#np-status", Label).update(self._status_line())


class MusicPlayerApp(App):
    """A basic textual music player TUI."""

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

    #controls {
        height: auto;
        align: center middle;
        padding: 1 0 0 0;
    }

    #controls Button {
        margin: 0 1;
        min-width: 8;
    }

    #np-status {
        color: $text-muted;
        padding-top: 1;
    }

    #np-title {
        padding-bottom: 1;
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
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.library = LIBRARY
        self.current_index = 0
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="playlist-panel"):
                yield Label("[b]Playlist[/b]")
                yield ListView(
                    *[TrackItem(i, t) for i, t in enumerate(self.library)],
                    id="playlist",
                )
            with Vertical(id="now-playing-panel"):
                yield Label("[b]Now Playing[/b]")
                yield NowPlaying(self.library[self.current_index])
                with Horizontal(id="controls"):
                    yield Button("⏮ Prev", id="btn-prev")
                    yield Button("▶ Play", id="btn-play")
                    yield Button("Next ⏭", id="btn-next")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#playlist", ListView).index = self.current_index

    @property
    def now_playing(self) -> NowPlaying:
        return self.query_one(NowPlaying)

    # -- transport actions ---------------------------------------------

    def action_toggle_play(self) -> None:
        np = self.now_playing
        np.playing = not np.playing
        np.refresh_playing_icon()
        play_btn = self.query_one("#btn-play", Button)
        play_btn.label = "⏸ Pause" if np.playing else "▶ Play"
        if np.playing:
            self._timer = self.set_interval(1.0, self._on_tick)
        elif self._timer is not None:
            self._timer.stop()
            self._timer = None

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

    def action_volume_down(self) -> None:
        np = self.now_playing
        np.volume = max(0, np.volume - 5)
        np.refresh_status()

    # -- helpers ----------------------------------------------------------

    def _advance(self, step: int) -> None:
        np = self.now_playing
        if np.shuffle:
            self.current_index = random.randrange(len(self.library))
        else:
            self.current_index = (self.current_index + step) % len(self.library)
        track = self.library[self.current_index]
        np.set_track(track)
        self.query_one("#playlist", ListView).index = self.current_index
        if np.playing:
            np.refresh_playing_icon()

    def _on_tick(self) -> None:
        np = self.now_playing
        finished = np.tick(1)
        if finished:
            if np.repeat:
                np.position = 0
                np.query_one("#np-progress", ProgressBar).progress = 0
            else:
                self._advance(1)

    # -- widget events ------------------------------------------------

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
            self.now_playing.set_track(item.track)


if __name__ == "__main__":
    MusicPlayerApp().run()
