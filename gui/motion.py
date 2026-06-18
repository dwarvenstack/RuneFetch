"""
RuneFetch "Forge" motion helpers — gui/motion.py

Factory functions for all animations so no widget hand-rolls its own.
Duration tokens match the Forge handoff §7.1.

Hard constraint: a QWidget can hold only ONE QGraphicsEffect at a time.
Put shadows on the card frame and opacity effects on inner containers.
"""

from PyQt6.QtCore import (
    QPropertyAnimation, QVariantAnimation, QEasingCurve,
    QParallelAnimationGroup, QSequentialAnimationGroup,
    QPoint, QRect, Qt,
)
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor

# ── Duration tokens (ms) ──────────────────────────────────────────────────
T_INSTANT = 90
T_FAST    = 160
T_BASE    = 220
T_SLOW    = 320
T_POP     = 260
T_AMBIENT = 2000   # default loop period

# ── Easing curves ─────────────────────────────────────────────────────────
EASE_OUT_CUBIC = QEasingCurve.Type.OutCubic
EASE_OUT_BACK  = QEasingCurve.Type.OutBack
EASE_IN_OUT    = QEasingCurve.Type.InOutSine
EASE_OUT_QUAD  = QEasingCurve.Type.OutQuad


# ── Fade in / out ─────────────────────────────────────────────────────────

