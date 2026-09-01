"""Clipboard, text selection, editability detection, and paste helpers."""

import subprocess
import time

try:
    import AppKit
    HAS_APPKIT = True
except ImportError:
    HAS_APPKIT = False

try:
    from ApplicationServices import (
        AXUIElementCreateSystemWide,
        AXUIElementCreateApplication,
        AXUIElementCopyAttributeValue,
        AXUIElementIsAttributeSettable,
        AXUIElementSetAttributeValue,
        kAXFocusedUIElementAttribute,
        kAXSelectedTextAttribute,
        kAXValueAttribute,
        kAXRoleAttribute,
        kAXRoleDescriptionAttribute,
        kAXSelectedTextRangeAttribute,
    )
    HAS_AX = True
except ImportError:
    HAS_AX = False

try:
    import Quartz
    from Quartz import (
        CGEventCreateKeyboardEvent,
        CGEventSetFlags,
        CGEventPost,
        kCGAnnotatedSessionEventTap,
        kCGEventFlagMaskCommand,
    )
    HAS_QUARTZ = True
except ImportError:
    HAS_QUARTZ = False

try:
    import pyperclip
except ImportError:
    pyperclip = None

from .config import PASTE_AUTOMATICALLY
from .logger import get_logger

logger = get_logger("Clipboard")

TERMINAL_APPS = {
    "com.mitchellh.ghostty",
    "com.googlecode.iterm2",
    "com.apple.terminal",
    "net.kovidgoyal.kitty",
    "alacritty",
    "org.alacritty",
    "io.alacritty",
    "com.github.wez.wezterm",
    "dev.warp.warp-stable",
    "co.zeit.hyper",
    "io.hyper.hyper",
}

READONLY_APPS = {
    "com.apple.finder",
    "com.apple.preview",
    "com.apple.calculator",
    "com.apple.systempreferences",
    "com.apple.systemsettings",
}


