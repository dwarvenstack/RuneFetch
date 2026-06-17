"""
WaveformProgress — RuneFetch's signature progress visualisation.

Key behaviour
─────────────
• _target_progress  — the value set externally (can jump)
• _display_progress — what is actually rendered (glides toward target)

Every 60 FPS tick:
  1. _display_progress moves toward _target_progress via lerp / easing
  2. _offset advances so the wave scrolls sideways
  3. Widget repaints

This means when a playlist track finishes and progress jumps from e.g.
33 → 67, the fill smoothly travels across the bar over ~0.6 s instead
of teleporting. Single-file downloads feel equally smooth since the
worker already reports fine-grained byte-level progress, and the lerp
just adds a tiny trailing smoothness.

Lerp speed: EASE_SPEED controls how fast the bar catches up.
  • Higher = snappier (catches up in fewer frames)
  • Lower  = more cinematic but lags behind real progress

Wave shape: Catmull-Rom cubic Bézier — no jagged lineTo segments.
"""

import math
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import (
    QPainter, QLinearGradient, QColor, QPainterPath,
    QPen, QBrush,
)

# ── Gradient presets ─────────────────────────────────────────────────────────
GRADIENT_PRESETS = {
    "cyan_blue":    ("#00d9ff", "#0099ff"),
    "orange_red":   ("#ff9f43", "#ff6b6b"),
    "pink_orange":  ("#ff6b9d", "#ff9f43"),
    "purple_cyan":  ("#9d4edd", "#00d9ff"),
    "green":        ("#2dd4a0", "#1a9b74"),
    "red":          ("#ff6b6b", "#cc3333"),
    "muted":        ("#4a5070", "#2a2f3d"),
}


