"""
RuneFetch UI WebSocket server — Path B.

Listens on ws://127.0.0.1:8770 for the pywebview frontend.

Commands (client → server):
  ping, snapshot, detect, fetch_formats, add, pause, resume, cancel, remove,
  pause_all, resume_all, clear_completed, set_concurrency, set_throttle,
  get_history, delete_history, clear_history, redownload,
  open_folder, save_settings, get_settings, check_file_exists

Events (server → all clients):
  item_update, item_removed, item_log, history_added, toast,
  formats_ready, settings, bridge_url, status_update
"""

import asyncio
import json
import logging
import os
import sys
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

_log = logging.getLogger(__name__)

DEFAULT_PORT = 8770
_BROADCAST_INTERVAL = 0.1


class UIServer:
    def __init__(self, engine, cfg: dict, port: int = DEFAULT_PORT):
        self.engine = engine
        self.cfg    = cfg
        self.port   = port
        self.token  = cfg.get("ui_token", "")

        self._clients: set = set()
        self._clients_lock: asyncio.Lock | None = None

        self._thread: threading.Thread | None = None
        self._loop:   asyncio.AbstractEventLoop | None = None
        self._started = False
        self._stop_event = None
        self._executor = ThreadPoolExecutor(max_workers=4,
                                            thread_name_prefix="rf-ui-fmt")

    def start(self):
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="rf-ws-ui"
        )
        self._thread.start()

    def stop(self):
        if self._loop and self._loop.is_running() and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        self._executor.shutdown(wait=False)

    @property
    def ws_url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    # ── asyncio side ──────────────────────────────────────────────────────────

    def _run(self):
        try:
            import websockets  # noqa: F401
        except ImportError:
            _log.error("UI server disabled — 'websockets' not installed.")
            return

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._clients_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            _log.error("UI server crashed: %s", e)
        finally:
            self._loop.close()

    async def _serve(self):
        import websockets

        async with websockets.serve(
            self._handler, "127.0.0.1", self.port, max_size=2 ** 20,
        ):
            _log.info("UI server listening on %s", self.ws_url)
            broadcaster = asyncio.create_task(self._broadcast_loop())
            try:
                await self._stop_event.wait()
            finally:
                broadcaster.cancel()
                await asyncio.gather(broadcaster, return_exceptions=True)

    # ── Per-connection handler ────────────────────────────────────────────────

    async def _handler(self, websocket):
        # Reject cross-site WebSocket connections (defense-in-depth on top of
        # the token). A real website Origin is never the local web UI.
        from utils import net_guard
        origin = net_guard.get_ws_origin(websocket)
        if not net_guard.ws_origin_allowed(origin):
            _log.warning("UI: rejected connection with disallowed Origin %r", origin)
            await websocket.close(1008, "forbidden origin")
            return

        async with self._clients_lock:
            self._clients.add(websocket)

        # Push snapshot + settings immediately on connect
        try:
            for d in self.engine.snapshot():
                await websocket.send(json.dumps({"event": "item_update", "data": d}))
            await websocket.send(json.dumps({
                "event": "settings", "data": self._safe_cfg()
            }))
        except Exception:
            pass

        try:
            async for raw in websocket:
                response = await self._dispatch(raw)
                await websocket.send(json.dumps(response))
        except Exception as exc:
            _log.debug("UI: connection closed: %s", exc)
        finally:
            async with self._clients_lock:
                self._clients.discard(websocket)

    # ── Command dispatcher ────────────────────────────────────────────────────

    async def _dispatch(self, raw: str) -> dict:
        try:
            msg = json.loads(raw)
        except (ValueError, TypeError):
            return {"ok": False, "error": "invalid_json"}

        if not isinstance(msg, dict):
            return {"ok": False, "error": "expected_object"}

        if msg.get("token") != self.token:
            return {"ok": False, "error": "unauthorized"}

        action = msg.get("action", "")

        try:
            # ── Ping ──────────────────────────────────────────────────────
            if action == "ping":
                from core.version import __version__
                return {"ok": True, "app": "RuneFetch", "version": __version__}

            # ── Snapshot ──────────────────────────────────────────────────
            if action == "snapshot":
                return {"ok": True, "items": self.engine.snapshot()}

            # ── Detect URL ────────────────────────────────────────────────
            if action == "detect":
                url = (msg.get("url") or "").strip()
                if not url:
                    return {"ok": False, "error": "no_url"}
                from core.detector import detect
                return {"ok": True, "detection": detect(url)}

            # ── Fetch formats (async, result via event) ────────────────────
            if action == "fetch_formats":
                url    = (msg.get("url") or "").strip()
                req_id = msg.get("request_id", "")
                proxy  = msg.get("proxy") or self.cfg.get("proxy", "")
                asyncio.ensure_future(
                    self._fetch_formats_async(url, req_id, proxy)
                )
                return {"ok": True, "pending": True, "request_id": req_id}

            # ── Add to queue ──────────────────────────────────────────────
            if action == "add":
                url  = (msg.get("url") or "").strip()
                opts = msg.get("opts") or {}
                if not url:
                    return {"ok": False, "error": "no_url"}
                # prompt_per_file: save_path comes from client (chosen via choose_folder)
                item_id = self.engine.add(url, opts)
                return {"ok": True, "id": item_id}

            # ── Lifecycle ─────────────────────────────────────────────────
            if action == "pause":
                self.engine.pause(msg.get("id", ""))
                return {"ok": True}

            if action == "resume":
                self.engine.resume(msg.get("id", ""))
                return {"ok": True}

            if action == "cancel":
                self.engine.cancel(msg.get("id", ""))
                return {"ok": True}

            if action == "remove":
                self.engine.remove(msg.get("id", ""))
                return {"ok": True}

            if action == "pause_all":
                self.engine.pause_all()
                return {"ok": True}

            if action == "resume_all":
                self.engine.resume_all()
                return {"ok": True}

            if action == "clear_completed":
                self.engine.clear_completed()
                return {"ok": True}

            # ── Concurrency / throttle ────────────────────────────────────
            if action == "set_concurrency":
                n = int(msg.get("value", 2))
                self.engine.set_concurrency(n)
                self.cfg["max_concurrent"] = n
                return {"ok": True}

            if action == "set_throttle":
                kbps = int(msg.get("value", 0))
                self.engine.set_throttle(kbps)
                self.cfg["throttle_kbps"] = kbps
                return {"ok": True}

            # ── History ───────────────────────────────────────────────────
            if action == "get_history":
                return {"ok": True, "history": self.engine.get_history()}

            if action == "delete_history":
                entry_id = msg.get("id", "")
                found = self.engine.delete_history_entry(entry_id)
                return {"ok": True, "found": found}

            if action == "clear_history":
                self.engine.clear_history()
                await self._broadcast({"event": "history_cleared", "data": {}})
                return {"ok": True}

            # ── Redownload ────────────────────────────────────────────────
            if action == "redownload":
                entry_id = msg.get("id", "")
                d = self._find_history(entry_id)
                if not d:
                    return {"ok": False, "error": "not_found"}
                new_id = self.engine.add(d["url"], {
                    "title":        d.get("title", ""),
                    "source_label": d.get("source_label", ""),
                    "source_icon":  d.get("source_icon", ""),
                    "fmt":          d.get("fmt", ""),
                    "quality":      d.get("quality", ""),
                    "dl_type":      d.get("dl_type", "ytdlp"),
                    "save_path":    d.get("save_path", ""),
                })
                return {"ok": True, "id": new_id}

            # ── Open folder ───────────────────────────────────────────────
            if action == "open_folder":
                path = msg.get("path", "")
                _open_folder(path)
                return {"ok": True}

            # ── File existence check ──────────────────────────────────────
            if action == "check_file_exists":
                save_path = msg.get("save_path", "")
                title     = msg.get("title", "")
                return {"ok": True, **_check_file_exists(save_path, title)}

            # ── Settings ──────────────────────────────────────────────────
            if action == "save_settings":
                patch = msg.get("settings") or {}
                self.cfg.update(patch)
                from utils.settings import save
                save(self.cfg)
                # Apply immediately
                if "max_concurrent" in patch:
                    self.engine.set_concurrency(int(patch["max_concurrent"]))
                if "throttle_kbps" in patch:
                    self.engine.set_throttle(int(patch["throttle_kbps"]))
                await self._broadcast({"event": "settings", "data": self._safe_cfg()})
                return {"ok": True}

            if action == "get_settings":
                return {"ok": True, "settings": self._safe_cfg()}

            # ── Updates ───────────────────────────────────────────────────
            if action == "check_update":
                from core import updater
                # Network call — keep it off the event loop.
                force = bool(msg.get("force", True))
                info = await asyncio.get_event_loop().run_in_executor(
                    self._executor, updater.check_for_update, force, self.cfg
                )
                if self.cfg.get("last_update_check"):
                    from utils.settings import save
                    save(self.cfg)
                return {"ok": True, "update": info}

            if action == "install_update":
                asset_url = msg.get("asset_url", "")
                if not asset_url:
                    return {"ok": False, "error": "no_asset_url"}
                size = int(msg.get("asset_size") or 0)
                asyncio.ensure_future(self._install_update_async(asset_url, size))
                return {"ok": True, "started": True}

            if action == "open_releases_page":
                from core import updater
                updater.open_releases_page()
                return {"ok": True}

            return {"ok": False, "error": f"unknown_action:{action}"}

        except Exception as exc:
            _log.error("UI dispatch error (action=%s): %s", action, exc,
                       exc_info=True)
            return {"ok": False, "error": str(exc)}

    # ── Format fetch ──────────────────────────────────────────────────────────

    async def _fetch_formats_async(self, url: str, req_id: str, proxy: str):
        loop = asyncio.get_event_loop()
        try:
            formats, title = await loop.run_in_executor(
                self._executor, _fetch_formats_sync, url, proxy
            )
            payload = {
                "event": "formats_ready",
                "data": {"request_id": req_id, "formats": formats, "title": title},
            }
        except Exception as exc:
            _log.warning("Format fetch failed for %s: %s", url[:60], exc)
            payload = {
                "event": "formats_ready",
                "data": {"request_id": req_id, "formats": [], "title": "",
                         "error": str(exc)},
            }
        await self._broadcast(payload)

    # ── Update download / install ─────────────────────────────────────────────

    async def _install_update_async(self, asset_url: str, expected_size: int = 0):
        """
        Download the update, then hand off to the installer and quit.

        Progress is broadcast as update_progress events so the UI can show a
        bar; the app keeps running normally until the download completes, so a
        failure here leaves the user exactly where they were.
        """
        from core import updater

        loop = asyncio.get_event_loop()

        def _progress(pct, done, total):
            # Called from the worker thread — hop back onto the loop to send.
            asyncio.run_coroutine_threadsafe(
                self._broadcast({
                    "event": "update_progress",
                    "data": {"percent": round(pct, 1), "done": done, "total": total},
                }), loop,
            )

        try:
            path = await loop.run_in_executor(
                self._executor, updater.download_update,
                asset_url, _progress, expected_size,
            )
        except Exception as exc:
            _log.error("Update download failed: %s", exc)
            await self._broadcast({
                "event": "update_failed",
                "data": {"error": str(exc)},
            })
            return

        await self._broadcast({
            "event": "update_ready", "data": {"path": path},
        })
        # Let the UI paint "Restarting…" before the process disappears.
        await asyncio.sleep(1.0)

        def _on_quit():
            try:
                from core.queue_persistence import save_queue
                save_queue(self.engine._qm.get_items())
            except Exception as exc:
                _log.warning("Could not save queue before update: %s", exc)

        ok = await loop.run_in_executor(
            self._executor, updater.install_and_restart, path, _on_quit
        )
        if not ok:
            await self._broadcast({
                "event": "update_failed",
                "data": {"error": "Could not launch the installer. "
                                  "The downloaded file has been revealed instead."},
            })

    # ── Broadcaster ───────────────────────────────────────────────────────────

    async def _broadcast_loop(self):
        while True:
            await asyncio.sleep(_BROADCAST_INTERVAL)
            events = self.engine.drain_events()
            for ev in events:
                await self._broadcast(ev)

    async def _broadcast(self, payload: dict):
        if not self._clients:
            return
        raw = json.dumps(payload)
        async with self._clients_lock:
            dead = set()
            for ws in self._clients:
                try:
                    await ws.send(raw)
                except Exception:
                    dead.add(ws)
            self._clients -= dead

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _safe_cfg(self) -> dict:
        skip = {"ui_token"}   # bridge_token IS sent so the web UI can display/copy it
        return {k: v for k, v in self.cfg.items() if k not in skip}

    def _find_history(self, entry_id: str) -> dict | None:
        for entry in self.engine.get_history():
            if entry.get("id") == entry_id:
                return entry
        return None


