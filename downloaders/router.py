"""
Router — dispatches a DownloadItem to the correct backend engine.
"""

from core.detector import (
    TYPE_YOUTUBE, TYPE_SPOTIFY, TYPE_YTDLP, TYPE_DIRECT, TYPE_DRM, TYPE_UNKNOWN
)


def run_download(item, progress_cb):
    """Called in a worker thread. Raises on unrecoverable failure."""
    t = item.dl_type

    if t == TYPE_DRM:
        raise Exception(
            "⛔ DRM-protected content cannot be downloaded.\n"
            "Netflix, Prime Video, Hotstar, and Disney+ use Widevine encryption.\n"
            "Use the official app's offline/download feature instead."
        )

    if t in (TYPE_YOUTUBE, TYPE_YTDLP):
        from downloaders.ytdlp_downloader import download_ytdlp
        download_ytdlp(item, progress_cb)

    elif t == TYPE_SPOTIFY:
        from downloaders.spotdl_downloader import download_spotify
        download_spotify(item, progress_cb)

    elif t == TYPE_DIRECT:
        from downloaders.direct_downloader import download_direct
        download_direct(item, progress_cb)

    else:
        # Universal fallback: try yt-dlp first, then direct HTTP
        try:
            from downloaders.ytdlp_downloader import download_ytdlp
            download_ytdlp(item, progress_cb)
        except Exception:
            from downloaders.direct_downloader import download_direct
            download_direct(item, progress_cb)
