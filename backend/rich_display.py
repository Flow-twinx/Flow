"""Rich-based now-playing display for the `display rich` config mode."""

from __future__ import annotations

from backend import config


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
    picked = [
        registry[name]()
        for name in config.ProgressColumns
        if name in registry
    ]
    return Progress(*picked, auto_refresh=False)


class NowPlaying:
    """A live rich panel with the track title and a progress bar."""

    def __init__(self, title, artist="", album="", duration=0):
        from rich.console import Console
        from rich.live import Live

        self.title = title or ""
        self.artist = artist or ""
        self.album = album or ""
        self.duration = int(duration or 0)
        self.console = Console()
        self.progress = _progress()
        self.task = self.progress.add_task("", total=self.duration or None)
        self._live = Live(
            self._panel(0.0, False),
            console=self.console,
            refresh_per_second=8,
            screen=False,
        )

    def _panel(self, elapsed, paused):
        from rich.panel import Panel

        sub = " - ".join(x for x in (self.artist, self.album) if x)
        if paused:
            sub = (sub + "  \u00b7  " if sub else "") + "[Paused]"
        return Panel(
            self.progress,
            title=self.title or "Flow",
            subtitle=sub or None,
            border_style="yellow" if paused else "cyan",
            padding=(0, 1),
        )

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