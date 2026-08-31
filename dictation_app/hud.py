import signal
import warnings

warnings.filterwarnings("ignore", message=".*ObjCPointer.*")

try:
    import AppKit
    from Cocoa import (
        NSPanel, NSColor, NSVisualEffectView, NSApplication,
        NSMakeRect, NSMakePoint, NSScreen, NSTextField, NSFont,
        NSFontWeightSemibold, NSValue,
        NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel,
        NSStatusWindowLevel,
        NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary,
        NSWindowCollectionBehaviorIgnoresCycle, NSVisualEffectMaterialPopover,
        NSVisualEffectBlendingModeBehindWindow, NSVisualEffectStateActive,
        NSTextAlignmentCenter, NSAnimationContext, NSAppearance,
        NSRunLoop, NSRunLoopCommonModes, NSTimer
    )
    import Quartz
    from Quartz import (
        CGPoint, CATransform3DMakeTranslation, CATransform3DMakeScale,
        CATransform3DConcat, CATransform3DIdentity,
        CABasicAnimation, CASpringAnimation, CAMediaTimingFunction,
        kCAMediaTimingFunctionEaseOut, kCAMediaTimingFunctionEaseIn,
        kCAFillModeForwards
    )
    from PyObjCTools import AppHelper
    HAS_PYOBJC = True
except ImportError:
    HAS_PYOBJC = False

from .caret import get_caret_screen_rect, get_focused_window_rect
from .config import ENABLE_HUD, HUD_FOLLOW_CARET, HUD_STYLE

# Unicode block glyphs (shortest to tallest) used to render the recording-level equalizer,
# and a per-bar sensitivity so the bars fan out unevenly instead of moving in lockstep.
_BAR_GLYPHS = "▁▂▃▄▅▆▇█"
_BAR_WEIGHTS = (0.55, 0.85, 1.0, 0.85, 0.55)
# Braille frames for the "Transcribing..." spinner animation
_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPINNER_INTERVAL = 0.08


def _make_centered_scale_transform(scale: float, width: float = 220.0, height: float = 40.0):
    """Build a CATransform3D matrix that scales strictly around the center (width/2, height/2)."""
    if not HAS_PYOBJC:
        return None
    t1 = CATransform3DMakeTranslation(-width / 2.0, -height / 2.0, 0.0)
    s = CATransform3DMakeScale(scale, scale, 1.0)
    t2 = CATransform3DMakeTranslation(width / 2.0, height / 2.0, 0.0)
    return CATransform3DConcat(CATransform3DConcat(t1, s), t2)


def get_screen_for_rect(x: float, y: float, w: float, h: float):
    """Find the NSScreen that contains the given rect or has the largest overlap."""
    if not HAS_PYOBJC:
        return None
    screens = AppKit.NSScreen.screens()
    if not screens:
        return AppKit.NSScreen.mainScreen()

    target_rect = Cocoa.NSMakeRect(x, y, w, h)
    best_screen = None
    best_area = -1.0

    for s in screens:
        intersection = Cocoa.NSIntersectionRect(target_rect, s.frame())
        area = intersection.size.width * intersection.size.height
        if area > best_area:
            best_area = area
            best_screen = s

    if best_screen and best_area > 0:
        return best_screen

    # Fallback to screen containing center point
    cx = x + w / 2.0
    cy = y + h / 2.0
    for s in screens:
        f = s.frame()
        if f.origin.x <= cx <= f.origin.x + f.size.width and f.origin.y <= cy <= f.origin.y + f.size.height:
            return s

    return AppKit.NSScreen.mainScreen() or screens[0]


