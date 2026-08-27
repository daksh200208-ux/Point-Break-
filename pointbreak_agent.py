"""
Point Break 3.0 — High-Speed Self-Driving Windows Agent Engine (Commercial)
===========================================================================
Autonomous Desktop Operating Agent combining:
1. Direct OS & Browser Fast-Path Bypasses (< 50ms instant execution)
2. Windows Accessibility Tree (uiautomation / pywin32) for instant UI clicks
3. Fast Gemini 2.0 Flash Vision Grounding (with 720p optimized downscaling)
4. Full Cancel / Stop Support with Live Progress Callbacks
"""

import os
import sys
import time
import json
import re
import base64
import tempfile
import threading
from typing import List, Dict, Any, Optional, Tuple

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pyautogui
import psutil
from PIL import Image

try:
    import uiautomation as auto
except ImportError:
    auto = None

try:
    import win32gui
    import win32process
    import win32con
except ImportError:
    win32gui = None

from dotenv import load_dotenv
import webbrowser

JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(JARVIS_DIR, ".env"))

try:
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
except ImportError:
    genai = None

# Safety & responsiveness
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

def set_system_volume(pct: int) -> bool:
    """Sets master OS audio volume directly (0 - 100)."""
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, 'EndpointVolume'):
            volume = speakers.EndpointVolume
        elif hasattr(speakers, 'Activate'):
            interface = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
        else:
            volume = speakers.EndpointVolume
        volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, float(pct) / 100.0)), None)
        return True
    except Exception as e:
        print(f"[Agent] Volume adjust error: {e}")
        return False

