from pointbreak_genai import query_generative_model, query_tars_vision
from pointbreak_uia import uia_engine
"""
Point Break 3.0 — High-Speed Self-Driving Windows Agent Engine
==============================================================
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
import subprocess
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

AGENT_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

# Safety & responsiveness
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.08

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
    def __init__(self, gemini_model="gemini-3.5-flash-lite"):
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
        """Captures screen and saves a fast 720p downscaled JPEG for low-latency visual reasoning."""
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

        # Optimize size for fast upload (< 100KB)
        screenshot.thumbnail((1280, 720), Image.Resampling.LANCZOS)
        screenshot.save(save_path, "JPEG", quality=75)
        return screenshot, save_path

    def find_native_control(self, name_or_id: str, max_depth: int = 3) -> Optional[Dict[str, Any]]:
        """Ultra-fast accessibility tree lookup with strict depth limit."""
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
        """Fast Gemini vision grounding with multi-model failover."""
        if not genai:
            return None

        prompt = f"""Locate UI element on this desktop: "{target_description}".
Output JSON only:
{{
  "found": true or false,
  "pct_x": 0.0 to 1.0 (horizontal fraction from left),
  "pct_y": 0.0 to 1.0 (vertical fraction from top)
}}"""
        for m in AGENT_MODELS:
            try:
                model = genai.GenerativeModel(m)
                img = Image.open(screenshot_path)
                response = model.generate_content([prompt, img], request_options={"timeout": 12.0})
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
            except Exception as e:
                print(f"[Agent Vision] Model {m} failed: {e}")
                continue
        return None

    def resolve_and_interact(self, target: str, action: str = "click", text_to_type: Optional[str] = None) -> bool:
        """Grounds target and executes physical click/type."""
        # 1. Instant native accessibility tree (< 40ms)
        loc = self.find_native_control(target)
        
        # 2. Vision fallback if needed
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
        pyautogui.moveTo(cx, cy, duration=0.22)
        if action == "click":
            pyautogui.click(cx, cy)
        elif action == "double_click":
            pyautogui.doubleClick(cx, cy)
        elif action == "right_click":
            pyautogui.rightClick(cx, cy)
        elif action == "type" and text_to_type:
            pyautogui.click(cx, cy)
            time.sleep(0.15)
            try:
                import pyperclip
                pyperclip.copy(text_to_type)
                pyautogui.hotkey('ctrl', 'v')
            except Exception:
                pyautogui.write(text_to_type, interval=0.01)
            time.sleep(0.1)
        elif action == "scroll":
            scroll_amt = int(text_to_type) if text_to_type and str(text_to_type).lstrip('-').isdigit() else -300
            pyautogui.scroll(scroll_amt, x=cx, y=cy)
        return True

    def plan_and_execute_task(self, natural_language_goal: str, update_callback=None) -> Dict[str, Any]:
        """High-speed DAG synthesizer and executor with resilient model failover."""
        clean_goal = re.sub(r'^(?:point\s*break|tars|jarvis)?[\s,\-:]*(?:can\s+you\s+|please\s+)?(?:automate\s+tasks?|automate|self\s*drive|self-drive|agent\s+execute|agent\s+plan|agent|autonomous\s+task|autonomous\s+agent|drive\s+windows\s+to)[\s,\-:\'"]*', '', natural_language_goal, flags=re.I).strip()
        clean_goal = re.sub(r'^(?:and\s+|to\s+|for\s+)', '', clean_goal, flags=re.I).strip()
        clean_goal = clean_goal.strip(" '\"`-,.:;!?")
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
You are the Autonomous Desktop Operating Engine for Point Break (Windows 11/10).
Goal: "{clean_goal}"

Create an optimal, fast step-by-step action plan.
Allowed Actions:
- "open_url": target = full URL (e.g. "https://www.amazon.in/s?k=...", "https://www.youtube.com/results?search_query=...", "https://www.google.com/search?q=...")
- "play_youtube": target = search query string
- "set_volume": level = integer (0 to 100)
- "launch_app": target = executable command (e.g. "notepad", "chrome", "calc", "cmd", "explorer")
- "hotkey": keys = array of keys (e.g. ["ctrl", "s"], ["alt", "f4"], ["enter"])
- "click": target = UI button/element description
- "type": target = element description, value = text to write
- "scroll": direction = "down" or "up", amount = integer (e.g. 300)
- "wait": seconds = float (e.g. 0.5, 1.0)

CRITICAL DIRECTIVE FOR SEARCH & SHOPPING:
If the goal is to search for a product or topic on a website (e.g., 'on amazon search X', 'find X on amazon', 'search youtube for X'), use ONE 'open_url' action with the complete query URL (e.g. 'https://www.amazon.in/s?k=X' or 'https://www.youtube.com/results?search_query=X') rather than just opening the homepage!

Output ONLY valid JSON:
{{
  "goal": "{clean_goal}",
  "steps": [
    {{ "step": 1, "action": "action_name", "target": "value", "description": "what this does" }}
  ]
}}
"""
        steps = []
        last_err = None

        for m in AGENT_MODELS:
            try:
                print(f"[Agent Planner] Querying model: {m}...")
                model = genai.GenerativeModel(m)
                res = model.generate_content(plan_prompt, request_options={"timeout": 15.0})
                match = re.search(r'\{.*\}', res.text.strip(), re.DOTALL)
                if match:
                    plan_data = json.loads(match.group(0))
                    steps = plan_data.get("steps", [])
                    if steps:
                        print(f"[Agent Planner] ✅ Plan synthesized with {len(steps)} steps via {m}!")
                        break
            except Exception as e:
                print(f"[Agent Planner] Model {m} failed: {e}")
                last_err = e
                continue

        if not steps:
            err_msg = f"Planning failed: {last_err}"
            if update_callback: update_callback({"goal": clean_goal, "status": "failed", "description": err_msg})
            with self._lock: self.is_running = False
            return {"success": False, "error": err_msg}

        try:
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
                    lvl = int(step.get("level", step.get("target", 50)))
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
                    app = str(step.get("target", "")).strip()
                    if app:
                        subprocess.Popen(app, shell=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
                        step_success = True

                elif action == "click":
                    target_name = step.get("target", "")
                    max_click_retries = 2
                    click_verified = False

                    for attempt in range(max_click_retries + 1):
                        _pre_img, _pre_path = self.capture_active_screen()
                        step_success = self.resolve_and_interact(target_name, action="click")

                        if step_success and _pre_img:
                            time.sleep(0.35 + attempt * 0.2)
                            _post_img, _post_path = self.capture_active_screen()
                            if _post_img and _pre_img:
                                try:
                                    import numpy as _np
                                    _pre_arr = _np.array(_pre_img.convert("RGB"), dtype=_np.float32)
                                    _post_arr = _np.array(_post_img.convert("RGB"), dtype=_np.float32)
                                    if _pre_arr.shape == _post_arr.shape:
                                        _diff = _np.mean(_np.abs(_pre_arr - _post_arr))
                                        if _diff >= 1.5:
                                            print(f"[Agent Verify] ✅ Step {idx+1} click on '{target_name}' verified (diff={_diff:.1f})")
                                            click_verified = True
                                        else:
                                            print(f"[Agent Verify] ⚠️ Step {idx+1} click attempt {attempt+1} — screen unchanged (diff={_diff:.1f})")
                                except Exception:
                                    click_verified = True
                            if _post_path and os.path.exists(_post_path):
                                try: os.remove(_post_path)
                                except: pass
                        if _pre_path and os.path.exists(_pre_path):
                            try: os.remove(_pre_path)
                            except: pass

                        if click_verified or not step_success:
                            break
                        if attempt < max_click_retries:
                            print(f"[Agent Retry] 🔄 Retrying click on '{target_name}' (attempt {attempt+2}/{max_click_retries+1})...")
                            time.sleep(0.5)

                    if not click_verified and step_success:
                        print(f"[Agent Verify] ❌ Step {idx+1} click failed visual verification after {max_click_retries+1} attempts.")
                        step_success = False

                elif action == "double_click":
                    step_success = self.resolve_and_interact(step.get("target", ""), action="double_click")

                elif action == "type":
                    step_success = self.resolve_and_interact(
                        step.get("target", ""), 
                        action="type", 
                        text_to_type=step.get("value", "")
                    )

                elif action == "scroll":
                    direction = str(step.get("direction", "down")).lower()
                    amt = int(step.get("amount", 300))
                    scroll_val = -abs(amt) if direction == "down" else abs(amt)
                    pyautogui.scroll(scroll_val)
                    step_success = True

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

                time.sleep(0.20)

            # ── Tier 1: verification_before_completion guardrail ──
            failed_steps = [s for s in self.execution_log if not s.get("success")]
            total_steps = len(self.execution_log)

            with self._lock:
                self.is_running = False

            if failed_steps:
                fail_desc = f"Completed {total_steps - len(failed_steps)}/{total_steps} steps. {len(failed_steps)} step(s) failed."
                print(f"[Agent] ⚠️ {fail_desc}")
                if update_callback:
                    update_callback({"goal": clean_goal, "status": "partial", "description": fail_desc, "steps": self.execution_log})
                return {"success": False, "partial": True, "goal": clean_goal, "steps_executed": total_steps, "steps_failed": len(failed_steps)}

            if update_callback:
                update_callback({"goal": clean_goal, "status": "completed", "description": f"Completed all {len(steps)} steps.", "steps": self.execution_log})

            print(f"[Agent] ✅ Finished Autonomous Workflow for '{clean_goal}' successfully!"
            )
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
