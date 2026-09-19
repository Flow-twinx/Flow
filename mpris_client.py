"""
Query ANY currently-running MPRIS player (Spotify, VLC, Firefox, your own
player from mpris_server.py, etc.) over D-Bus and print its status.

This is basically what playerctl does internally.

Install: sudo apt install python3-dbus   (or python-dbus on Arch)
"""

import dbus

PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPS_IFACE = "org.freedesktop.DBus.Properties"


def list_players(bus):
    """Return bus names of every running MPRIS player."""
    names = bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus") \
               .ListNames(dbus_interface="org.freedesktop.DBus")
    return [n for n in names if n.startswith("org.mpris.MediaPlayer2.")]


def get_status(bus, bus_name):
    obj = bus.get_object(bus_name, "/org/mpris/MediaPlayer2")
    props = dbus.Interface(obj, PROPS_IFACE)

    playback_status = str(props.Get(PLAYER_IFACE, "PlaybackStatus"))
    metadata = props.Get(PLAYER_IFACE, "Metadata")

    title = str(metadata.get("xesam:title", "Unknown"))
    artist_list = metadata.get("xesam:artist", [])
    artist = ", ".join(str(a) for a in artist_list) if artist_list else "Unknown"
    length_us = int(metadata.get("mpris:length", 0))
    art_url = str(metadata.get("mpris:artUrl", ""))

    try:
        position_us = int(props.Get(PLAYER_IFACE, "Position"))
    except dbus.exceptions.DBusException:
        position_us = 0

    return {
        "player": bus_name.replace("org.mpris.MediaPlayer2.", ""),
        "status": playback_status.lower(),
        "title": title,
        "artist": artist,
        "position": fmt_us(position_us),
        "duration": fmt_us(length_us),
        "art_url": art_url,
    }


def fmt_us(microseconds):
    seconds = microseconds // 1_000_000
    return f"{seconds // 60}:{seconds % 60:02d}"


if __name__ == "__main__":
    bus = dbus.SessionBus()
    players = list_players(bus)

    if not players:
        print("No MPRIS players currently running.")
    for name in players:
        try:
            info = get_status(bus, name)
            print(f"[{info['player']}] {info['status']} — "
                  f"{info['artist']} - {info['title']} "
                  f"({info['position']}/{info['duration']})")
        except Exception as e:
            print(f"[{name}] could not read status: {e}")
