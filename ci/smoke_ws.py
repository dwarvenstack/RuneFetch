#!/usr/bin/env python3
"""
Smoke-test the WebSocket layer: UI server (web UI) and bridge (extension).

Guards the seam most likely to break on a dependency bump. websockets 14
changed the connection-handler signature, and both servers rely on the current
one — if a future release drops it, these servers stop accepting connections
while every module still imports fine. check_imports.py cannot see that; this
can, because it actually completes a request/response round trip.

Test ports are used so a running RuneFetch instance does not collide with CI.
"""

import asyncio
import json
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

UI_PORT     = 8790
BRIDGE_PORT = 8795
TIMEOUT     = 10


async def _recv_reply(ws):
    """Read until a command reply arrives, skipping pushed events."""
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), TIMEOUT))
        if "ok" in msg:
            return msg


async def run_checks(cfg) -> list:
    import websockets

    failures = []

    # ── UI server ────────────────────────────────────────────────────────────
    # Origin "file://" mimics the pywebview frontend.
    async with websockets.connect(
        f"ws://127.0.0.1:{UI_PORT}", additional_headers={"Origin": "file://"}
    ) as ws:
        await ws.send(json.dumps({"token": cfg["ui_token"], "action": "ping"}))
        reply = await _recv_reply(ws)
        if reply.get("ok") and reply.get("app") == "RuneFetch":
            print(f"OK    UI ping -> v{reply.get('version')}")
        else:
            print(f"FAIL  UI ping -> {reply}")
            failures.append("ui_ping")

        await ws.send(json.dumps({
            "token": cfg["ui_token"], "action": "detect",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        }))
        reply = await _recv_reply(ws)
        label = (reply.get("detection") or {}).get("label")
        if label == "YouTube":
            print("OK    UI detect -> YouTube")
        else:
            print(f"FAIL  UI detect -> {reply}")
            failures.append("ui_detect")

        # An unauthenticated command must be rejected.
        await ws.send(json.dumps({"token": "wrong-token", "action": "ping"}))
        reply = await _recv_reply(ws)
        if reply.get("error") == "unauthorized":
            print("OK    UI rejects bad token")
        else:
            print(f"FAIL  UI accepted bad token -> {reply}")
            failures.append("ui_auth")

    # ── Bridge ───────────────────────────────────────────────────────────────
    async with websockets.connect(
        f"ws://127.0.0.1:{BRIDGE_PORT}",
        additional_headers={"Origin": "chrome-extension://runefetch-ci"},
    ) as ws:
        await ws.send(json.dumps({"token": cfg["bridge_token"], "action": "ping"}))
        reply = await _recv_reply(ws)
        if reply.get("ok"):
            print("OK    bridge ping")
        else:
            print(f"FAIL  bridge ping -> {reply}")
            failures.append("bridge_ping")

        await ws.send(json.dumps({"token": "wrong-token", "url": "https://example.com"}))
        reply = await _recv_reply(ws)
        if reply.get("error") == "unauthorized":
            print("OK    bridge rejects bad token")
        else:
            print(f"FAIL  bridge accepted bad token -> {reply}")
            failures.append("bridge_auth")

    # A page origin must be refused outright — the connection should close.
    try:
        async with websockets.connect(
            f"ws://127.0.0.1:{UI_PORT}",
            additional_headers={"Origin": "https://evil.example.com"},
        ) as ws:
            await asyncio.wait_for(ws.recv(), TIMEOUT)
        print("FAIL  UI accepted a website Origin")
        failures.append("ui_origin")
    except Exception:
        print("OK    UI rejects website Origin")

    return failures


def main() -> int:
    import logging
    logging.basicConfig(level=logging.WARNING)

    from core.engine import EngineFacade
    from core.ui_server import UIServer
    from core.bridge import LocalBridge

    # A self-contained config — never touch the developer's ~/.runefetch.
    cfg = {
        "save_path":      tempfile.mkdtemp(prefix="runefetch_ci_"),
        "ui_token":       "ci-ui-token",
        "bridge_token":   "ci-bridge-token",
        "max_concurrent": 2,
        "throttle_kbps":  0,
        "keep_history":   False,
    }

    engine = EngineFacade(cfg)
    ui     = UIServer(engine=engine, cfg=cfg, port=UI_PORT)
    bridge = LocalBridge(token=cfg["bridge_token"], port=BRIDGE_PORT)
    ui.start()
    bridge.start()
    time.sleep(2)   # let both asyncio loops bind their ports

    try:
        failures = asyncio.run(run_checks(cfg))
    except Exception as exc:
        print(f"FAIL  smoke test raised {type(exc).__name__}: {exc}")
        return 1
    finally:
        ui.stop()
        bridge.stop()

    if failures:
        print(f"\nWebSocket smoke test failed: {', '.join(failures)}")
        return 1

    print("\nWebSocket layer OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
