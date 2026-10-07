"""One-word tags trimmed out of a track's YouTube metadata.

A music video's title and description carry credits, hashtags, "(Official
Video)" noise and film names. Everything except the language and the artist is
dropped here, so the library keeps two clean single-word tags it can filter and
play by.
"""

import re

LANGUAGE_NAMES = {
    "af": "afrikaans",
    "am": "amharic",
    "ar": "arabic",
    "as": "assamese",
    "az": "azerbaijani",
    "be": "belarusian",
    "bg": "bulgarian",
    "bn": "bengali",
    "ca": "catalan",
    "cs": "czech",
    "da": "danish",
    "de": "german",
    "el": "greek",
    "en": "english",
    "eo": "esperanto",
    "es": "spanish",
    "et": "estonian",
    "eu": "basque",
    "fa": "persian",
    "fi": "finnish",
    "fr": "french",
    "ga": "irish",
    "gl": "galician",
    "gu": "gujarati",
    "ha": "hausa",
    "he": "hebrew",
    "hi": "hindi",
    "hr": "croatian",
    "hu": "hungarian",
    "hy": "armenian",
    "id": "indonesian",
    "ig": "igbo",
    "is": "icelandic",
    "it": "italian",
    "ja": "japanese",
    "ka": "georgian",
    "kk": "kazakh",
    "km": "khmer",
    "kn": "kannada",
    "ko": "korean",
    "lo": "lao",
    "lt": "lithuanian",
    "lv": "latvian",
    "ml": "malayalam",
    "mn": "mongolian",
    "mr": "marathi",
    "ms": "malay",
    "my": "myanmar",
    "ne": "nepali",
    "nl": "dutch",
    "no": "norwegian",
    "or": "odia",
    "pa": "punjabi",
    "pl": "polish",
    "ps": "pashto",
    "pt": "portuguese",
    "ro": "romanian",
    "ru": "russian",
    "si": "sinhala",
    "sk": "slovak",
    "sq": "albanian",
    "sr": "serbian",
    "sv": "swedish",
    "sw": "swahili",
    "ta": "tamil",
    "te": "telugu",
    "th": "thai",
    "tr": "turkish",
    "uk": "ukrainian",
    "ur": "urdu",
    "uz": "uzbek",
    "vi": "vietnamese",
    "yo": "yoruba",
    "zh": "chinese",
    "zu": "zulu",
}

UNKNOWN_LANGUAGE = "other"

LANGUAGE_WORDS = frozenset(LANGUAGE_NAMES.values())

SCRIPT_RANGES = (
    ("urdu", ((0x0750, 0x077F),)),
    ("persian", ((0xFB50, 0xFDFF), (0x06F0, 0x06FF))),
    ("arabic", ((0x0600, 0x06FF),)),
    ("hebrew", ((0x0590, 0x05FF),)),
    ("hindi", ((0x0900, 0x097F), (0xA8E0, 0xA8FF))),
    ("bengali", ((0x0980, 0x09FF),)),
    ("punjabi", ((0x0A00, 0x0A7F),)),
    ("gujarati", ((0x0A80, 0x0AFF),)),
    ("odia", ((0x0B00, 0x0B7F),)),
    ("tamil", ((0x0B80, 0x0BFF),)),
    ("telugu", ((0x0C00, 0x0C7F),)),
    ("kannada", ((0x0C80, 0x0CFF),)),
    ("malayalam", ((0x0D00, 0x0D7F),)),
    ("sinhala", ((0x0D80, 0x0DFF),)),
    ("thai", ((0x0E00, 0x0E7F),)),
    ("lao", ((0x0E80, 0x0EFF),)),
    ("myanmar", ((0x1000, 0x109F), (0xAA60, 0xAA7F))),
    ("khmer", ((0x1780, 0x17FF),)),
    ("korean", ((0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F))),
    ("japanese", ((0x3040, 0x30FF), (0x31F0, 0x31FF))),
    ("chinese", ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))),
    ("russian", ((0x0400, 0x04FF),)),
    ("greek", ((0x0370, 0x03FF),)),
)

_CREDIT = re.compile(
    r"(?:singer|singers|artist|artists|vocal|vocals|performed\s+by)"
    r"[^|\n]{0,30}?[-–:]\s*([^|\n–]+)",
    re.IGNORECASE,
)

_CREDITS_NOISE = re.compile(
    r"\b(?:official|video|audio|song|lyrics?|lyrical|full\s*song|mv|feat\.?|ft\.?|"
    r"remastered|remix|hd|hq|4k|movie\s*track|out\s*now|new\s*song|premiere)\b",
    re.IGNORECASE,
)


def _first(value) -> str:
    if isinstance(value, (list, tuple)):
        value = next((v for v in value if v), "")
    return str(value or "").strip()


def _names(value) -> str:
    """A credits field may be a list of collaborators; keep them all, comma joined."""
    if isinstance(value, (list, tuple)):
        return ", ".join(_first(v) for v in value if _first(v))
    return _first(value)


def normalize_language(value) -> str:
    """`pa`, `Punjabi`, `en-US` -> `punjabi`; unusable input -> `other`."""
    raw = _first(value).lower()
    if not raw:
        return ""
    if raw in LANGUAGE_WORDS:
        return raw
    code = re.split(r"[-_]", raw)[0]
    if code in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[code]
    word = re.sub(r"[^a-z]", "", raw)
    return word if word in LANGUAGE_WORDS else UNKNOWN_LANGUAGE


def detect_language(text) -> str:
    """One word for the script `text` is written in; plain latin text is english."""
    body = str(text or "")
    if not body.strip():
        return ""
    for word, ranges in SCRIPT_RANGES:
        for low, high in ranges:
            if any(low <= ord(ch) <= high for ch in body):
                return word
    return "english"


_PLACEHOLDERS = frozenset(
    {"", "-", "n/a", "na", "none", "null", "unknown", "undefined"}
)


def _clean_name(value) -> str:
    name = re.sub(r"\s+", " ", _first(value)).strip(" \t\n\r|·•,-–—:")
    if name.lower() in _PLACEHOLDERS:
        return ""
    return name[:80]


def artist_from_info(info: dict) -> str:
    """The credited artist: yt-dlp's field, the description credits, then the title."""
    info = info or {}
    for key in ("artist", "artists"):
        name = _clean_name(_names(info.get(key)))
        if name and not _CREDITS_NOISE.fullmatch(name):
            return name
    for line in str(info.get("description") or "").splitlines():
        match = _CREDIT.search(line)
        if match:
            name = _clean_name(match.group(1))
            if name and not _CREDITS_NOISE.fullmatch(name):
                return name
    try:
        from Tile import parse_title

        return _clean_name(parse_title(str(info.get("title") or "")).get("artist"))
    except Exception:
        return ""


def tags_from_info(info: dict) -> dict:
    """The tags a download stores: `language` (one word) and `artist`."""
    info = info or {}
    language = normalize_language(info.get("language"))
    if not language:
        language = detect_language(info.get("title"))
    if not language:
        language = detect_language(info.get("description"))
    tags = {}
    if language:
        tags["language"] = language
    artist = artist_from_info(info)
    if artist:
        tags["artist"] = artist
    return tags