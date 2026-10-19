"""
URL Detector — classifies any URL and detects batch/playlist content.

Returns a detection dict consumed by the queue manager and main window.
"""

import re
from urllib.parse import urlparse, parse_qs

# ── Platform host sets ───────────────────────────────────────────────────────
YOUTUBE_HOSTS    = {"youtube.com", "www.youtube.com", "youtu.be",
                    "music.youtube.com", "m.youtube.com"}
SPOTIFY_HOSTS    = {"open.spotify.com"}
PINTEREST_HOSTS  = {"pinterest.com", "www.pinterest.com", "pin.it",
                    "in.pinterest.com"}
TWITTER_HOSTS    = {"twitter.com", "x.com", "www.twitter.com", "www.x.com"}
INSTAGRAM_HOSTS  = {"instagram.com", "www.instagram.com"}
FACEBOOK_HOSTS   = {"facebook.com", "www.facebook.com", "fb.watch", "fb.com"}
TIKTOK_HOSTS     = {"tiktok.com", "www.tiktok.com", "vm.tiktok.com"}
REDDIT_HOSTS     = {"reddit.com", "www.reddit.com", "v.redd.it", "i.redd.it"}
VIMEO_HOSTS      = {"vimeo.com", "www.vimeo.com"}
TWITCH_HOSTS     = {"twitch.tv", "www.twitch.tv", "clips.twitch.tv"}
SOUNDCLOUD_HOSTS = {"soundcloud.com", "www.soundcloud.com", "on.soundcloud.com"}
DRM_HOSTS        = {
    "netflix.com", "www.netflix.com",
    "primevideo.com", "www.primevideo.com", "amazon.com",
    "hotstar.com", "www.hotstar.com", "disneyplus.com", "www.disneyplus.com",
    "hulu.com", "www.hulu.com", "max.com", "www.max.com",
    "peacocktv.com", "www.peacocktv.com", "paramountplus.com",
    "crunchyroll.com", "www.crunchyroll.com",
    "zee5.com", "www.zee5.com", "sonyliv.com", "www.sonyliv.com",
}

DIRECT_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".tiff",
    ".ico", ".avif",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
    ".3gp", ".ts",
    ".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".wma", ".opus",
    ".aiff",
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt",
    ".csv", ".epub", ".mobi", ".djvu",
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
    ".exe", ".apk", ".dmg", ".deb", ".rpm", ".msi",
    ".json", ".xml", ".yaml", ".sql", ".db", ".sqlite",
}

GDRIVE_HOSTS = {
    "drive.google.com", "docs.google.com",
}

YTDLP_HOSTS = (
    TWITTER_HOSTS | INSTAGRAM_HOSTS | FACEBOOK_HOSTS | TIKTOK_HOSTS |
    REDDIT_HOSTS  | VIMEO_HOSTS     | TWITCH_HOSTS   | SOUNDCLOUD_HOSTS |
    PINTEREST_HOSTS | GDRIVE_HOSTS  | {
        "dailymotion.com", "www.dailymotion.com",
        "bilibili.com",    "www.bilibili.com",
        "nicovideo.jp",    "www.nicovideo.jp",
        "rumble.com",      "www.rumble.com",
        "odysee.com",      "www.odysee.com",
        "bitchute.com",    "www.bitchute.com",
        "streamable.com",  "www.streamable.com",
        "gfycat.com",      "www.gfycat.com",
        "tenor.com",       "www.tenor.com",
        "giphy.com",       "www.giphy.com",
        "bandcamp.com",    "twitch.tv",
        "mixcloud.com",    "www.mixcloud.com",
        "archive.org",     "www.archive.org",
    }
)

# Type constants
TYPE_YOUTUBE  = "youtube"
TYPE_SPOTIFY  = "spotify"
TYPE_YTDLP    = "ytdlp"
TYPE_DIRECT   = "direct"
TYPE_DRM      = "drm"
TYPE_UNKNOWN  = "unknown"


