"""macOS Menu Bar (Status Item) interface with recent history and app controls."""

from collections.abc import Callable

from .clipboard import copy_to_clipboard
from .config import ENABLE_MENUBAR, LOG_FILE
from .history import HistoryManager
from .logger import clear_log_file, get_logger, open_log_file
from .sound import play_sound

logger = get_logger("MenuBar")

try:
    import AppKit
    import Cocoa
    import objc
    from PyObjCTools import AppHelper

    HAS_PYOBJC = True
except ImportError:
    HAS_PYOBJC = False


if HAS_PYOBJC:

    class _MenuBarDelegate(Cocoa.NSObject):
        def init(self):
            self = objc.super(_MenuBarDelegate, self).init()
            self._menubar_ref = None
            return self

        def setMenuBarRef_(self, ref):
            self._menubar_ref = ref

        def copyHistoryItem_(self, sender):
            if self._menubar_ref:
                text = sender.representedObject()
                self._menubar_ref.on_copy_text(text)

        def clearHistory_(self, sender):
            if self._menubar_ref:
                self._menubar_ref.on_clear_history()

        def openLogs_(self, sender):
            if self._menubar_ref:
                self._menubar_ref.on_open_logs()

        def clearLogs_(self, sender):
            if self._menubar_ref:
                self._menubar_ref.on_clear_logs()

        def restartApp_(self, sender):
            if self._menubar_ref:
                self._menubar_ref.on_restart()

        def quitApp_(self, sender):
            if self._menubar_ref:
                self._menubar_ref.on_quit()


def _make_sf_symbol(name: str):
    """Load a native Apple SF Symbol template image for NSMenuItem."""
    if not HAS_PYOBJC:
        return None
    try:
        img = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
        if img:
            img.setTemplate_(True)
        return img
    except Exception:
        return None