# ── Standalone helpers (no class dependency) ──────────────────────────────────

def _open_folder(path: str):
    try:
        path = os.path.normpath(path)
        if not os.path.exists(path):
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as exc:
        _log.warning("open_folder(%s): %s", path, exc)


def _check_file_exists(save_path: str, title: str) -> dict:
    try:
        if not save_path or not title or not os.path.isdir(save_path):
            return {"exists": False, "filename": ""}
        safe = title[:60].replace("/", "_").replace("\\", "_")
        for fname in os.listdir(save_path):
            if safe.lower()[:20] in fname.lower():
                return {"exists": True, "filename": fname}
    except Exception as exc:
        _log.warning("check_file_exists: %s", exc)
    return {"exists": False, "filename": ""}


def _fetch_formats_sync(url: str, proxy: str) -> tuple[list, str]:
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    if proxy:
        opts["proxy"] = proxy
    from downloaders.hianime import create_ytdlp
    with create_ytdlp(opts, url) as ydl:
        info    = ydl.extract_info(url, download=False)
        formats = info.get("formats") or []
        title   = info.get("title", "")
    slim = []
    for f in formats:
        slim.append({
            "height":          f.get("height"),
            "vcodec":          f.get("vcodec") or "",
            "acodec":          f.get("acodec") or "",
            "ext":             f.get("ext") or "",
            "filesize":        f.get("filesize"),
            "filesize_approx": f.get("filesize_approx"),
            "format_note":     f.get("format_note") or "",
        })
    return slim, title
