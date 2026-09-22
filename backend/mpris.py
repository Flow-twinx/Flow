from __future__ import annotations

import os
import threading
import time

from backend import config

BUS_NAME = "org.mpris.MediaPlayer2.flow"
OBJECT_PATH = "/org/mpris/MediaPlayer2"
ROOT_IFACE = "org.mpris.MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"

PLAYING = "Playing"
PAUSED = "Paused"
STOPPED = "Stopped"

BACKEND_LOCK = threading.Lock()
_bg = None
_pending = []
_pending_lock = threading.Lock()
_once_wait_done = False


def _flush_pending():
    global _pending
    b = _bg
    if b is None or not b.available:
        return
    with _pending_lock:
        calls = _pending
        _pending = []
    if not calls:
        return
    for fn in calls:
        try:
            fn(b)
        except Exception:
            pass


def _defer(fn):
    with _pending_lock:
        if len(_pending) > 32:
            _pending.pop(0)
        _pending.append(fn)


def _start_flusher():
    def _loop():
        while True:
            time.sleep(0.05)
            try:
                _flush_pending()
            except Exception:
                pass

    threading.Thread(target=_loop, daemon=True, name="mpris-flush").start()


try:
    import dbus  # noqa: F401
    import dbus.mainloop.glib  # noqa: F401
    import dbus.service  # noqa: F401
    from gi.repository import GLib  # noqa: F401

    _DBUS_OK = True
except Exception:
    dbus = None
    _DBUS_OK = False

try:
    import dbus_fast  # noqa: F401

    _FAST_OK = True
except Exception:
    dbus_fast = None
    _FAST_OK = False


def _next_trackid() -> str:
    return f"/org/mpris/MediaPlayer2/track/{int(time.time() * 1000) % 10**12}"


# --------------------------------------------------------------------------- #
# Control routing: MPRIS methods deliver the same signals the CLI shell uses. #
# --------------------------------------------------------------------------- #


class _Control:
    """Sends flow's control signals to the current process (the player)."""

    @staticmethod
    def _kill(sig):
        try:
            os.kill(os.getpid(), sig)
        except OSError:
            pass

    def play(self):
        self._kill(config.SIG_STOP)

    def pause(self):
        self._kill(config.SIG_STOP)

    def playpause(self):
        self._kill(config.SIG_STOP)

    def stop(self):
        self._kill(config.SIG_STOP_ALL)

    def next(self):
        self._kill(config.SIG_NEXT)

    def previous(self):
        self._kill(config.SIG_PREV)


# --------------------------------------------------------------------------- #
# dbus-python + PyGObject backend                                             #
# --------------------------------------------------------------------------- #


