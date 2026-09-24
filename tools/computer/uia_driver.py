"""
Point Break Windows UI Automation (UIA) Fast-Path Driver
=========================================================
Traverses Windows native UI accessibility tree for sub-50ms native control interactions.
"""

from typing import Dict, Any, Optional
import pyautogui

try:
    import uiautomation as auto
except ImportError:
    auto = None

from tools.registry import register_tool

def uia_click_control(control_name: str, max_depth: int = 3) -> Dict[str, Any]:
    """Finds and clicks a native Windows control by name."""
    if not auto:
        return {"success": False, "error": "uiautomation package not installed"}

    target_lower = control_name.lower().strip()
    fg = auto.GetForegroundControl() or auto.GetRootControl()

    def _search(ctrl, depth=0):
        if depth > max_depth or not ctrl: return None
        try:
            name = (ctrl.Name or "").lower()
            if target_lower in name:
                rect = ctrl.BoundingRectangle
                if rect and (rect.right > rect.left) and (rect.bottom > rect.top):
                    cx = (rect.left + rect.right) // 2
                    cy = (rect.top + rect.bottom) // 2
                    return [cx, cy]
        except Exception:
            pass

        try:
            for child in ctrl.GetChildren():
                res = _search(child, depth + 1)
                if res: return res
        except Exception:
            pass
        return None

    coords = _search(fg, 0)
    if coords:
        pyautogui.click(coords[0], coords[1])
        return {"success": True, "clicked_at": coords}

    return {"success": False, "error": f"Control '{control_name}' not found in UIA tree"}

@register_tool(name="uia_click", description="Clicks Windows native control using UIA fast-path", risk_level="R1")
def tool_uia_click(control_name: str = "", **kwargs) -> Dict[str, Any]:
    return uia_click_control(control_name)
