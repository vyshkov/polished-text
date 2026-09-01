"""Best-effort lookup of the system text caret (insertion point) position via macOS
Accessibility APIs, so the HUD can float next to the field the user is dictating into
instead of a fixed screen location.

Requires Accessibility permission - the same permission the pynput global hotkey
listener already needs (System Settings > Privacy & Security > Accessibility).
Falls back silently (returns None) if unavailable: no permission, no focused text
field, or an app that doesn't expose proper Accessibility bounds (some Electron/web
apps don't).
"""

from .logger import get_logger

try:
    import Quartz
    from ApplicationServices import (
        AXUIElementCopyAttributeValue,
        AXUIElementCopyParameterizedAttributeValue,
        AXUIElementCreateSystemWide,
        AXValueGetValue,
        kAXBoundsForRangeParameterizedAttribute,
        kAXFocusedApplicationAttribute,
        kAXFocusedUIElementAttribute,
        kAXFocusedWindowAttribute,
        kAXPositionAttribute,
        kAXSelectedTextRangeAttribute,
        kAXSizeAttribute,
        kAXValueCGPointType,
        kAXValueCGRectType,
        kAXValueCGSizeType,
    )

    HAS_ACCESSIBILITY = True
except ImportError:
    HAS_ACCESSIBILITY = False

logger = get_logger("Caret")


def get_caret_screen_rect():
    """Return (x, y, height) of the text caret in AppKit screen coordinates (origin
    bottom-left of the main display), or None if it can't be determined."""
    if not HAS_ACCESSIBILITY:
        return None
    try:
        system_wide = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(
            system_wide, kAXFocusedUIElementAttribute, None
        )
        if err or focused is None:
            return None

        err, text_range = AXUIElementCopyAttributeValue(
            focused, kAXSelectedTextRangeAttribute, None
        )
        if err or text_range is None:
            return None

        err, bounds = AXUIElementCopyParameterizedAttributeValue(
            focused, kAXBoundsForRangeParameterizedAttribute, text_range, None
        )
        if err or bounds is None:
            return None

        ok, rect = AXValueGetValue(bounds, kAXValueCGRectType, None)
        if not ok:
            return None

        # Sanity check caret dimensions
        if rect.size.height <= 0 or rect.size.height > 500:
            return None
        if rect.origin.x == 0 and rect.origin.y == 0 and rect.size.width == 0:
            return None

        # Accessibility coordinates have their origin at the top-left of the main screen;
        # AppKit screen coordinates have their origin at the bottom-left. Convert.
        main_screen_height = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.height
        x = rect.origin.x
        y = main_screen_height - rect.origin.y - rect.size.height
        return (x, y, rect.size.height)
    except Exception as e:
        logger.debug("get_caret_screen_rect failed: %s", e)
        return None


def get_focused_window_rect():
    """Fallback for apps that don't expose per-caret Accessibility bounds (common in
    GPU-rendered terminals like Ghostty/Alacritty/Kitty, which draw text themselves instead
    of using a standard NSTextView). Returns the frontmost app's focused window frame
    (x, y, width, height) in AppKit screen coordinates, or None.
    """
    if not HAS_ACCESSIBILITY:
        return None
    try:
        system_wide = AXUIElementCreateSystemWide()
        err, app = AXUIElementCopyAttributeValue(system_wide, kAXFocusedApplicationAttribute, None)
        if err or app is None:
            return None

        err, window = AXUIElementCopyAttributeValue(app, kAXFocusedWindowAttribute, None)
        if err or window is None:
            return None

        err, pos_value = AXUIElementCopyAttributeValue(window, kAXPositionAttribute, None)
        if err or pos_value is None:
            return None
        err, size_value = AXUIElementCopyAttributeValue(window, kAXSizeAttribute, None)
        if err or size_value is None:
            return None

        ok1, point = AXValueGetValue(pos_value, kAXValueCGPointType, None)
        ok2, size = AXValueGetValue(size_value, kAXValueCGSizeType, None)
        if not (ok1 and ok2):
            return None

        if size.width < 50 or size.height < 50:
            return None

        main_screen_height = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID()).size.height
        x = point.x
        y = main_screen_height - point.y - size.height
        return (x, y, size.width, size.height)
    except Exception as e:
        logger.debug("get_focused_window_rect failed: %s", e)
        return None
