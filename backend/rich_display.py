"""Rich-based now-playing display and live spinners for `display rich`."""

from __future__ import annotations

import sys
import time

from backend import config


def active():
    """True when the rich display mode is on and stdout can render it."""
    try:
        return config.Display == "rich" and sys.stdout.isatty()
    except Exception:
        return False


def _progress():
    """Build a rich Progress bar from the user's configured column names."""
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        FileSizeColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TaskProgressColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
        TotalFileSizeColumn,
        TransferSpeedColumn,
    )

    registry = {
        "bar": BarColumn,
        "download": DownloadColumn,
        "file_size": FileSizeColumn,
        "m_of_n": MofNCompleteColumn,
        "percentage": TaskProgressColumn,
        "spinner": SpinnerColumn,
        "task": TaskProgressColumn,
        "time_elapsed": TimeElapsedColumn,
        "time_remaining": TimeRemainingColumn,
        "total_size": TotalFileSizeColumn,
        "transfer_speed": TransferSpeedColumn,
    }
    picked = []
    seen = set()
    for name in config.ProgressColumns:
        cls = registry.get(name)
        if cls is None or cls in seen:
            continue
        seen.add(cls)
        picked.append(cls())
    return Progress(*picked, auto_refresh=False)


class NowPlaying:
    """A live rich panel with the track metadata and a progress bar."""

    def __init__(self, title, artist="", album="", duration=0, status=""):
        from rich.console import Console
        from rich.live import Live

        self.title = title or ""
        self.artist = artist or ""
        self.album = album or ""
        self.duration = int(duration or 0)
        self.status = status or ""
        self.console = Console()
        self.progress = _progress()
        self.task = self.progress.add_task("", total=self.duration or None)
        self._live = Live(
            self._panel(0.0, False),
            console=self.console,
            refresh_per_second=8,
            screen=False,
        )

    def set_track(self, title, artist="", album="", duration=0, status=""):
        """Point the panel at another track (used by the `--full` monitor)."""
        self.title = title or ""
        self.artist = artist or ""
        self.album = album or ""
        self.duration = int(duration or 0)
        self.status = status or ""
        try:
            self.progress.update(self.task, completed=0.0, total=self.duration or None)
        except Exception:
            pass

    def render(self, elapsed=0.0, paused=False):
        """The panel renderable for the given position (no Live required)."""
        return self._panel(elapsed, paused)

    def _panel(self, elapsed, paused):
        from rich.panel import Panel

        parts = [x for x in (self.artist, self.album) if x]
        if self.status:
            parts.append(self.status)
        if paused:
            parts.append("[Paused]")
        sub = "  \u00b7  ".join(parts)
        return Panel(
            self.progress,
            title=self.title or "Flow",
            subtitle=sub or None,
            border_style="yellow" if paused else "cyan",
            padding=(0, 1),
            width=self._panel_width(),
        )

    def _panel_width(self):
        """A small panel: about 40% of the terminal, within a readable range."""
        try:
            cols = self.console.width or 80
        except Exception:
            cols = 80
        return max(30, min(int(cols * 0.4), 80))

    def start(self):
        try:
            self._live.start()
        except Exception:
            pass

    def update(self, elapsed, paused=False):
        try:
            self.progress.update(
                self.task,
                completed=max(0.0, float(elapsed)),
                total=self.duration or None,
            )
            self._live.update(self._panel(elapsed, paused))
        except Exception:
            pass

    def stop(self):
        try:
            self._live.stop()
        except Exception:
            pass


def spinner_run(stop, label="Searching"):
    """Block until `stop()` is true, showing a rich spinner meanwhile."""
    from rich.console import Console

    console = Console()
    try:
        with console.status(f"[bold]{label}...[/]"):
            while not stop():
                time.sleep(0.08)
    except Exception:
        pass


class _DownloadBar:
    def __init__(self):
        from rich.console import Console
        from rich.live import Live

        self.console = Console()
        self.progress = _progress()
        self.task = self.progress.add_task("", total=None)
        self._live = Live(
            self.progress, console=self.console, refresh_per_second=8, screen=False
        )

    def start(self):
        try:
            self._live.start()
        except Exception:
            pass

    def update(self, got, total):
        try:
            self.progress.update(
                self.task, completed=float(got), total=float(total) or None
            )
        except Exception:
            pass

    def stop(self):
        try:
            self._live.stop()
        except Exception:
            pass


_download_bar = None


def download_start():
    """Open the rich download progress bar (no-op unless rich display)."""
    global _download_bar
    if not active():
        return
    _download_bar = _DownloadBar()
    _download_bar.start()


def download_update(got, total):
    if _download_bar is not None:
        _download_bar.update(got, total)


def download_stop():
    global _download_bar
    if _download_bar is not None:
        _download_bar.stop()
        _download_bar = None