def get_screen_notch_info(screen):
    """Return (notch_left, notch_right, notch_bottom) in AppKit coordinates if screen has a notch, or None."""
    if not HAS_PYOBJC or not screen or not hasattr(screen, "safeAreaInsets"):
        return None
    insets = screen.safeAreaInsets()
    if insets.top <= 0:
        return None

    frame = screen.frame()
    left_aux = getattr(screen, "auxiliaryTopLeftArea", None)
    right_aux = getattr(screen, "auxiliaryTopRightArea", None)

    if left_aux and right_aux:
        l_rect = screen.auxiliaryTopLeftArea()
        r_rect = screen.auxiliaryTopRightArea()
        if l_rect.size.width > 0 and r_rect.size.width > 0:
            notch_left = l_rect.origin.x + l_rect.size.width
            notch_right = r_rect.origin.x
            notch_bottom = frame.origin.y + frame.size.height - insets.top
            return (notch_left, notch_right, notch_bottom)

    # Heuristic fallback for screens with notch safe area
    center_x = frame.origin.x + frame.size.width / 2.0
    notch_bottom = frame.origin.y + frame.size.height - insets.top
    return (center_x - 110.0, center_x + 110.0, notch_bottom)


def calculate_intelligent_hud_position(
    panel_w: float = 220.0,
    panel_h: float = 40.0,
    caret_rect=None,
    window_rect=None,
):
    """Calculate non-occluded, notch-avoiding (x, y) coordinates for the HUD pill."""
    if not HAS_PYOBJC:
        return (100.0, 100.0)

    # 1. Determine active target screen
    target_screen = None
    if caret_rect:
        cx, cy, ch = caret_rect
        if ch > 0:
            target_screen = get_screen_for_rect(cx, cy, 10.0, ch)

    if not target_screen and window_rect:
        wx, wy, ww, wh = window_rect
        if ww > 0 and wh > 0:
            target_screen = get_screen_for_rect(wx, wy, ww, wh)

    if not target_screen:
        target_screen = AppKit.NSScreen.mainScreen() or (AppKit.NSScreen.screens()[0] if AppKit.NSScreen.screens() else None)

    if not target_screen:
        return (100.0, 100.0)

    vframe = target_screen.visibleFrame()
    vx, vy, vw, vh = vframe.origin.x, vframe.origin.y, vframe.size.width, vframe.size.height
    notch = get_screen_notch_info(target_screen)

    # Keep a comfortable margin inside the visible screen
    margin = 12.0
    min_x = vx + margin
    max_x = vx + vw - panel_w - margin
    min_y = vy + margin
    max_y = vy + vh - panel_h - margin

    # Default fallback: centered horizontally, safely below top menu bar and notch
    candidate_x = vx + (vw - panel_w) / 2.0
    candidate_y = max_y - 20.0

    if caret_rect:
        cx, cy, ch = caret_rect
        cand_x = cx - (panel_w / 2.0) + 6.0

        # Try placing above caret first
        above_y = cy + ch + 8.0
        below_y = cy - panel_h - 8.0

        # If placing above exceeds top screen safe area, flip below
        if above_y + panel_h > max_y:
            cand_y = below_y if below_y >= min_y else above_y
        else:
            cand_y = above_y

        candidate_x = cand_x
        candidate_y = cand_y
    elif window_rect:
        wx, wy, ww, wh = window_rect
        if ww > 50 and wh > 50:
            cand_x = wx + (ww - panel_w) / 2.0
            cand_y = wy + wh - panel_h - 18.0
            candidate_x = cand_x
            candidate_y = cand_y

    # Clamp within visible screen boundaries
    x = max(min_x, min(candidate_x, max_x))
    y = max(min_y, min(candidate_y, max_y))

    # Avoid notch collision if present
    if notch:
        n_left, n_right, n_bottom = notch
        notch_margin = 10.0
        overlaps_x = (x < n_right + notch_margin) and (x + panel_w > n_left - notch_margin)
        overlaps_y = (y + panel_h > n_bottom - notch_margin)

        if overlaps_x and overlaps_y:
            # Shift safely below notch
            safe_y_below = n_bottom - panel_h - notch_margin - 4.0
            if safe_y_below >= min_y:
                y = safe_y_below
            else:
                # If vertical room is tight, shift left or right of notch
                dist_left = abs(x + panel_w / 2.0 - n_left)
                dist_right = abs(x + panel_w / 2.0 - n_right)
                if dist_left <= dist_right and (n_left - panel_w - notch_margin >= min_x):
                    x = n_left - panel_w - notch_margin
                elif n_right + notch_margin <= max_x:
                    x = n_right + notch_margin
                else:
                    x = n_left - panel_w - notch_margin

    return (x, y)