class WaveformProgress(QWidget):
    """
    Animated waveform progress bar with smooth eased fill motion.

    Public API
    ----------
    set_progress(value: float)   — set target 0–100; bar glides there
    set_gradient(key: str)       — switch colour preset
    progress  (property)         — current TARGET value (not display)
    """

    # ── Tuning ────────────────────────────────────────────────────────────────
    AMPLITUDE   = 5.5     # px wave half-height
    WAVELENGTH  = 80.0    # px per full sine cycle
    WAVE_SPEED  = 3.2     # px/frame scroll speed
    FPS         = 60
    TRACK_H     = 3.0     # unfilled track height px
    SAMPLES     = 3       # sample multiplier for Bézier smoothness

    # How fast _display_progress eases toward _target_progress.
    # Each frame: display += (target - display) * EASE_SPEED
    # 0.08 ≈ reaches target in ~0.5 s; 0.15 ≈ ~0.3 s
    EASE_SPEED  = 0.09

    # Snap threshold — if difference < this px-equivalent %, just snap
    SNAP_THRESH = 0.05    # percent (not pixels)

    def __init__(self, parent=None, gradient_key: str = "cyan_blue",
                 height: int = 28):
        super().__init__(parent)
        self._target_progress  = 0.0   # what the downloader reported
        self._display_progress = 0.0   # what we're actually drawing
        self._gradient  = gradient_key
        self._offset    = 0.0
        self._animating = False

        self.setFixedHeight(height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(60)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_progress(self, value: float):
        """Set the target progress (0–100). Display glides there smoothly."""
        value = max(0.0, min(100.0, float(value)))
        self._target_progress = value

        # Start timer whenever there's anything to render
        if value > 0.0 and not self._animating:
            self._start()
        elif value == 0.0 and self._animating:
            self._display_progress = 0.0
            self._stop()

    def set_gradient(self, key: str):
        if key in GRADIENT_PRESETS:
            self._gradient = key
            self.update()

    @property
    def progress(self) -> float:
        """Returns the TARGET progress (not the animated display value)."""
        return self._target_progress

    # ── Timer ─────────────────────────────────────────────────────────────────

    def _start(self):
        self._animating = True
        self._timer.start(1000 // self.FPS)

    def _stop(self):
        self._animating = False
        self._timer.stop()
        self.update()

    def _tick(self):
        # ── Ease display toward target ──────────────────────────────────
        diff = self._target_progress - self._display_progress
        if abs(diff) < self.SNAP_THRESH:
            # Close enough — snap and check if we should stop
            self._display_progress = self._target_progress
            if self._target_progress >= 100.0:
                # Reached 100 — keep animating one more frame so the
                # filled bar reaches the right edge, then stop
                self._offset += self.WAVE_SPEED
                self.update()
                self._stop()
                return
        else:
            # Ease: exponential approach — fast at first, slows near target
            self._display_progress += diff * self.EASE_SPEED

        # ── Scroll wave ─────────────────────────────────────────────────
        self._offset += self.WAVE_SPEED
        if self._offset > self.WAVELENGTH * 100:
            self._offset -= self.WAVELENGTH * 100

        self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Use _display_progress for all rendering — the smoothed value
        fill_x = (self._display_progress / 100.0) * w
        c1h, c2h = GRADIENT_PRESETS.get(self._gradient, GRADIENT_PRESETS["cyan_blue"])
        c1 = QColor(c1h)
        c2 = QColor(c2h)
        mid_y = h / 2.0

        # ── Unfilled track ────────────────────────────────────────────────
        if fill_x < w:
            track_y = mid_y - self.TRACK_H / 2
            track_rect = QRectF(max(fill_x, 0), track_y,
                                w - max(fill_x, 0), self.TRACK_H)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor("#23283a")))
            p.drawRoundedRect(track_rect, self.TRACK_H / 2, self.TRACK_H / 2)

        # ── Filled wave region ────────────────────────────────────────────
        if fill_x > 0.5:
            # Wave is only shown while actively animating (downloading/queued)
            # At rest (complete/paused/stopped) draw a clean flat fill
            show_wave = self._animating and self._display_progress < 99.9

            pts = self._wave_points(fill_x, mid_y, show_wave)

            # Filled area path
            fill_path = QPainterPath()
            fill_path.moveTo(0.0, h)
            fill_path.lineTo(pts[0][0], pts[0][1])
            self._smooth_path(fill_path, pts)
            fill_path.lineTo(fill_x, mid_y)
            fill_path.lineTo(fill_x, h)
            fill_path.closeSubpath()

            fg = QLinearGradient(0, 0, fill_x, 0)
            ca = QColor(c1); ca.setAlpha(170)
            cb = QColor(c2); cb.setAlpha(170)
            fg.setColorAt(0.0, ca)
            fg.setColorAt(1.0, cb)
            p.setPen(Qt.PenStyle.NoPen)
            p.fillPath(fill_path, QBrush(fg))

            if show_wave:
                # Bright wave line on top
                wave_path = QPainterPath()
                wave_path.moveTo(pts[0][0], pts[0][1])
                self._smooth_path(wave_path, pts)

                lg = QLinearGradient(0, 0, fill_x, 0)
                lg.setColorAt(0.0, c1)
                lg.setColorAt(1.0, c2)
                pen = QPen(QBrush(lg), 2.2, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(wave_path)

        p.end()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _wave_y(self, x: float, fill_x: float, mid_y: float,
                show_wave: bool) -> float:
        if not show_wave:
            return mid_y
        phase    = 2 * math.pi * (x - self._offset) / self.WAVELENGTH
        fade_in  = min(1.0, x / 50.0)
        fade_out = min(1.0, max(0.0, (fill_x - x) / 30.0))
        amp = self.AMPLITUDE * fade_in * fade_out
        return mid_y - math.sin(phase) * amp

    def _wave_points(self, fill_x: float, mid_y: float,
                     show_wave: bool) -> list:
        n = max(int(fill_x * self.SAMPLES), 4)
        return [
            (fill_x * i / n,
             self._wave_y(fill_x * i / n, fill_x, mid_y, show_wave))
            for i in range(n + 1)
        ]

    @staticmethod
    def _smooth_path(path: QPainterPath, pts: list):
        """Catmull-Rom → cubic Bézier for a smooth curve through all points."""
        if len(pts) < 2:
            return
        t = 0.5
        for i in range(1, len(pts)):
            p0 = pts[max(i - 2, 0)]
            p1 = pts[i - 1]
            p2 = pts[i]
            p3 = pts[min(i + 1, len(pts) - 1)]
            cp1x = p1[0] + (p2[0] - p0[0]) * t / 3.0
            cp1y = p1[1] + (p2[1] - p0[1]) * t / 3.0
            cp2x = p2[0] - (p3[0] - p1[0]) * t / 3.0
            cp2y = p2[1] - (p3[1] - p1[1]) * t / 3.0
            path.cubicTo(cp1x, cp1y, cp2x, cp2y, p2[0], p2[1])