def _simulate_cmd_key(key_char: str):
    """Simulate a pure Cmd+<key> keystroke without inheriting active modifier keys (Option/Shift)."""
    if HAS_QUARTZ:
        code_map = {"a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9}
        key_code = code_map.get(key_char.lower(), 8)
        event_down = CGEventCreateKeyboardEvent(None, key_code, True)
        CGEventSetFlags(event_down, kCGEventFlagMaskCommand)
        event_up = CGEventCreateKeyboardEvent(None, key_code, False)
        CGEventSetFlags(event_up, kCGEventFlagMaskCommand)
        CGEventPost(kCGAnnotatedSessionEventTap, event_down)
        CGEventPost(kCGAnnotatedSessionEventTap, event_up)
    else:
        applescript = f'tell application "System Events" to keystroke "{key_char}" using command down'
        subprocess.run(["osascript", "-e", applescript], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def is_focused_element_editable(focused=None) -> bool:
    """Check if the given focused element (or system-wide focused element) is an editable field."""
    if not HAS_AX:
        return False
    try:
        if focused is None:
            system_wide = AXUIElementCreateSystemWide()
            err, focused = AXUIElementCopyAttributeValue(system_wide, kAXFocusedUIElementAttribute, None)
            if (err or focused is None) and HAS_APPKIT:
                ws = AppKit.NSWorkspace.sharedWorkspace()
                front_app = ws.frontmostApplication()
                if front_app:
                    app_elem = AXUIElementCreateApplication(front_app.processIdentifier())
                    err, focused = AXUIElementCopyAttributeValue(app_elem, kAXFocusedUIElementAttribute, None)
        if not focused:
            return False

        # 1. Direct settability check on AXSelectedText or AXValue
        err, sel_settable = AXUIElementIsAttributeSettable(focused, kAXSelectedTextAttribute, None)
        if not err and sel_settable:
            return True

        err, val_settable = AXUIElementIsAttributeSettable(focused, kAXValueAttribute, None)
        if not err and val_settable:
            return True

        # 2. Check Role
        err, role = AXUIElementCopyAttributeValue(focused, kAXRoleAttribute, None)
        editable_roles = {
            "AXTextField", "AXTextArea", "AXComboBox", "AXSearchField", "AXText", "AXWebArea"
        }
        if not err and role in editable_roles:
            return True

        # 3. Check Role Description
        err, desc = AXUIElementCopyAttributeValue(focused, kAXRoleDescriptionAttribute, None)
        if not err and desc:
            desc_str = str(desc).lower()
            if any(k in desc_str for k in ["editable", "text field", "text area", "input", "html"]):
                return True

        # 4. Check if text selection range exists and it's not an explicit read-only role
        readonly_roles = {"AXStaticText", "AXHeading", "AXImage", "AXLink", "AXButton", "AXMenuBar"}
        err, text_range = AXUIElementCopyAttributeValue(focused, kAXSelectedTextRangeAttribute, None)
        if not err and text_range is not None:
            if not (role and role in readonly_roles):
                return True

        return False
    except Exception:
        return False


def is_likely_editable_context(focused=None) -> bool:
    """Determine if the current context is likely editable (including web browsers and editors)."""
    if not HAS_APPKIT:
        return True

    try:
        ws = AppKit.NSWorkspace.sharedWorkspace()
        front_app = ws.frontmostApplication()
        if not front_app:
            return is_focused_element_editable(focused)

        bundle_id = (front_app.bundleIdentifier() or "").lower()

        # Terminal emulators (Ghostty, iTerm, Terminal.app, etc.):
        # Selection is purely on the terminal screen grid and cannot be overwritten via Cmd+V
        # without duplicating text on the shell prompt. Return False so we safely copy to clipboard.
        if bundle_id in TERMINAL_APPS or any(t in bundle_id for t in ["ghostty", "iterm", "terminal", "alacritty", "kitty", "wezterm"]):
            logger.debug("Terminal frontmost (%s) - using clipboard copy mode", bundle_id)
            return False

        # Explicit read-only system tools
        if bundle_id in READONLY_APPS:
            return is_focused_element_editable(focused)

        if is_focused_element_editable(focused):
            return True

        # Default to True for editors, browsers, notes, word processors, chat apps
        return True
    except Exception:
        return True


def get_selected_text_ax() -> tuple[str | None, bool, object | None]:
    """Best-effort attempt to get selected text and editability via macOS Accessibility API."""
    if not HAS_AX:
        return None, False, None
    try:
        system_wide = AXUIElementCreateSystemWide()
        err, focused = AXUIElementCopyAttributeValue(system_wide, kAXFocusedUIElementAttribute, None)
        if (err or focused is None) and HAS_APPKIT:
            ws = AppKit.NSWorkspace.sharedWorkspace()
            front_app = ws.frontmostApplication()
            if front_app:
                app_elem = AXUIElementCreateApplication(front_app.processIdentifier())
                err, focused = AXUIElementCopyAttributeValue(app_elem, kAXFocusedUIElementAttribute, None)

        if not err and focused:
            editable = is_focused_element_editable(focused)
            err, text = AXUIElementCopyAttributeValue(focused, kAXSelectedTextAttribute, None)
            if not err and text:
                text_str = str(text).strip()
                if text_str:
                    return text_str, editable, focused
            return None, editable, focused
    except Exception:
        pass
    return None, False, None


def get_selected_text_info(timeout: float = 0.25, preserve_clipboard: bool = False) -> tuple[str | None, bool, object | None]:
    """Retrieve the selected text, whether it is in an editable field, and the focused element.

    Returns: (selected_text, is_editable, focused_element)
    """
    # 1. Try Accessibility API
    ax_text, is_editable, focused_elem = get_selected_text_ax()
    if ax_text:
        return ax_text, is_editable, focused_elem

    # 2. Fallback to Cmd+C
    old_text = None
    old_count = None
    if HAS_APPKIT:
        pb = AppKit.NSPasteboard.generalPasteboard()
        old_count = pb.changeCount()
        old_text = pb.stringForType_(AppKit.NSPasteboardTypeString)
    elif pyperclip:
        try:
            old_text = pyperclip.paste()
        except Exception:
            pass
    else:
        try:
            old_text = subprocess.check_output(["pbpaste"], text=True)
        except Exception:
            pass

    # Simulate clean Cmd+C via Quartz (unaffected by physically held Option/Shift modifier keys)
    _simulate_cmd_key("c")

    start = time.time()
    selected_text = None

    while time.time() - start < timeout:
        time.sleep(0.02)
        if HAS_APPKIT:
            if pb.changeCount() != old_count:
                new_text = pb.stringForType_(AppKit.NSPasteboardTypeString)
                if new_text and new_text.strip():
                    selected_text = new_text.strip()
                    break
        elif pyperclip:
            try:
                new_text = pyperclip.paste()
                if new_text and new_text != old_text and new_text.strip():
                    selected_text = new_text.strip()
                    break
            except Exception:
                pass
        else:
            try:
                new_text = subprocess.check_output(["pbpaste"], text=True)
                if new_text and new_text != old_text and new_text.strip():
                    selected_text = new_text.strip()
                    break
            except Exception:
                pass

    if preserve_clipboard and old_text is not None and selected_text is not None:
        # Restore previous clipboard
        if HAS_APPKIT:
            pb.clearContents()
            pb.setString_forType_(old_text, AppKit.NSPasteboardTypeString)
        elif pyperclip:
            pyperclip.copy(old_text)

    if selected_text and not is_editable and focused_elem:
        is_editable = is_focused_element_editable(focused_elem)

    return selected_text, is_editable, focused_elem


def get_selected_text(timeout: float = 0.35, preserve_clipboard: bool = False) -> str | None:
    """Get the currently selected text on screen."""
    text, _, _ = get_selected_text_info(timeout=timeout, preserve_clipboard=preserve_clipboard)
    return text


WEB_BROWSER_BUNDLES = {
    "com.apple.safari",
    "com.apple.safaritechnologypreview",
    "com.google.chrome",
    "com.google.chrome.canary",
    "org.mozilla.firefox",
    "org.mozilla.firefoxdeveloperedition",
    "company.thebrowser.browser",  # Arc
    "com.microsoft.edgemac",
    "com.brave.browser",
    "com.operasoftware.opera",
    "com.vivaldi.vivaldi",
    "com.duckduckgo.macos.browser",
}


def _is_web_browser_frontmost() -> bool:
    """Check if the active/frontmost application is a web browser."""
    if not HAS_APPKIT:
        return False
    try:
        ws = AppKit.NSWorkspace.sharedWorkspace()
        front_app = ws.frontmostApplication()
        if front_app:
            bundle_id = (front_app.bundleIdentifier() or "").lower()
            return (
                bundle_id in WEB_BROWSER_BUNDLES
                or any(browser in bundle_id for browser in ["safari", "chrome", "firefox", "arc", "edge", "brave", "opera", "vivaldi"])
            )
    except Exception:
        pass
    return False


def replace_selected_text(text: str, focused_elem: object = None) -> bool:
    """Replace the currently selected text with new text in the active editable field."""
    if not text:
        return False

    is_browser = _is_web_browser_frontmost()

    # 1. For native macOS apps (Apple Notes, TextEdit, Mail, Xcode, Pages, etc.),
    # direct AXUIElement set is instant, synchronous, and immune to modifier key state/focus issues.
    if not is_browser and HAS_AX and focused_elem is not None:
        try:
            err_set, settable = AXUIElementIsAttributeSettable(focused_elem, kAXSelectedTextAttribute, None)
            if not err_set and settable:
                err = AXUIElementSetAttributeValue(focused_elem, kAXSelectedTextAttribute, text)
                if not err:
                    copy_to_clipboard(text)
                    return True
        except Exception:
            pass

    # 2. For Web Browsers (Safari, Chrome, Arc, etc.) and fallback:
    # WebKit/Blink web content processes do not apply AX text mutations to web DOM (e.g. Gmail compose),
    # so simulating Cmd+V paste is required to trigger the web framework's paste handlers.
    paste_text(text)
    return True




def copy_to_clipboard(text: str):
    """Copy text to clipboard without pasting."""
    if not text:
        return
    if HAS_APPKIT:
        pb = AppKit.NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
    elif pyperclip:
        pyperclip.copy(text)
    else:
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))


def paste_text(text: str):
    """Copies text to clipboard and simulates Cmd+V into the active window."""
    if not text:
        return

    # Copy to clipboard
    copy_to_clipboard(text)

    if PASTE_AUTOMATICALLY:
        # Brief pause to ensure physical modifier keys settle
        time.sleep(0.06)
        _simulate_cmd_key("v")