def detect(url: str) -> dict:
    """
    Returns:
    {
      "type":         TYPE_*,
      "host":         str,
      "label":        str,   # human-readable platform name
      "icon":         str,   # emoji
      "url":          str,   # normalised URL
      "is_playlist":  bool,  # True if URL points to a playlist / batch
      "batch_label":  str,   # e.g. "YouTube playlist" / "Spotify playlist"
    }
    """
    url = url.strip()
    if not url:
        return _result(TYPE_UNKNOWN, "", "Unknown", "🔗", url)

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except Exception:
        return _result(TYPE_UNKNOWN, "", "Unknown", "🔗", url)

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    from downloaders.hianime_series import is_series_page
    if is_series_page(url):
        result = _result(TYPE_YTDLP, host, 'HiAnime', '▶', url)
        result['series_capable'] = True
        return result

    # DRM first
    if _match(host, DRM_HOSTS):
        return _result(TYPE_DRM, host, _drm_label(host), "🔒", url)

    # YouTube
    if _match(host, YOUTUBE_HOSTS):
        is_pl, pl_label = _yt_playlist(parsed)
        return _result(TYPE_YOUTUBE, host, "YouTube", "▶", url,
                       is_playlist=is_pl, batch_label=pl_label)

    # Spotify
    if _match(host, SPOTIFY_HOSTS):
        is_pl, pl_label = _spotify_batch(parsed)
        return _result(TYPE_SPOTIFY, host, "Spotify", "♫", url,
                       is_playlist=is_pl, batch_label=pl_label)

    # yt-dlp supported
    if _match(host, YTDLP_HOSTS):
        label = _ytdlp_label(host)
        return _result(TYPE_YTDLP, host, label, "↓", url)

    # Direct file by extension
    path = parsed.path.lower()
    for ext in DIRECT_EXTENSIONS:
        if path.endswith(ext):
            cat = _ext_category(ext)
            return _result(TYPE_DIRECT, host, f"Direct {cat}", _ext_icon(ext), url)

    # HLS / DASH
    if ".m3u8" in url.lower() or "m3u8" in parsed.query.lower():
        return _result(TYPE_YTDLP, host, "HLS Stream", "📡", url)
    if ".mpd" in url.lower():
        return _result(TYPE_YTDLP, host, "DASH Stream", "📡", url)

    # Generic — try yt-dlp as a universal fallback
    return _result(TYPE_YTDLP, host, host or "Generic URL", "🔗", url)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _result(type_: str, host: str, label: str, icon: str, url: str,
            is_playlist: bool = False, batch_label: str = "") -> dict:
    return {
        "type":        type_,
        "host":        host,
        "label":       label,
        "icon":        icon,
        "url":         url,
        "is_playlist": is_playlist,
        "batch_label": batch_label,
    }


def _match(host: str, host_set: set) -> bool:
    return host in host_set or any(host.endswith("." + h) for h in host_set)


def _yt_playlist(parsed) -> tuple:
    """Return (is_playlist, description) for a YouTube URL."""
    qs = parse_qs(parsed.query)
    # Explicit playlist ID
    if "list" in qs:
        pl_id = qs["list"][0]
        if pl_id.startswith("PL") or pl_id.startswith("UU") or pl_id.startswith("FL"):
            return True, "YouTube playlist"
        return True, "YouTube queue/mix"
    # Channel / user pages
    path = parsed.path.lower()
    if any(seg in path for seg in ("/channel/", "/user/", "/c/", "/@")):
        if any(seg in path for seg in ("/videos", "/playlists", "/streams")):
            return True, "YouTube channel page"
    return False, ""


def _spotify_batch(parsed) -> tuple:
    path = parsed.path.lower()
    if "/playlist/" in path:
        return True, "Spotify playlist"
    if "/album/" in path:
        return True, "Spotify album"
    if "/artist/" in path:
        return True, "Spotify artist (top tracks)"
    return False, ""


def _drm_label(host: str) -> str:
    mapping = {
        "netflix.com":       "Netflix",
        "primevideo.com":    "Prime Video",
        "amazon.com":        "Amazon Video",
        "hotstar.com":       "Hotstar",
        "disneyplus.com":    "Disney+",
        "hulu.com":          "Hulu",
        "max.com":           "Max",
        "peacocktv.com":     "Peacock",
        "paramountplus.com": "Paramount+",
        "crunchyroll.com":   "Crunchyroll",
        "zee5.com":          "ZEE5",
        "sonyliv.com":       "SonyLIV",
    }
    for k, v in mapping.items():
        if host.endswith(k):
            return v
    return "Streaming Service (DRM)"


def _ytdlp_label(host: str) -> str:
    mapping = {
        "twitter.com": "Twitter / X", "x.com": "Twitter / X",
        "instagram.com": "Instagram", "facebook.com": "Facebook",
        "fb.watch": "Facebook", "tiktok.com": "TikTok",
        "reddit.com": "Reddit", "v.redd.it": "Reddit",
        "vimeo.com": "Vimeo", "twitch.tv": "Twitch",
        "soundcloud.com": "SoundCloud", "pinterest.com": "Pinterest",
        "pin.it": "Pinterest", "dailymotion.com": "Dailymotion",
        "bilibili.com": "Bilibili", "rumble.com": "Rumble",
        "odysee.com": "Odysee", "archive.org": "Internet Archive",
        "mixcloud.com": "Mixcloud", "bandcamp.com": "Bandcamp",
        "drive.google.com": "Google Drive", "docs.google.com": "Google Drive",
    }
    for k, v in mapping.items():
        if host.endswith(k):
            return v
    return host


def _ext_category(ext: str) -> str:
    if ext in {".jpg",".jpeg",".png",".gif",".webp",".svg",".bmp",".avif",".ico",".tiff"}:
        return "Image"
    if ext in {".mp4",".mkv",".avi",".mov",".wmv",".flv",".webm",".m4v",".3gp",".ts"}:
        return "Video"
    if ext in {".mp3",".flac",".wav",".aac",".ogg",".m4a",".wma",".opus",".aiff"}:
        return "Audio"
    if ext in {".pdf",".docx",".doc",".xlsx",".pptx",".txt",".csv",".epub"}:
        return "Document"
    if ext in {".zip",".rar",".7z",".tar",".gz",".bz2",".iso"}:
        return "Archive"
    return "File"


def _ext_icon(ext: str) -> str:
    icons = {"Image":"🖼","Video":"🎬","Audio":"🎵",
             "Document":"📄","Archive":"📦","File":"📁"}
    return icons.get(_ext_category(ext), "📁")