if _DBUS_OK:

    class _GlibBackend:
        def __init__(self):
            self._service = None
            self._loop = None
            self.error = None
            self.available = False

        def start(self):
            threading.Thread(target=self._run, daemon=True, name="mpris-glib").start()

        def _run(self):
            try:
                dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
                bus = dbus.SessionBus()
                try:
                    bus_name = dbus.service.BusName(
                        BUS_NAME, bus=bus, do_not_queue=True
                    )
                except dbus.exceptions.NameExistsException:
                    self.error = f"{BUS_NAME} already owned"
                    return
                self._service = _GlibService(bus_name)
                self._loop = loop = GLib.MainLoop()
                self.available = True
                loop.run()
            except Exception as exc:  # pragma: no cover - defensive
                self.error = exc

        def _post(self, fn, *args):
            svc = self._service
            loop = self._loop
            if svc is None or loop is None:
                return
            # idle_add is safe before the loop has started: the callback is
            # queued on the default main context and runs once loop.run() is
            # processing, so early track loads are still applied.
            try:
                GLib.idle_add(fn, *args)
            except Exception:
                pass

        def load_track(
            self,
            video_id,
            title,
            duration,
            artist="",
            album="",
            art_path="",
            has_next=False,
            has_prev=False,
        ):
            if self._service is None:
                return
            self._post(
                self._service.apply_track,
                video_id,
                title,
                duration,
                artist,
                album,
                art_path,
                has_next,
                has_prev,
            )

        def set_status(self, status):
            if self._service is None:
                return
            self._post(self._service.apply_status, status)

        def set_position(self, microseconds):
            svc = self._service
            if svc is not None:
                svc._position_us = int(microseconds or 0)

        def set_position_getter(self, fn):
            svc = self._service
            if svc is not None:
                svc._position_getter = fn

        def close(self):
            loop = self._loop
            if loop is not None and loop.is_running():
                try:
                    GLib.idle_add(loop.quit)
                except Exception:
                    pass

    class _GlibService(dbus.service.Object):
        def __init__(self, bus_name):
            super().__init__(bus_name, OBJECT_PATH)
            self._status = STOPPED
            self._metadata = self._empty_metadata()
            self._has_next = False
            self._has_prev = False
            self._position_us = 0
            self._position_getter = None
            self._control = _Control()

        @staticmethod
        def _empty_metadata():
            return {
                "mpris:trackid": dbus.ObjectPath(_next_trackid()),
                "mpris:length": dbus.Int64(0),
                "mpris:artUrl": dbus.String(""),
                "xesam:title": dbus.String(""),
                "xesam:artist": dbus.Array([], signature="s"),
                "xesam:album": dbus.String(""),
            }

        def apply_track(
            self,
            video_id,
            title,
            duration,
            artist="",
            album="",
            art_path="",
            has_next=False,
            has_prev=False,
        ):
            title = str(title or "")
            artist = str(artist or "")
            album = str(album or "")
            art = str(art_path or "")
            self._metadata = {
                "mpris:trackid": dbus.ObjectPath(_next_trackid()),
                "mpris:length": dbus.Int64(int(duration or 0) * 1_000_000),
                "mpris:artUrl": dbus.String(f"file://{art}" if art else ""),
                "xesam:title": dbus.String(title),
                "xesam:artist": dbus.Array([artist] if artist else [], signature="s"),
                "xesam:album": dbus.String(album),
            }
            self._has_next = bool(has_next)
            self._has_prev = bool(has_prev)
            self._position_us = 0
            self._status = PLAYING
            self._emit()

        def apply_status(self, status):
            if status not in (PLAYING, PAUSED, STOPPED):
                return
            self._status = status
            self._emit()

        def _emit(self):
            self.PropertiesChanged(
                PLAYER_IFACE,
                {
                    "PlaybackStatus": dbus.String(self._status),
                    "Metadata": dbus.Dictionary(self._metadata, signature="sv"),
                    "CanGoNext": dbus.Boolean(self._has_next),
                    "CanGoPrevious": dbus.Boolean(self._has_prev),
                },
                [],
            )

        # ---------------- org.freedesktop.DBus.Properties ----------------

        @dbus.service.method(
            dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v"
        )
        def Get(self, interface, prop):
            return self.GetAll(interface)[prop]

        @dbus.service.method(
            dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}"
        )
        def GetAll(self, interface):
            if interface == ROOT_IFACE:
                return {
                    "CanQuit": dbus.Boolean(True),
                    "CanRaise": dbus.Boolean(False),
                    "HasTrackList": dbus.Boolean(False),
                    "Identity": dbus.String("Flow"),
                    "SupportedUriSchemes": dbus.Array([], signature="s"),
                    "SupportedMimeTypes": dbus.Array([], signature="s"),
                }
            if interface == PLAYER_IFACE:
                position = self._position_us
                if self._position_getter is not None:
                    try:
                        raw = self._position_getter()
                        if raw is not None and raw >= 0:
                            position = int(raw) * 1000
                    except Exception:
                        pass
                return {
                    "PlaybackStatus": dbus.String(self._status),
                    "Metadata": dbus.Dictionary(self._metadata, signature="sv"),
                    "Volume": dbus.Double(1.0),
                    "Position": dbus.Int64(position),
                    "CanPlay": dbus.Boolean(True),
                    "CanPause": dbus.Boolean(True),
                    "CanGoNext": dbus.Boolean(self._has_next),
                    "CanGoPrevious": dbus.Boolean(self._has_prev),
                    "CanSeek": dbus.Boolean(False),
                    "CanControl": dbus.Boolean(True),
                    "MinimumRate": dbus.Double(1.0),
                    "MaximumRate": dbus.Double(1.0),
                }
            return {}

        @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ssv")
        def Set(self, interface, prop, value):
            pass

        @dbus.service.signal(dbus.PROPERTIES_IFACE, signature="sa{sv}as")
        def PropertiesChanged(self, interface, changed, invalidated):
            pass

        # ---------------- org.mpris.MediaPlayer2 (root) ----------------

        @dbus.service.method(ROOT_IFACE)
        def Raise(self):
            pass

        @dbus.service.method(ROOT_IFACE)
        def Quit(self):
            pass

        # ---------------- org.mpris.MediaPlayer2.Player ----------------

        @dbus.service.method(PLAYER_IFACE)
        def Play(self):
            if self._status != PLAYING:
                self._control.play()

        @dbus.service.method(PLAYER_IFACE)
        def Pause(self):
            if self._status != PAUSED:
                self._control.pause()

        @dbus.service.method(PLAYER_IFACE)
        def PlayPause(self):
            if self._status in (PLAYING, PAUSED):
                self._control.playpause()

        @dbus.service.method(PLAYER_IFACE)
        def Stop(self):
            self._control.stop()

        @dbus.service.method(PLAYER_IFACE)
        def Next(self):
            self._control.next()

        @dbus.service.method(PLAYER_IFACE)
        def Previous(self):
            self._control.previous()


