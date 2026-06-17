"""
Router — dispatches a DownloadItem to the correct backend engine.
"""

import ipaddress
import socket
from urllib.parse import urlparse

from core.detector import (
    TYPE_YOUTUBE, TYPE_SPOTIFY, TYPE_YTDLP, TYPE_DIRECT, TYPE_DRM, TYPE_UNKNOWN
)

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def _is_private_url(url: str) -> bool:
    """Return True if the URL resolves to a private/loopback address."""
    try:
        host = urlparse(url).hostname or ""
        addr = ipaddress.ip_address(socket.gethostbyname(host))
        return any(addr in net for net in _PRIVATE_NETS)
    except Exception:
        return False


def run_download(item, progress_cb):
    """Called in a worker thread. Raises on unrecoverable failure."""
    t = item.dl_type

    if t == TYPE_DRM:
        raise Exception(
            "⛔ DRM-protected content cannot be downloaded by RuneFetch.\n"
            "Netflix, Prime Video, Hotstar, and Disney+ use Widevine encryption.\n"
            "Use the official app's built-in offline/download feature instead."
        )

    if t in (TYPE_YOUTUBE, TYPE_YTDLP):
        from downloaders.ytdlp_downloader import download_ytdlp
        download_ytdlp(item, progress_cb)

    elif t == TYPE_SPOTIFY:
        from downloaders.spotdl_downloader import download_spotify
        download_spotify(item, progress_cb)

    elif t == TYPE_DIRECT:
        # Use segmented downloader; it auto-falls back to single-stream if
        # the server does not support Range requests.
        from downloaders.segmented_downloader import download as download_segmented
        ok = download_segmented(item, progress_cb)
        if not ok:
            err = getattr(item, "error", "Download failed")
            raise Exception(err)

    else:
        # Generic fallback: block internal addresses before handing to yt-dlp
        if _is_private_url(item.url):
            raise Exception(
                "⛔ Download blocked: URL resolves to a private/local address.\n"
                "RuneFetch does not fetch content from internal network hosts."
            )
        try:
            from downloaders.ytdlp_downloader import download_ytdlp
            download_ytdlp(item, progress_cb)
        except Exception:
            from downloaders.direct_downloader import download_direct
            download_direct(item, progress_cb)