def fade_in(widget, duration: int = T_BASE) -> QPropertyAnimation:
    """Fade widget from 0 → 1 opacity. Installs a QGraphicsOpacityEffect."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(EASE_OUT_CUBIC)
    return anim


def fade_out(widget, duration: int = T_BASE,
             delete_after: bool = False) -> QPropertyAnimation:
    """Fade widget from current opacity → 0. Optionally calls deleteLater."""
    effect = widget.graphicsEffect()
    if not isinstance(effect, QGraphicsOpacityEffect):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(effect.opacity())
    anim.setEndValue(0.0)
    anim.setEasingCurve(EASE_OUT_CUBIC)
    if delete_after:
        anim.finished.connect(widget.deleteLater)
    return anim


# ── Collapse height ───────────────────────────────────────────────────────

def collapse_height(widget, target_h: int = 0,
                    duration: int = T_SLOW) -> QPropertyAnimation:
    """Animate maximumHeight from current → target_h (0 to collapse)."""
    anim = QPropertyAnimation(widget, b"maximumHeight", widget)
    anim.setDuration(duration)
    anim.setStartValue(widget.height())
    anim.setEndValue(target_h)
    anim.setEasingCurve(EASE_OUT_CUBIC)
    return anim


def expand_height(widget, target_h: int,
                  duration: int = T_SLOW) -> QPropertyAnimation:
    """Animate maximumHeight from 0 → target_h."""
    widget.setMaximumHeight(0)
    anim = QPropertyAnimation(widget, b"maximumHeight", widget)
    anim.setDuration(duration)
    anim.setStartValue(0)
    anim.setEndValue(target_h)
    anim.setEasingCurve(EASE_OUT_CUBIC)
    return anim


# ── Card entrance / exit ──────────────────────────────────────────────────

def card_enter(widget, target_h: int,
               duration: int = T_SLOW) -> QParallelAnimationGroup:
    """Parallel: expand height 0→target AND fade 0→1."""
    grp = QParallelAnimationGroup(widget)
    grp.addAnimation(expand_height(widget, target_h, duration))
    grp.addAnimation(fade_in(widget, duration))
    return grp


def card_exit(widget, duration: int = T_SLOW,
              delete_after: bool = True) -> QParallelAnimationGroup:
    """Parallel: collapse height→0 AND fade→0, then deleteLater."""
    grp = QParallelAnimationGroup(widget)
    grp.addAnimation(collapse_height(widget, 0, duration))
    grp.addAnimation(fade_out(widget, duration, delete_after=False))
    if delete_after:
        grp.finished.connect(widget.deleteLater)
    return grp


# ── Drop-shadow (card resting + hover lift) ───────────────────────────────

def apply_shadow(widget,
                 blur: int = 12,
                 offset_y: int = 4,
                 colour: str = "#000000",
                 alpha: int = 100) -> QGraphicsDropShadowEffect:
    """Install and return a QGraphicsDropShadowEffect on widget."""
    shadow = QGraphicsDropShadowEffect(widget)
    c = QColor(colour)
    c.setAlpha(alpha)
    shadow.setColor(c)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, offset_y)
    widget.setGraphicsEffect(shadow)
    return shadow


def animate_shadow_blur(shadow: QGraphicsDropShadowEffect,
                        start_blur: int, end_blur: int,
                        duration: int = T_FAST) -> QPropertyAnimation:
    """Animate blurRadius on an existing QGraphicsDropShadowEffect."""
    anim = QPropertyAnimation(shadow, b"blurRadius")
    anim.setDuration(duration)
    anim.setStartValue(start_blur)
    anim.setEndValue(end_blur)
    anim.setEasingCurve(EASE_OUT_CUBIC)
    return anim


# ── Colour transition (badge cross-fade, border lerp) ────────────────────

def colour_anim(start: str, end: str,
                duration: int = T_BASE,
                parent=None) -> QVariantAnimation:
    """QVariantAnimation interpolating between two QColor hex strings."""
    anim = QVariantAnimation(parent)
    anim.setDuration(duration)
    anim.setStartValue(QColor(start))
    anim.setEndValue(QColor(end))
    anim.setEasingCurve(EASE_OUT_CUBIC)
    return anim


# ── Badge pulse (scale 1.0 → 1.08 → 1.0) ─────────────────────────────────
# QSS can't scale transforms, so we simulate by briefly expanding padding.
# For a true scale you would subclass QWidget and use QPainter transform.
# This gives a subtle "pop" by animating the widget geometry outward then back.

def badge_pulse(widget, duration: int = T_POP) -> QSequentialAnimationGroup:
    """Briefly expand then contract the widget geometry to simulate a pulse."""
    orig = widget.geometry()
    expand = QRect(orig.x() - 2, orig.y() - 1,
                   orig.width() + 4, orig.height() + 2)
    grp = QSequentialAnimationGroup(widget)

    out = QPropertyAnimation(widget, b"geometry")
    out.setDuration(duration // 2)
    out.setStartValue(orig)
    out.setEndValue(expand)
    out.setEasingCurve(EASE_OUT_BACK)

    back = QPropertyAnimation(widget, b"geometry")
    back.setDuration(duration // 2)
    back.setStartValue(expand)
    back.setEndValue(orig)
    back.setEasingCurve(EASE_OUT_CUBIC)

    grp.addAnimation(out)
    grp.addAnimation(back)
    return grp


# ── Ambient pulse (status dot, 0.5 → 1.0 loop) ───────────────────────────

def ambient_pulse(widget, low: float = 0.5, high: float = 1.0,
                  period: int = T_AMBIENT) -> QPropertyAnimation:
    """Looping opacity pulse on widget. Installs a QGraphicsOpacityEffect."""
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(high)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(period)
    anim.setStartValue(high)
    anim.setEndValue(low)
    anim.setEasingCurve(EASE_IN_OUT)
    anim.setLoopCount(-1)
    return anim


# ── Vertical float (empty-state rune, ±6px) ──────────────────────────────

def ambient_float(widget, amplitude: int = 6,
                  period: int = 3000) -> QPropertyAnimation:
    """Gentle vertical drift for the empty-state rune mark."""
    base_y = widget.y()
    anim = QPropertyAnimation(widget, b"pos", widget)
    anim.setDuration(period)
    anim.setStartValue(QPoint(widget.x(), base_y))
    anim.setEndValue(QPoint(widget.x(), base_y + amplitude))
    anim.setEasingCurve(EASE_IN_OUT)
    anim.setLoopCount(-1)
    return anim


# ── Nav indicator slide ───────────────────────────────────────────────────

def slide_geometry(widget, target: QRect,
                   duration: int = T_BASE) -> QPropertyAnimation:
    """Slide widget to a new geometry (used for nav active indicator)."""
    anim = QPropertyAnimation(widget, b"geometry", widget)
    anim.setDuration(duration)
    anim.setStartValue(widget.geometry())
    anim.setEndValue(target)
    anim.setEasingCurve(EASE_OUT_CUBIC)
    return anim


# ── Sidebar width (collapse / expand) ────────────────────────────────────

def animate_sidebar_width(widget, target_width: int,
                           duration: int = T_BASE) -> QParallelAnimationGroup:
    """Animate both min and max width together for a smooth sidebar slide."""
    grp = QParallelAnimationGroup(widget)

    mn = QPropertyAnimation(widget, b"minimumWidth")
    mn.setDuration(duration)
    mn.setStartValue(widget.minimumWidth())
    mn.setEndValue(target_width)
    mn.setEasingCurve(EASE_OUT_CUBIC)

    mx = QPropertyAnimation(widget, b"maximumWidth")
    mx.setDuration(duration)
    mx.setStartValue(widget.maximumWidth())
    mx.setEndValue(target_width)
    mx.setEasingCurve(EASE_OUT_CUBIC)

    grp.addAnimation(mn)
    grp.addAnimation(mx)
    return grp