# --------------------------------------------------------------------------- #
# dbus-fast (pure Python) backend                                             #
# --------------------------------------------------------------------------- #


if _FAST_OK:

    class _FastRoot(dbus_fast.service.ServiceInterface):
        def __init__(self):
            super().__init__(ROOT_IFACE)

        @dbus_fast.service.method()
        def Raise(self):
            pass

        @dbus_fast.service.method()
        def Quit(self):
            pass

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def CanQuit(self) -> "b":
            return False

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def CanRaise(self) -> "b":
            return False

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def HasTrackList(self) -> "b":
            return False

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def Identity(self) -> "s":
            return "Flow"

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def SupportedUriSchemes(self) -> "as":
            return ["file", "https", "http"]

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def SupportedMimeTypes(self) -> "as":
            return []

    class _FastPlayer(dbus_fast.service.ServiceInterface):
        def __init__(self, control):
            super().__init__(PLAYER_IFACE)
            self._control = control
            self._status = STOPPED
            self._metadata = {}
            self._has_next = False
            self._has_prev = False
            self._position_us = 0
            self._position_getter = None
            self._reset_metadata()

        def _reset_metadata(self):
            self._metadata = {
                "mpris:trackid": dbus_fast.Variant("o", _next_trackid()),
                "mpris:length": dbus_fast.Variant("x", 0),
                "mpris:artUrl": dbus_fast.Variant("s", ""),
                "xesam:title": dbus_fast.Variant("s", ""),
                "xesam:artist": dbus_fast.Variant("as", []),
                "xesam:album": dbus_fast.Variant("s", ""),
            }

        def apply_track(
            self,
            video_id,
            title,
            duration,
            artist="",
            album="",
            art_path="",
            has_next=False,
            has_prev=False,
        ):
            title = str(title or "")
            artist = str(artist or "")
            album = str(album or "")
            art = str(art_path or "")
            self._metadata = {
                "mpris:trackid": dbus_fast.Variant("o", _next_trackid()),
                "mpris:length": dbus_fast.Variant("x", int(duration or 0) * 1_000_000),
                "mpris:artUrl": dbus_fast.Variant("s", f"file://{art}" if art else ""),
                "xesam:title": dbus_fast.Variant("s", title),
                "xesam:artist": dbus_fast.Variant("as", [artist] if artist else []),
                "xesam:album": dbus_fast.Variant("s", album),
            }
            self._has_next = bool(has_next)
            self._has_prev = bool(has_prev)
            self._position_us = 0
            self._status = PLAYING
            self._emit()

        def apply_status(self, status):
            if status not in (PLAYING, PAUSED, STOPPED):
                return
            self._status = status
            self._emit()

        def _emit(self):
            self.emit_properties_changed(
                {
                    "PlaybackStatus": dbus_fast.Variant("s", self._status),
                    "Metadata": dbus_fast.Variant("a{sv}", self._metadata),
                    "CanGoNext": dbus_fast.Variant("b", self._has_next),
                    "CanGoPrevious": dbus_fast.Variant("b", self._has_prev),
                }
            )

        def _position(self) -> int:
            us = self._position_us
            if self._position_getter is not None:
                try:
                    raw = self._position_getter()
                    if raw is not None and raw >= 0:
                        us = int(raw) * 1000
                except Exception:
                    pass
            return int(us)

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def PlaybackStatus(self) -> "s":
            return self._status

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def LoopStatus(self) -> "s":
            return "None"

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def Rate(self) -> "d":
            return 1.0

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def Shuffle(self) -> "b":
            return False

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def Metadata(self) -> "a{sv}":
            return self._metadata

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def Volume(self) -> "d":
            return 1.0

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def Position(self) -> "x":
            return self._position()

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def MinimumRate(self) -> "d":
            return 1.0

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def MaximumRate(self) -> "d":
            return 1.0

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def CanGoNext(self) -> "b":
            return self._has_next

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def CanGoPrevious(self) -> "b":
            return self._has_prev

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def CanPlay(self) -> "b":
            return True

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def CanPause(self) -> "b":
            return True

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def CanSeek(self) -> "b":
            return False

        @dbus_fast.service.dbus_property(access=dbus_fast.PropertyAccess.READ)
        def CanControl(self) -> "b":
            return True

        @dbus_fast.service.method()
        def Next(self):
            self._control.next()

        @dbus_fast.service.method()
        def Previous(self):
            self._control.previous()

        @dbus_fast.service.method()
        def Pause(self):
            if self._status != PAUSED:
                self._control.pause()

        @dbus_fast.service.method()
        def PlayPause(self):
            if self._status in (PLAYING, PAUSED):
                self._control.playpause()

        @dbus_fast.service.method()
        def Stop(self):
            self._control.stop()

        @dbus_fast.service.method()
        def Play(self):
            if self._status != PLAYING:
                self._control.play()

        @dbus_fast.service.method()
        def Seek(self, offset: "x"):
            pass

        @dbus_fast.service.method()
        def SetPosition(self, track_id: "o", position: "x"):
            pass

        @dbus_fast.service.method()
        def OpenUri(self, uri: "s"):
            pass

    class _FastBackend:
        def __init__(self):
            self._bus = None
            self._player = None
            self._loop = None
            self.error = None
            self.available = False

        def start(self):
            threading.Thread(target=self._run, daemon=True, name="mpris-fast").start()

        def _run(self):
            import asyncio

            asyncio.run(self._aio_main())

        async def _aio_main(self):
            from dbus_fast.aio import MessageBus
            from dbus_fast.constants import NameRequestReturn

            try:
                self._loop = asyncio.get_running_loop()
                bus = await MessageBus().connect()
                res = await bus.request_name(BUS_NAME)
                if res != NameRequestReturn.PRIMARY_OWNER:
                    self.error = f"{BUS_NAME} already owned"
                    await bus.disconnect()
                    return
                root = _FastRoot()
                player = _FastPlayer(_Control())
                bus.export(OBJECT_PATH, root)
                bus.export(OBJECT_PATH, player)
                self._bus = bus
                self._player = player
                self.available = True
            except Exception as exc:  # pragma: no cover - defensive
                self.error = exc
                return
            try:
                while True:
                    await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass

        def _post(self, fn, *args):
            player = self._player
            loop = self._loop
            if player is None or loop is None:
                return
            try:
                loop.call_soon_threadsafe(fn, *args)
            except RuntimeError:
                pass

        def load_track(
            self,
            video_id,
            title,
            duration,
            artist="",
            album="",
            art_path="",
            has_next=False,
            has_prev=False,
        ):
            if self._player is None:
                return
            self._post(
                self._player.apply_track,
                video_id,
                title,
                duration,
                artist,
                album,
                art_path,
                has_next,
                has_prev,
            )

        def set_status(self, status):
            if self._player is None:
                return
            self._post(self._player.apply_status, status)

        def set_position(self, microseconds):
            p = self._player
            if p is not None:
                p._position_us = int(microseconds or 0)

        def set_position_getter(self, fn):
            p = self._player
            if p is not None:
                p._position_getter = fn

        def close(self):
            pass