class DictationMenuBar:
    """Native macOS top panel / menu bar status item for Gemini Dictation."""

    def __init__(
        self,
        history: HistoryManager,
        hud=None,
        get_active_device: Callable[[], str] | None = None,
        on_quit_callback: Callable[[], None] | None = None,
        enabled: bool = True,
    ):
        self.history = history
        self.hud = hud
        self.get_active_device = get_active_device
        self.on_quit_callback = on_quit_callback
        self.enabled = enabled and HAS_PYOBJC and ENABLE_MENUBAR

        self.status_item = None
        self.menu = None
        self.delegate = None
        self._items_cache = []

        if self.enabled:
            self._init_status_item()

    def _init_status_item(self):
        try:
            app = AppKit.NSApplication.sharedApplication()
            app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

            self.delegate = _MenuBarDelegate.alloc().init()
            self.delegate.setMenuBarRef_(self)

            status_bar = AppKit.NSStatusBar.systemStatusBar()
            self.status_item = status_bar.statusItemWithLength_(AppKit.NSSquareStatusItemLength)

            button = self.status_item.button()
            if button:
                # Try SF Symbols first
                img = (
                    _make_sf_symbol("waveform.and.mic")
                    or _make_sf_symbol("mic.fill")
                    or _make_sf_symbol("mic")
                )
                if img:
                    button.setImage_(img)
                else:
                    button.setTitle_("🎙️")

                button.setToolTip_("Gemini Dictation & Text Corrector")

            self.menu = AppKit.NSMenu.alloc().init()
            self.menu.setAutoenablesItems_(False)
            self.status_item.setMenu_(self.menu)

            self._build_menu()
        except Exception as e:
            print(f"Menu bar initialization notice: {e}")
            self.enabled = False

    def update_menu(self):
        """Thread-safe request to rebuild the menu."""
        if not self.enabled or not self.menu:
            return
        AppHelper.callAfter(self._build_menu)

    def _build_menu(self):
        if not self.menu or not self.enabled:
            return

        self.menu.removeAllItems()
        self._items_cache = self.history.get_recent(5)

        # 1. Title Header
        title_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Gemini Dictation", None, ""
        )
        title_item.setImage_(_make_sf_symbol("waveform"))
        title_item.setEnabled_(False)
        self.menu.addItem_(title_item)

        # 2. Active Audio Input Device
        active_dev = self.get_active_device() if self.get_active_device else "Default"
        dev_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            f"Input: {active_dev}", None, ""
        )
        dev_item.setImage_(_make_sf_symbol("mic"))
        dev_item.setEnabled_(False)
        self.menu.addItem_(dev_item)

        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # 3. Recent History Header
        history_header = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Recent Text (Click to copy):", None, ""
        )
        history_header.setImage_(_make_sf_symbol("clock"))
        history_header.setEnabled_(False)
        self.menu.addItem_(history_header)

        # 4. History Items (up to 5)
        if not self._items_cache:
            empty_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "   (No recent transcriptions)", None, ""
            )
            empty_item.setImage_(_make_sf_symbol("doc.text"))
            empty_item.setEnabled_(False)
            self.menu.addItem_(empty_item)
        else:
            for item in self._items_cache:
                raw_text = item.get("text", "")
                kind = item.get("kind", "dictation")
                symbol_name = "quote.bubble" if kind == "dictation" else "sparkles"

                # Format single-line preview
                clean_line = " ".join(raw_text.split())
                preview = f"{clean_line[:38]}…" if len(clean_line) > 38 else clean_line

                menu_title = f'"{preview}"'
                menu_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    menu_title, "copyHistoryItem:", ""
                )
                menu_item.setImage_(_make_sf_symbol(symbol_name))
                menu_item.setTarget_(self.delegate)
                menu_item.setRepresentedObject_(raw_text)
                menu_item.setToolTip_(raw_text)
                menu_item.setEnabled_(True)
                self.menu.addItem_(menu_item)

        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # 5. Clear History (if items exist)
        if self._items_cache:
            clear_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "Clear History", "clearHistory:", ""
            )
            clear_item.setImage_(_make_sf_symbol("trash"))
            clear_item.setTarget_(self.delegate)
            clear_item.setEnabled_(True)
            self.menu.addItem_(clear_item)
            self.menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # 6. Shortcuts Info
        info_dictate = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Dictate: Right ⌘", None, ""
        )
        info_dictate.setImage_(_make_sf_symbol("command"))
        info_dictate.setEnabled_(False)
        self.menu.addItem_(info_dictate)

        info_correct = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Polish Text: Right ⌘ + ⌥", None, ""
        )
        info_correct.setImage_(_make_sf_symbol("option"))
        info_correct.setEnabled_(False)
        self.menu.addItem_(info_correct)

        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # 7. Logs Section
        logs_menu_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Open Logs...", "openLogs:", ""
        )
        logs_menu_item.setImage_(
            _make_sf_symbol("doc.text.magnifyingglass") or _make_sf_symbol("doc.text")
        )
        logs_menu_item.setTarget_(self.delegate)
        logs_menu_item.setEnabled_(True)
        self.menu.addItem_(logs_menu_item)

        clear_logs_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Clear Logs", "clearLogs:", ""
        )
        clear_logs_item.setImage_(_make_sf_symbol("xmark.bin") or _make_sf_symbol("trash"))
        clear_logs_item.setTarget_(self.delegate)
        clear_logs_item.setEnabled_(True)
        self.menu.addItem_(clear_logs_item)

        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())

        # 8. Restart Option
        restart_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Restart Dictation", "restartApp:", "r"
        )
        restart_item.setImage_(_make_sf_symbol("arrow.clockwise"))
        restart_item.setTarget_(self.delegate)
        restart_item.setEnabled_(True)
        self.menu.addItem_(restart_item)

        # 9. Quit Option
        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit Dictation", "quitApp:", "q"
        )
        quit_item.setImage_(_make_sf_symbol("power"))
        quit_item.setTarget_(self.delegate)
        quit_item.setEnabled_(True)
        self.menu.addItem_(quit_item)

    def on_copy_text(self, text: str):
        """Called when user clicks a recent history item."""
        if text:
            copy_to_clipboard(text)
            play_sound("Hero")
            if self.hud and getattr(self.hud, "enabled", False):
                self.hud.show_done("✨  Copied")

            clean_preview = " ".join(text.split())
            if len(clean_preview) > 40:
                clean_preview = f"{clean_preview[:40]}…"
            logger.info('Copied recent history to clipboard: "%s"', clean_preview)

    def on_copy_item(self, tag: int):
        """Backwards-compatibility copy helper by index."""
        if 0 <= tag < len(self._items_cache):
            self.on_copy_text(self._items_cache[tag].get("text", ""))

    def on_clear_history(self):
        """Called when user clicks Clear History."""
        self.history.clear()
        self._build_menu()
        play_sound("Pop")
        if self.hud and getattr(self.hud, "enabled", False):
            self.hud.show_done("🗑️  Cleared")
        logger.info("History cleared by user")

    def on_open_logs(self):
        """Called when user clicks Open Logs."""
        open_log_file(LOG_FILE)

    def on_clear_logs(self):
        """Called when user clicks Clear Logs."""
        clear_log_file(LOG_FILE)
        play_sound("Pop")
        if self.hud and getattr(self.hud, "enabled", False):
            self.hud.show_done("🗑️  Logs Cleared")
        logger.info("App logs cleared by user")

    def on_restart(self):
        """Cleanly restart the application (reloading code, config, and environment)."""
        import os

        logger.info("Restart requested by user (sending restart signal 42)...")
        play_sound("Blow")
        if self.hud and getattr(self.hud, "enabled", False):
            self.hud.show_done("🔄  Restarting...")

        # Release resources cleanly
        if self.on_quit_callback:
            try:
                self.on_quit_callback()
            except Exception:
                pass

        from .hud import stop_cocoa_event_loop

        stop_cocoa_event_loop()

        # Signal supervisor process to reboot with a fresh PID and clean Mach ports
        os._exit(42)

    def on_quit(self):
        """Called when user clicks Quit."""
        logger.info("Quit requested by user")
        if self.on_quit_callback:
            try:
                self.on_quit_callback()
            except Exception:
                pass
        from .hud import stop_cocoa_event_loop

        stop_cocoa_event_loop()
        try:
            AppHelper.stopEventLoop()
        except Exception:
            pass
        try:
            AppKit.NSApplication.sharedApplication().terminate_(None)
        except Exception:
            pass
