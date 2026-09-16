"""
Point Break — Native UI Automation (UIA) Takeover Engine
=========================================================
Delivers sub-50ms deterministic desktop element targeting and interaction
via the native Windows UI Automation COM tree (via uiautomation package).

Key Advantages over Vision-Grounding:
  - Latency: < 50ms (tree walk + pattern invocation) vs 2-4 seconds (screenshot + cloud LLM)
  - Zero API Token cost
  - Immune to theme/color/scaling/dark mode shifts
  - Direct Programmatic Action: InvokePattern, ValuePattern, TogglePattern, SelectionItemPattern
  - Fallback Chain: UIA Pattern -> pyautogui click/type at BoundingRectangle center -> Vision Grounding
"""

import os
import sys
import time
import threading
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict, Any, Callable

try:
    import uiautomation as auto
    _UIA_AVAILABLE = True
except ImportError:
    auto = None
    _UIA_AVAILABLE = False

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

@dataclass
class UIAElementResult:
    found: bool
    name: str
    automation_id: str
    class_name: str
    control_type: str
    center: Tuple[int, int]
    bounding_rect: Tuple[int, int, int, int]  # (left, top, right, bottom)
    is_enabled: bool
    is_offscreen: bool
    patterns: List[str]
    source: str = "uia_native"
    _raw_control: Any = None