# --------------------------------------------------------------------------- #
# No-op stub                                                                  #
# --------------------------------------------------------------------------- #


class _StubBackend:
    available = False
    error = "no dbus backend available"

    def start(self):
        pass

    def load_track(self, *args, **kwargs):
        pass

    def set_status(self, *args, **kwargs):
        pass

    def set_position(self, *args, **kwargs):
        pass

    def set_position_getter(self, *args, **kwargs):
        pass

    def close(self):
        pass


# --------------------------------------------------------------------------- #
# Facade                                                                      #
# --------------------------------------------------------------------------- #


def _build_backend():
    if _DBUS_OK:
        backend = _GlibBackend()
    elif _FAST_OK:
        backend = _FastBackend()
    else:
        backend = _StubBackend()
    backend.start()
    return backend


def _get():
    global _bg, _once_wait_done
    if _bg is None:
        with BACKEND_LOCK:
            if _bg is None:
                _bg = _build_backend()
                _start_flusher()
    if not _once_wait_done:
        # Only the first MPRIS interaction pays the boot latency.
        if not isinstance(_bg, _StubBackend):
            for _ in range(400):  # up to 4s for a slow session-bus boot
                if _bg.available or _bg.error is not None:
                    break
                time.sleep(0.01)
            _flush_pending()
        _once_wait_done = True
    return _bg


def start():
    _get()


def available() -> bool:
    b = _get()
    return b is not None and not isinstance(b, _StubBackend) and b.available


def _call(name, *args, **kwargs):
    b = _get()
    if b.available:
        getattr(b, name)(*args, **kwargs)
    else:
        _defer(lambda bb, _n=name, _a=args, _k=kwargs: getattr(bb, _n)(*_a, **_k))


def load_track(
    video_id,
    title,
    duration,
    artist="",
    album="",
    art_path="",
    has_next=False,
    has_prev=False,
):
    _call(
        "load_track",
        video_id,
        title,
        duration,
        artist=artist,
        album=album,
        art_path=art_path,
        has_next=has_next,
        has_prev=has_prev,
    )


def set_status(status):
    _call("set_status", status)


def set_position(microseconds):
    b = _get()
    if b.available:
        b.set_position(microseconds)


def set_position_getter(fn):
    _call("set_position_getter", fn)


def close():
    b = _get()
    if b.available:
        b.close()
