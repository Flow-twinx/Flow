import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

BUS_NAME = "org.mpris.MediaPlayer2.flow"
OBJECT_PATH = "/org/mpris/MediaPlayer2"

ROOT_IFACE = "org.mpris.MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"


class Flow(dbus.service.Object):
    def __init__(self):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus_name = dbus.service.BusName(BUS_NAME, bus=dbus.SessionBus())
        super().__init__(bus_name, OBJECT_PATH)

        self._status = "Stopped"  # "Playing" | "Paused" | "Stopped"
        self._metadata = {
            "mpris:trackid": dbus.ObjectPath("/org/mpris/MediaPlayer2/track/0"),
            "mpris:length": dbus.Int64(0),  # microseconds
            "mpris:artUrl": "",
            "xesam:title": "",
            "xesam:artist": dbus.Array([], signature="s"),
            "xesam:album": "",
        }

    # ---- called by YOUR app when a track starts ----
    def load_track(self, title, artist, album, length_seconds, art_path=""):
        self._metadata.update(
            {
                "mpris:trackid": dbus.ObjectPath("/org/mpris/MediaPlayer2/track/1"),
                "mpris:length": dbus.Int64(int(length_seconds * 1_000_000)),
                "mpris:artUrl": f"file://{art_path}" if art_path else "",
                "xesam:title": title,
                "xesam:artist": dbus.Array([artist], signature="s"),
                "xesam:album": album,
            }
        )
        self._status = "Playing"
        self._emit_properties_changed()

    def set_status(self, status):
        self._status = status
        self._emit_properties_changed()

    def _emit_properties_changed(self):
        self.PropertiesChanged(
            PLAYER_IFACE,
            {
                "PlaybackStatus": self._status,
                "Metadata": dbus.Dictionary(self._metadata, signature="sv"),
            },
            [],
        )

    # ---------------- org.freedesktop.DBus.Properties ----------------

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        return self.GetAll(interface)[prop]

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface == ROOT_IFACE:
            return {
                "CanQuit": True,
                "CanRaise": False,
                "HasTrackList": False,
                "Identity": "Flow",
                "SupportedUriSchemes": dbus.Array([], signature="s"),
                "SupportedMimeTypes": dbus.Array([], signature="s"),
            }
        if interface == PLAYER_IFACE:
            return {
                "PlaybackStatus": self._status,
                "Metadata": dbus.Dictionary(self._metadata, signature="sv"),
                "Volume": 1.0,
                "Position": dbus.Int64(0),
                "CanPlay": True,
                "CanPause": True,
                "CanGoNext": True,
                "CanGoPrevious": True,
                "CanSeek": False,
                "CanControl": True,
            }
        return {}

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ssv")
    def Set(self, interface, prop, value):
        pass  # implement Volume, etc. if you want it writable

    @dbus.service.signal(dbus.PROPERTIES_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    # ---------------- org.mpris.MediaPlayer2 (root) ----------------

    @dbus.service.method(ROOT_IFACE)
    def Raise(self):
        pass

    @dbus.service.method(ROOT_IFACE)
    def Quit(self):
        loop.quit()

    # ---------------- org.mpris.MediaPlayer2.Player ----------------

    @dbus.service.method(PLAYER_IFACE)
    def Play(self):
        self.set_status("Playing")

    @dbus.service.method(PLAYER_IFACE)
    def Pause(self):
        self.set_status("Paused")

    @dbus.service.method(PLAYER_IFACE)
    def PlayPause(self):
        self.set_status("Paused" if self._status == "Playing" else "Playing")

    @dbus.service.method(PLAYER_IFACE)
    def Stop(self):
        self.set_status("Stopped")

    @dbus.service.method(PLAYER_IFACE)
    def Next(self):
        print("Next requested (hook this up to your queue)")

    @dbus.service.method(PLAYER_IFACE)
    def Previous(self):
        print("Previous requested (hook this up to your queue)")


if __name__ == "__main__":
    player = Flow()

    # demo: pretend a track loaded
    player.load_track(
        title="Sweater Weather",
        artist="The Neighbourhood",
        album="I Love You.",
        length_seconds=252,
        art_path="/downloads/.cache/GCdwKhTtNNw.jpg",
    )

    print(f"Running as {BUS_NAME} — try: playerctl -l")
    loop = GLib.MainLoop()
    loop.run()