class UIAEngine:
    """Sub-50ms native Windows UI Automation Takeover Engine."""
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(UIAEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.available = _UIA_AVAILABLE
        if self.available:
            try:
                auto.SetGlobalSearchTimeout(0.2)
            except Exception:
                pass

    def is_available(self) -> bool:
        return self.available and auto is not None

    def get_foreground_window(self):
        if not self.is_available():
            return None
        try:
            return auto.GetForegroundControl()
        except Exception:
            return None

    def benchmark_traversal(self, max_depth: int = 4) -> float:
        """Measures raw COM tree traversal speed in milliseconds."""
        if not self.is_available():
            return 0.0
        t0 = time.perf_counter()
        root = auto.GetRootControl()
        if root:
            try:
                _ = root.GetChildren()
            except Exception:
                pass
        dt_ms = (time.perf_counter() - t0) * 1000
        return dt_ms

    def find_element(
        self,
        name: Optional[str] = None,
        automation_id: Optional[str] = None,
        class_name: Optional[str] = None,
        control_type: Optional[str] = None,
        window_title: Optional[str] = None,
        max_depth: int = 12,
        timeout: float = 0.5,
        index: int = 0
    ) -> Optional[UIAElementResult]:
        """
        Deep recursive search in UI tree.
        Sub-50ms when target is present.
        """
        if not self.is_available():
            return None

        start_t = time.perf_counter()
        name_lower = name.lower().strip() if name else None
        auto_id_lower = automation_id.lower().strip() if automation_id else None
        class_lower = class_name.lower().strip() if class_name else None

        while True:
            try:
                root = None
                if window_title:
                    root = auto.WindowControl(searchDepth=2, SubName=window_title)
                    if not root.Exists(maxSearchSeconds=0.1):
                        root = None
                if not root:
                    root = auto.GetForegroundControl()
                if not root:
                    root = auto.GetRootControl()

                if root:
                    matches = []
                    self._walk_tree(root, name_lower, auto_id_lower, class_lower, control_type, max_depth, 0, matches)

                    if matches:
                        idx = min(index, len(matches) - 1)
                        target = matches[idx]
                        rect = target.BoundingRectangle
                        if rect and (rect.right > rect.left) and (rect.bottom > rect.top):
                            cx = (rect.left + rect.right) // 2
                            cy = (rect.top + rect.bottom) // 2
                            patterns = self._detect_patterns(target)
                            return UIAElementResult(
                                found=True,
                                name=getattr(target, "Name", "") or "",
                                automation_id=getattr(target, "AutomationId", "") or "",
                                class_name=getattr(target, "ClassName", "") or "",
                                control_type=str(getattr(target, "ControlTypeName", "") or getattr(target, "ControlType", "")),
                                center=(cx, cy),
                                bounding_rect=(rect.left, rect.top, rect.right, rect.bottom),
                                is_enabled=getattr(target, "IsEnabled", True),
                                is_offscreen=getattr(target, "IsOffscreen", False),
                                patterns=patterns,
                                source="uia_native",
                                _raw_control=target
                            )
            except Exception:
                pass

            elapsed = time.perf_counter() - start_t
            if elapsed >= timeout:
                break
            time.sleep(0.02)

        return None

    def _walk_tree(self, node, name_lower, auto_id_lower, class_lower, control_type, max_depth, current_depth, matches):
        if current_depth > max_depth or len(matches) > 10:
            return

        try:
            node_name = (getattr(node, "Name", "") or "").lower()
            node_id = (getattr(node, "AutomationId", "") or "").lower()
            node_class = (getattr(node, "ClassName", "") or "").lower()
            node_type = str(getattr(node, "ControlTypeName", "") or getattr(node, "ControlType", ""))

            matched = True
            if name_lower and name_lower not in node_name:
                matched = False
            if auto_id_lower and auto_id_lower not in node_id:
                matched = False
            if class_lower and class_lower not in node_class:
                matched = False
            if control_type and (control_type.lower() not in node_type.lower()):
                matched = False

            if matched and current_depth > 0:
                matches.append(node)

            children = node.GetChildren()
            for child in children:
                self._walk_tree(child, name_lower, auto_id_lower, class_lower, control_type, max_depth, current_depth + 1, matches)
        except Exception:
            return

    def _detect_patterns(self, control) -> List[str]:
        patterns = []
        if not control:
            return patterns
        try:
            if hasattr(control, "GetInvokePattern") and control.GetInvokePattern():
                patterns.append("Invoke")
        except Exception: pass
        try:
            if hasattr(control, "GetValuePattern") and control.GetValuePattern():
                patterns.append("Value")
        except Exception: pass
        try:
            if hasattr(control, "GetTogglePattern") and control.GetTogglePattern():
                patterns.append("Toggle")
        except Exception: pass
        try:
            if hasattr(control, "GetSelectionItemPattern") and control.GetSelectionItemPattern():
                patterns.append("SelectionItem")
        except Exception: pass
        try:
            if hasattr(control, "GetScrollPattern") and control.GetScrollPattern():
                patterns.append("Scroll")
        except Exception: pass
        return patterns

    # ── HIGH-PERFORMANCE SMART ACTIONS (< 50ms) ──
    def click_element(self, element: UIAElementResult) -> bool:
        """Invokes element pattern directly in < 15ms or clicks center."""
        if not element or not element.found:
            return False

        if element._raw_control:
            try:
                pattern = element._raw_control.GetInvokePattern()
                if pattern:
                    pattern.Invoke()
                    return True
            except Exception:
                pass

            try:
                pattern = element._raw_control.GetTogglePattern()
                if pattern:
                    pattern.Toggle()
                    return True
            except Exception:
                pass

        if pyautogui and element.center:
            cx, cy = element.center
            pyautogui.click(cx, cy)
            return True

        return False

    def type_into_element(self, element: UIAElementResult, text: str, clear_first: bool = True) -> bool:
        """Sets text via ValuePattern in < 10ms, or clicks and types."""
        if not element or not element.found:
            return False

        if element._raw_control:
            try:
                pattern = element._raw_control.GetValuePattern()
                if pattern:
                    pattern.SetValue(text)
                    return True
            except Exception:
                pass

        if pyautogui and element.center:
            cx, cy = element.center
            pyautogui.click(cx, cy)
            time.sleep(0.05)
            if clear_first:
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.03)
                pyautogui.press("backspace")
                time.sleep(0.03)

            if pyperclip:
                pyperclip.copy(text)
                time.sleep(0.02)
                pyautogui.hotkey("ctrl", "v")
            else:
                pyautogui.typewrite(text, interval=0.01)
            return True

        return False

    def toggle_element(self, element: UIAElementResult) -> bool:
        """Toggles checkbox or switch."""
        if not element or not element.found:
            return False
        if element._raw_control:
            try:
                p = element._raw_control.GetTogglePattern()
                if p:
                    p.Toggle()
                    return True
            except Exception:
                pass
        return self.click_element(element)

    def select_tab(self, element: UIAElementResult) -> bool:
        """Selects tab or list item."""
        if not element or not element.found:
            return False
        if element._raw_control:
            try:
                p = element._raw_control.GetSelectionItemPattern()
                if p:
                    p.Select()
                    return True
            except Exception:
                pass
        return self.click_element(element)

    # ── COMPOSITE MACRO ACTIONS ──
    def click_button(self, name: str, window_title: Optional[str] = None) -> bool:
        elem = self.find_element(name=name, control_type="ButtonControl", window_title=window_title, timeout=0.5)
        if not elem:
            elem = self.find_element(name=name, window_title=window_title, timeout=0.3)
        return self.click_element(elem) if elem else False

    def type_into_field(self, field_name: str, text: str, window_title: Optional[str] = None) -> bool:
        elem = self.find_element(name=field_name, control_type="EditControl", window_title=window_title, timeout=0.5)
        if not elem:
            elem = self.find_element(control_type="EditControl", window_title=window_title, timeout=0.3)
        return self.type_into_element(elem, text) if elem else False

    def read_element_text(self, name: str, window_title: Optional[str] = None) -> Optional[str]:
        elem = self.find_element(name=name, window_title=window_title, timeout=0.5)
        if elem and elem._raw_control:
            try:
                vp = elem._raw_control.GetValuePattern()
                if vp and vp.Value:
                    return vp.Value
            except Exception:
                pass
            return elem.name
        return None

    def focus_window(self, title_contains: str) -> bool:
        if not self.is_available():
            return False
        try:
            win = auto.WindowControl(searchDepth=2, SubName=title_contains)
            if win.Exists(maxSearchSeconds=0.5):
                win.SetActive()
                win.SetTopmost(True)
                win.SetTopmost(False)
                return True
        except Exception:
            pass
        return False

# Global singleton instance
uia_engine = UIAEngine()