if HAS_PYOBJC:
    import Cocoa

    class _PySignalWatcher(Cocoa.NSObject):
        def tick_(self, timer):
            pass

    _signal_watcher = None
    _signal_timer = None


def stop_cocoa_event_loop():
    """Signal the Cocoa event loop to stop."""
    if HAS_PYOBJC:
        try:
            app = AppKit.NSApplication.sharedApplication()
            app.stop_(None)
            dummy = AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
                AppKit.NSEventTypeApplicationDefined,
                (0, 0),
                0,
                0,
                0,
                None,
                0,
                0,
                0,
            )
            app.postEvent_atStart_(dummy, True)
        except Exception:
            pass


def run_cocoa_event_loop():
    """Run the native Cocoa NSApplication event loop (handles mouse clicks, status bar menus, HUD animations, and signals)."""
    global _signal_watcher, _signal_timer
    if not HAS_PYOBJC:
        return

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    app.finishLaunching()

    def _sig_handler(sig, frame):
        stop_cocoa_event_loop()
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass

    if _signal_watcher is None:
        _signal_watcher = _PySignalWatcher.alloc().init()
        _signal_timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.15, _signal_watcher, "tick:", None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(_signal_timer, NSRunLoopCommonModes)

    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        stop_cocoa_event_loop()


# Backwards compatibility alias
run_console_event_loop = run_cocoa_event_loop


