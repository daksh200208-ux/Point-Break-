"""
Point Break High-Speed Visual Grounding Engine
==============================================
Captures downscaled 720p screenshots and utilizes Gemini Vision to ground
UI coordinates for natural language queries (e.g. "red checkout button").
"""

import os
import re
import json
import tempfile
import time
from typing import Dict, Any, Optional, Tuple
from PIL import Image
import pyautogui

from tools.registry import register_tool

try:
    import google.generativeai as genai
except ImportError:
    genai = None

GROUNDING_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-2.0-flash"
]

def capture_screen(save_path: Optional[str] = None) -> Tuple[Optional[Image.Image], str]:
    """Captures desktop screen and saves an optimized JPEG for vision reasoning."""
    if not save_path:
        tmp_fd, save_path = tempfile.mkstemp(suffix=".jpg", prefix="pb_vision_")
        os.close(tmp_fd)

    img = pyautogui.screenshot()
    img.thumbnail((1280, 720), Image.Resampling.LANCZOS)
    img.save(save_path, "JPEG", quality=75)
    return img, save_path

def visual_ground_and_click(target_description: str) -> Dict[str, Any]:
    """Locates an element visually and performs physical click."""
    _, path = capture_screen()
    try:
        if not genai:
            return {"success": False, "error": "Gemini not available."}

        prompt = f"""Locate UI element on this screen: "{target_description}".
Output JSON only:
{{
  "found": true or false,
  "pct_x": 0.0 to 1.0,
  "pct_y": 0.0 to 1.0
}}"""
        for m in GROUNDING_MODELS:
            try:
                model = genai.GenerativeModel(m)
                img = Image.open(path)
                resp = model.generate_content([prompt, img], request_options={"timeout": 10.0})
                match = re.search(r'\{.*\}', resp.text.strip(), re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    if data.get("found"):
                        sw, sh = pyautogui.size()
                        cx = int(data["pct_x"] * sw)
                        cy = int(data["pct_y"] * sh)
                        pyautogui.click(cx, cy)
                        return {"success": True, "clicked_at": [cx, cy]}
            except Exception as e:
                print(f"[VisualGrounding] Model {m} error: {e}")
                continue

        return {"success": False, "error": f"Element '{target_description}' not found on screen."}
    finally:
        if os.path.exists(path):
            try: os.remove(path)
            except: pass

@register_tool(name="click", description="Clicks on UI target by visual name or description", risk_level="R1")
def tool_click(target: str = "", **kwargs) -> Dict[str, Any]:
    return visual_ground_and_click(target)

@register_tool(name="open_url", description="Opens URL in browser", risk_level="R0")
def tool_open_url(url: str = "", **kwargs) -> Dict[str, Any]:
    import webbrowser
    webbrowser.open(url)
    return {"success": True, "url": url}

@register_tool(name="type_text", description="Types text into focused UI", risk_level="R1")
def tool_type_text(text: str = "", **kwargs) -> Dict[str, Any]:
    try:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    except Exception:
        pyautogui.write(text, interval=0.01)
    return {"success": True, "text": text}

@register_tool(name="hotkey", description="Sends keyboard shortcut combination", risk_level="R1")
def tool_hotkey(keys: Optional[list] = None, **kwargs) -> Dict[str, Any]:
    if keys:
        pyautogui.hotkey(*keys)
    return {"success": True, "keys": keys}

@register_tool(name="wait", description="Pauses for specified seconds", risk_level="R0")
def tool_wait(seconds: float = 1.0, **kwargs) -> Dict[str, Any]:
    time.sleep(float(seconds))
    return {"success": True, "seconds": seconds}