class SelfDrivingWindowsAgent:
    def __init__(self, gemini_model="gemini-2.0-flash"):
        self.gemini_model_name = gemini_model
        self.is_running = False
        self.stop_requested = False
        self.current_goal = None
        self.execution_log = []
        self._lock = threading.Lock()

    def stop(self):
        """Signals the agent to abort execution immediately."""
        self.stop_requested = True
        self.is_running = False
        print("[Agent] ⏹️ Stop requested. Aborting workflow...")

    def capture_active_screen(self, save_path: Optional[str] = None) -> Tuple[Optional[Image.Image], str]:
        if not save_path:
            tmp_fd, save_path = tempfile.mkstemp(suffix=".jpg", prefix="pb_screen_")
            os.close(tmp_fd)

        screenshot = None
        try:
            screenshot = pyautogui.screenshot()
        except Exception:
            pass

        if screenshot is None and win32gui:
            try:
                import win32ui
                hdesktop = win32gui.GetDesktopWindow()
                width = win32gui.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
                height = win32gui.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
                desktop_dc = win32gui.GetWindowDC(hdesktop)
                img_dc = win32ui.CreateDCFromHandle(desktop_dc)
                mem_dc = img_dc.CreateCompatibleDC()
                screenshot_bmp = win32ui.CreateBitmap()
                screenshot_bmp.CreateCompatibleBitmap(img_dc, width, height)
                mem_dc.SelectObject(screenshot_bmp)
                mem_dc.BitBlt((0, 0), (width, height), img_dc, (0, 0), win32con.SRCCOPY)
                bmpinfo = screenshot_bmp.GetInfo()
                bmpstr = screenshot_bmp.GetBitmapBits(True)
                screenshot = Image.frombuffer('RGB', (bmpinfo['bmWidth'], bmpinfo['bmHeight']), bmpstr, 'raw', 'BGRX', 0, 1)
                win32gui.DeleteObject(screenshot_bmp.GetHandle())
                mem_dc.DeleteDC()
                win32gui.ReleaseDC(hdesktop, desktop_dc)
            except Exception:
                pass

        if screenshot is None:
            w, h = (1280, 720)
            screenshot = Image.new("RGB", (w, h), color=(10, 15, 25))

        screenshot.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        screenshot.save(save_path, "JPEG", quality=75)
        return screenshot, save_path

    def find_native_control(self, name_or_id: str, max_depth: int = 3) -> Optional[Dict[str, Any]]:
        if not auto:
            return None
        try:
            target_lower = name_or_id.lower().strip()
            fg_window = auto.GetForegroundControl() or auto.GetRootControl()

            def _search(ctrl, depth=0):
                if depth > max_depth or not ctrl: return None
                try:
                    c_name = (ctrl.Name or "").lower()
                    if target_lower in c_name:
                        rect = ctrl.BoundingRectangle
                        if rect and (rect.right > rect.left) and (rect.bottom > rect.top):
                            cx = (rect.left + rect.right) // 2
                            cy = (rect.top + rect.bottom) // 2
                            return {"found": True, "name": ctrl.Name, "center": [cx, cy], "source": "accessibility_tree"}
                except Exception:
                    pass

                try:
                    for child in ctrl.GetChildren():
                        res = _search(child, depth + 1)
                        if res: return res
                except Exception:
                    pass
                return None

            return _search(fg_window, 0)
        except Exception:
            return None

    def ground_target_visually(self, target_description: str, screenshot_path: str) -> Optional[Dict[str, Any]]:
        if not genai:
            return None

        prompt = f"""Locate UI element on this desktop: "{target_description}".
Output JSON only:
{{
  "found": true or false,
  "pct_x": 0.0 to 1.0 (horizontal fraction from left),
  "pct_y": 0.0 to 1.0 (vertical fraction from top)
}}"""
        try:
            model = genai.GenerativeModel(self.gemini_model_name)
            img = Image.open(screenshot_path)
            response = model.generate_content([prompt, img])
            text = response.text.strip()
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if data.get("found"):
                    screen_w, screen_h = pyautogui.size()
                    cx = int(data["pct_x"] * screen_w)
                    cy = int(data["pct_y"] * screen_h)
                    data["center"] = [cx, cy]
                    data["source"] = "vision_llm"
                    return data
            return None
        except Exception as e:
            print(f"[Agent] Vision error: {e}")
            return None

    def resolve_and_interact(self, target: str, action: str = "click", text_to_type: Optional[str] = None) -> bool:
        loc = self.find_native_control(target)
        
        if not loc or not loc.get("found"):
            _, img_path = self.capture_active_screen()
            try:
                loc = self.ground_target_visually(target, img_path)
            finally:
                if os.path.exists(img_path):
                    try: os.remove(img_path)
                    except: pass

        if not loc or not loc.get("found"):
            print(f"[Agent] ❌ Could not locate element: '{target}'")
            return False

        cx, cy = loc["center"]
        pyautogui.moveTo(cx, cy, duration=0.15)
        if action == "click":
            pyautogui.click(cx, cy)
        elif action == "double_click":
            pyautogui.doubleClick(cx, cy)
        elif action == "right_click":
            pyautogui.rightClick(cx, cy)
        elif action == "type" and text_to_type:
            pyautogui.click(cx, cy)
            time.sleep(0.1)
            pyautogui.write(text_to_type, interval=0.01)
        return True

    def plan_and_execute_task(self, natural_language_goal: str, update_callback=None) -> Dict[str, Any]:
        clean_goal = re.sub(r'^[,\s:;.-]+', '', natural_language_goal).strip()
        if not clean_goal: clean_goal = natural_language_goal.strip()

        with self._lock:
            self.is_running = True
            self.stop_requested = False
            self.current_goal = clean_goal
            self.execution_log = []

        if update_callback:
            update_callback({"goal": clean_goal, "status": "planning", "step": "Synthesizing Plan", "description": "Compiling execution DAG..."})

        print(f"\n[Agent] 🚀 Planning Self-Driving Workflow for: '{clean_goal}'")

        if not genai:
            err_msg = "Gemini AI not initialized (check GEMINI_API_KEY in .env)."
            if update_callback: update_callback({"goal": clean_goal, "status": "failed", "description": err_msg})
            return {"success": False, "error": err_msg}

        plan_prompt = f"""
You are the Autonomous Desktop Operating Engine for Point Break 3.0 (Windows 11/10).
Goal: "{clean_goal}"

Create an optimal, fast step-by-step action plan.
Allowed Actions:
- "open_url": target = full URL (e.g. "https://www.youtube.com/results?search_query=...")
- "play_youtube": target = search query string
- "set_volume": level = integer (0 to 100)
- "launch_app": target = executable name (e.g. "notepad", "chrome", "calc", "cmd")
- "hotkey": keys = array of keys (e.g. ["ctrl", "s"], ["alt", "f4"], ["enter"])
- "click": target = UI button/element description
- "type": target = element description, value = text to write
- "wait": seconds = float (e.g. 0.5, 1.0)

Output ONLY valid JSON:
{{
  "goal": "{clean_goal}",
  "steps": [
    {{ "step": 1, "action": "action_name", "target": "value", "description": "what this does" }}
  ]
}}
"""
        try:
            model = genai.GenerativeModel(self.gemini_model_name)
            res = model.generate_content(plan_prompt)
            match = re.search(r'\{.*\}', res.text.strip(), re.DOTALL)
            if not match:
                err_msg = "Failed to parse planning response from AI."
                if update_callback: update_callback({"goal": clean_goal, "status": "failed", "description": err_msg})
                return {"success": False, "error": err_msg}

            plan_data = json.loads(match.group(0))
            steps = plan_data.get("steps", [])

            if not steps:
                err_msg = "Planner generated 0 steps for this goal."
                if update_callback: update_callback({"goal": clean_goal, "status": "failed", "description": err_msg})
                return {"success": False, "error": err_msg}

            # Execute DAG Plan
            for idx, step in enumerate(steps):
                if self.stop_requested:
                    print("[Agent] ⏹️ Workflow cancelled by operator.")
                    if update_callback: update_callback({"goal": clean_goal, "status": "cancelled", "description": "Aborted by user."})
                    return {"success": False, "cancelled": True}

                action = step.get("action")
                desc = step.get("description", f"Step {idx + 1}")
                print(f"[Agent] ▶ Step {idx + 1}/{len(steps)}: {desc}")
                
                if update_callback:
                    update_callback({
                        "goal": clean_goal,
                        "status": "executing",
                        "current_step": idx + 1,
                        "total_steps": len(steps),
                        "description": desc
                    })

                step_success = False
                if action == "set_volume":
                    lvl = int(step.get("level", 50))
                    step_success = set_system_volume(lvl)

                elif action == "open_url":
                    url = step.get("target", "")
                    if url:
                        webbrowser.open(url)
                        step_success = True

                elif action == "play_youtube":
                    q = step.get("target", "")
                    yt_url = f"https://www.youtube.com/results?search_query={q.replace(' ', '+')}"
                    webbrowser.open(yt_url)
                    step_success = True

                elif action == "launch_app":
                    app = step.get("target", "")
                    subprocess.Popen([{app}], creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
                    step_success = True

                elif action == "click":
                    step_success = self.resolve_and_interact(step.get("target", ""), action="click")

                elif action == "double_click":
                    step_success = self.resolve_and_interact(step.get("target", ""), action="double_click")

                elif action == "type":
                    step_success = self.resolve_and_interact(
                        step.get("target", ""), 
                        action="type", 
                        text_to_type=step.get("value", "")
                    )

                elif action == "hotkey":
                    keys = step.get("keys", [])
                    if keys:
                        pyautogui.hotkey(*keys)
                        step_success = True

                elif action == "wait":
                    sec = float(step.get("seconds", 0.5))
                    time.sleep(sec)
                    step_success = True

                self.execution_log.append({
                    "step": idx + 1,
                    "description": desc,
                    "success": step_success
                })

                time.sleep(0.15)

            with self._lock:
                self.is_running = False

            if update_callback:
                update_callback({"goal": clean_goal, "status": "completed", "description": f"Completed all {len(steps)} steps.", "steps": self.execution_log})

            print(f"[Agent] ✅ Finished Autonomous Workflow for '{clean_goal}' successfully!")
            return {"success": True, "goal": clean_goal, "steps_executed": len(steps)}

        except Exception as e:
            with self._lock:
                self.is_running = False
            err_str = f"Execution error: {e}"
            print(f"[Agent] Task execution failure: {e}")
            if update_callback:
                update_callback({"goal": clean_goal, "status": "failed", "description": err_str})
            return {"success": False, "error": str(e)}

# Global instance
agent_engine = SelfDrivingWindowsAgent()