class DictationHUD:
    """Minimal floating macOS frosted glass HUD pill (Dynamic Island / Siri style)."""
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and HAS_PYOBJC and ENABLE_HUD
        self.panel = None
        self.effect_view = None
        self.label = None
        self._is_visible = False
        self._spinner_active = False
        self._spinner_index = 0
        if self.enabled:
            self._init_ui()

    def _init_ui(self):
        try:
            app = NSApplication.sharedApplication()
            app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

            w, h = 220, 40
            x, y = calculate_intelligent_hud_position(w, h)
            self._panel_size = (w, h)
            self._default_origin = (x, y)

            self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(x, y, w, h),
                NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
                AppKit.NSBackingStoreBuffered,
                False
            )
            self.panel.setLevel_(NSStatusWindowLevel)
            self.panel.setCollectionBehavior_(
                NSWindowCollectionBehaviorCanJoinAllSpaces |
                NSWindowCollectionBehaviorStationary |
                NSWindowCollectionBehaviorIgnoresCycle
            )
            self.panel.setOpaque_(False)
            self.panel.setBackgroundColor_(NSColor.clearColor())
            self.panel.setIgnoresMouseEvents_(True)
            self.panel.setHasShadow_(True)
            self.panel.setAlphaValue_(0.0)

            # Use Apple's native Liquid Glass component (macOS 26+ NSGlassEffectView) or classic NSVisualEffectView
            if hasattr(AppKit, "NSGlassEffectView"):
                glass_style = AppKit.NSGlassEffectViewStyleClear if HUD_STYLE == "clear" else AppKit.NSGlassEffectViewStyleRegular
                effect_view = AppKit.NSGlassEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
                effect_view.setStyle_(glass_style)
                effect_view.setCornerRadius_(h / 2.0)
                effect_view.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
                effect_view.setWantsLayer_(True)
            else:
                effect_view = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
                effect_view.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
                effect_view.setMaterial_(NSVisualEffectMaterialPopover)
                effect_view.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
                effect_view.setState_(NSVisualEffectStateActive)
                effect_view.setWantsLayer_(True)
                effect_view.layer().setCornerRadius_(h / 2.0)
                effect_view.layer().setMasksToBounds_(True)

            self.effect_view = effect_view
            layer = effect_view.layer()
            if layer:
                layer.setTransform_(_make_centered_scale_transform(0.85, w, h))

            self.label = NSTextField.alloc().initWithFrame_(NSMakeRect(10, 10, w - 20, 20))
            self.label.setStringValue_("🔴  Listening...")
            self.label.setBezeled_(False)
            self.label.setDrawsBackground_(False)
            self.label.setEditable_(False)
            self.label.setSelectable_(False)
            self.label.setAlignment_(NSTextAlignmentCenter)
            self.label.setFont_(NSFont.systemFontOfSize_weight_(13.5, NSFontWeightSemibold))
            self.label.setTextColor_(NSColor.whiteColor())

            effect_view.addSubview_(self.label)
            self.panel.setContentView_(effect_view)
            self.panel.orderFrontRegardless()
        except Exception as e:
            print(f"HUD initialization notice: {e}")
            self.enabled = False

    def _animate_in(self, duration: float = 0.22):
        if not self.panel:
            return
        self.panel.orderFrontRegardless()

        # Fade in window
        NSAnimationContext.beginGrouping()
        context = NSAnimationContext.currentContext()
        context.setDuration_(duration)
        if HAS_PYOBJC:
            context.setTimingFunction_(CAMediaTimingFunction.functionWithName_(kCAMediaTimingFunctionEaseOut))
        self.panel.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()

        # Zoom in effect_view layer from center (0.85 -> 1.0) with subtle spring/ease-out
        if self.effect_view:
            layer = self.effect_view.layer()
            if layer:
                w, h = self._panel_size
                from_transform = _make_centered_scale_transform(0.85, w, h)
                from_val = NSValue.valueWithCATransform3D_(from_transform)
                to_val = NSValue.valueWithCATransform3D_(CATransform3DIdentity)
                try:
                    spring = CASpringAnimation.animationWithKeyPath_("transform")
                    spring.setDamping_(16.0)
                    spring.setMass_(0.6)
                    spring.setStiffness_(240.0)
                    spring.setFromValue_(from_val)
                    spring.setToValue_(to_val)
                    spring.setDuration_(0.26)
                    spring.setFillMode_(kCAFillModeForwards)
                    layer.addAnimation_forKey_(spring, "zoom")
                except Exception:
                    anim = CABasicAnimation.animationWithKeyPath_("transform")
                    anim.setFromValue_(from_val)
                    anim.setToValue_(to_val)
                    anim.setDuration_(duration)
                    anim.setTimingFunction_(CAMediaTimingFunction.functionWithName_(kCAMediaTimingFunctionEaseOut))
                    anim.setFillMode_(kCAFillModeForwards)
                    layer.addAnimation_forKey_(anim, "zoom")
                layer.setTransform_(CATransform3DIdentity)
        self._is_visible = True

    def _animate_out(self, duration: float = 0.18):
        if not self.panel:
            return

        # Fade out window
        NSAnimationContext.beginGrouping()
        context = NSAnimationContext.currentContext()
        context.setDuration_(duration)
        if HAS_PYOBJC:
            context.setTimingFunction_(CAMediaTimingFunction.functionWithName_(kCAMediaTimingFunctionEaseIn))
        self.panel.animator().setAlphaValue_(0.0)
        NSAnimationContext.endGrouping()

        # Zoom out effect_view layer to center (1.0 -> 0.85)
        if self.effect_view:
            layer = self.effect_view.layer()
            if layer:
                w, h = self._panel_size
                to_transform = _make_centered_scale_transform(0.85, w, h)
                from_val = NSValue.valueWithCATransform3D_(CATransform3DIdentity)
                to_val = NSValue.valueWithCATransform3D_(to_transform)
                anim = CABasicAnimation.animationWithKeyPath_("transform")
                anim.setFromValue_(from_val)
                anim.setToValue_(to_val)
                anim.setDuration_(duration)
                anim.setTimingFunction_(CAMediaTimingFunction.functionWithName_(kCAMediaTimingFunctionEaseIn))
                anim.setFillMode_(kCAFillModeForwards)
                layer.addAnimation_forKey_(anim, "zoom")
                layer.setTransform_(to_transform)
        self._is_visible = False



    def _update_ui(self, text: str, visible: bool, duration: float = 0.2):
        if not self.panel or not self.label:
            return
        if visible:
            if text:
                self.label.setStringValue_(text)
            if not self._is_visible:
                self._animate_in(duration=duration)
            else:
                self.panel.orderFrontRegardless()
                if self.panel.alphaValue() < 0.99:
                    self.panel.setAlphaValue_(1.0)
        else:
            if self._is_visible:
                self._animate_out(duration=duration)


    def show_recording(self):
        if not self.enabled:
            return
        self._spinner_active = False
        self._reposition_for_recording()
        AppHelper.callAfter(self._update_ui, "🔴  Listening...", True)

    def _reposition_for_recording(self):
        """Intelligently reposition HUD near text caret or window, avoiding the notch and screen edges."""
        if not self.panel:
            return
        w, h = self._panel_size

        caret = get_caret_screen_rect() if HUD_FOLLOW_CARET else None
        window = get_focused_window_rect() if (HUD_FOLLOW_CARET and caret is None) else None

        x, y = calculate_intelligent_hud_position(w, h, caret_rect=caret, window_rect=window)
        AppHelper.callAfter(self._move_to, x, y)

    def _move_to(self, x, y):
        if self.panel:
            self.panel.setFrameOrigin_(NSMakePoint(x, y))

    def update_level(self, level: float):
        """Redraw the HUD as a small equalizer reacting to the live mic level (0.0-1.0)."""
        if not self.enabled:
            return
        level = max(0.0, min(1.0, level))
        bars = "".join(
            _BAR_GLYPHS[int(min(1.0, level * weight) * (len(_BAR_GLYPHS) - 1))]
            for weight in _BAR_WEIGHTS
        )
        AppHelper.callAfter(self._update_ui, f"🔴  {bars}", True, 0.05)

    def show_transcribing(self):
        if not self.enabled:
            return
        self._spinner_active = True
        self._spinner_index = 0
        self._spinner_message = "Transcribing..."
        AppHelper.callAfter(self._spin_step)

    def show_correcting(self):
        if not self.enabled:
            return
        self._spinner_active = True
        self._spinner_index = 0
        self._spinner_message = "Correcting..."
        self._reposition_for_recording()
        AppHelper.callAfter(self._spin_step)

    def _spin_step(self):
        if not self._spinner_active:
            return
        frame = _SPINNER_FRAMES[self._spinner_index % len(_SPINNER_FRAMES)]
        self._spinner_index += 1
        msg = getattr(self, "_spinner_message", "Transcribing...")
        self._update_ui(f"{frame}  {msg}", True, 0.05)
        AppHelper.callLater(_SPINNER_INTERVAL, self._spin_step)

    def show_done(self, message: str = "✨  Done"):
        if not self.enabled:
            return
        self._spinner_active = False
        AppHelper.callAfter(self._update_ui, message, True)
        AppHelper.callLater(0.8, self._update_ui, "", False)

    def show_cancelled(self, message: str = "⚠️  Cancelled"):
        if not self.enabled:
            return
        self._spinner_active = False
        AppHelper.callAfter(self._update_ui, message, True)
        AppHelper.callLater(0.8, self._update_ui, "", False)

    def hide(self):
        if not self.enabled:
            return
        self._spinner_active = False
        AppHelper.callAfter(self._update_ui, "", False)
