"""
Point Break 3.0 — Proactive Ambient Awareness & Screen Explainer
================================================================
1. Instant Screen Explanation & Auto-Solve (Triggerable via Voice or Win+Shift+X).
2. Active Window & Context Tracker.
3. Voice Dictation / Direct Command Trigger (Win+Shift+Z or Voice).
"""

import os
import sys
import time
import json
import tempfile
import threading
from typing import Dict, Any, Optional, Callable

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pyautogui
from PIL import Image

try:
    import win32gui
    import win32process
except ImportError:
    win32gui = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    import keyboard
except ImportError:
    keyboard = None

from dotenv import load_dotenv
JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(JARVIS_DIR, ".env"))

try:
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
except ImportError:
    genai = None

class AmbientAwarenessEngine:
    def __init__(self, gemini_model="models/gemini-2.5-flash"):
        self.gemini_model_name = gemini_model
        self.last_context = {}
        self._lock = threading.Lock()

    def get_foreground_context(self) -> Dict[str, Any]:
        """Returns active window title, process name, and high-level context."""
        context = {
            "window_title": "Desktop",
            "process_name": "explorer.exe",
            "timestamp": time.strftime("%H:%M:%S")
        }
        if win32gui and psutil:
            try:
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd)
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                context["window_title"] = title or "Unknown"
                context["process_name"] = proc.name()
            except Exception:
                pass
        self.last_context = context
        return context

    def explain_and_solve_screen(self, speak_fn: Optional[Callable[[str], None]] = None, hud_fn: Optional[Callable[[Dict[str, Any]], None]] = None) -> str:
        """
        Captures the live screen and uses Gemini Vision with multi-model failover
        to provide a concise explanation and solution.
        """
        context = self.get_foreground_context()
        w_title = context.get('window_title', '').lower()
        
        # If currently focused on the Point Break HUD / Console, give user time to switch
        if any(h in w_title for h in ["localhost", "8787", "point break console", "point break hud"]):
            if speak_fn:
                speak_fn("Please switch to your target window, sir. Capturing in two seconds...")
            time.sleep(2.0)
            context = self.get_foreground_context()
        elif speak_fn:
            speak_fn("Analyzing your screen now, sir.")

        print("[Ambient] 👁️ Capturing live screen for instant explanation & auto-solving...")

        # Capture real desktop screen directly using pyautogui
        img_path = None
        try:
            shot = pyautogui.screenshot()
            # Resize if large for fast upload & inference
            w, h = shot.size
            if w > 1600:
                new_h = int(h * (1600 / w))
                shot = shot.resize((1600, new_h), Image.Resampling.LANCZOS)
            
            tmp_fd, img_path = tempfile.mkstemp(suffix=".jpg", prefix="pb_screen_solve_")
            os.close(tmp_fd)
            shot.save(img_path, format="JPEG", quality=82)
        except Exception as snap_err:
            print(f"[Ambient Snapshot Warning]: {snap_err}")
            try:
                from pointbreak_agent import agent_engine
                _, img_path = agent_engine.capture_active_screen()
            except Exception:
                tmp_fd, img_path = tempfile.mkstemp(suffix=".jpg", prefix="pb_screen_solve_")
                os.close(tmp_fd)
                Image.new("RGB", (1920, 1080), color=(10, 15, 25)).save(img_path)

        if not genai:
            if img_path and os.path.exists(img_path): os.remove(img_path)
            return "Gemini Vision AI is not configured."

        context = self.get_foreground_context()
        prompt = f"""
You are Point Break — Daksh's elite tactical AI assistant.
Active Window: "{context.get('window_title')}"
Running Process: "{context.get('process_name')}"

Analyze this screen carefully. Deliver:
1. SUMMARY: What is currently displayed (1-2 sentences).
2. KEY INSIGHT / SOLUTION: If there is an error, code bug, formula, question, or document on screen, give the direct answer or next tactical step.
3. Keep the tone concise, intelligent, and natural for voice readout.
"""
        models_to_try = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.6-flash"
        ]

        explanation = None
        last_err = None

        for m_name in models_to_try:
            try:
                print(f"[Ambient] Trying vision model: {m_name}...")
                model = genai.GenerativeModel(m_name)
                img = Image.open(img_path)
                response = model.generate_content([prompt, img], request_options={"timeout": 15.0})
                if response and response.text:
                    explanation = response.text.strip()
                    print(f"\n[Ambient] 🧠 Screen Analysis ({m_name}):\n{explanation}\n")
                    break
            except Exception as e:
                print(f"[Ambient] Model {m_name} failed: {e}")
                last_err = e
                continue

        if not explanation:
            err_msg = f"Screen analysis error: {last_err}"
            print(f"[Ambient] {err_msg}")
            if speak_fn:
                speak_fn("I encountered an issue connecting to the vision matrix, sir.")
            if img_path and os.path.exists(img_path):
                try: os.remove(img_path)
                except: pass
            return err_msg

        try:
            if hud_fn:
                hud_fn({
                    "screen_explanation": explanation,
                    "context": context,
                    "timestamp": time.strftime("%H:%M:%S")
                })

            if speak_fn:
                # Speak first 2-3 sentences for rapid vocal response
                spoken_part = ". ".join(explanation.split(". ")[:3])
                if not spoken_part.endswith("."):
                    spoken_part += "."
                speak_fn(spoken_part)

            return explanation
        finally:
            if img_path and os.path.exists(img_path):
                try: os.remove(img_path)
                except: pass

    def setup_hotkeys(self, on_explain_callback: Callable, on_dictate_callback: Callable):
        """Registers optional global hotkeys (Win+Shift+X and Win+Shift+Z)."""
        if keyboard:
            try:
                keyboard.add_hotkey("windows+shift+x", on_explain_callback)
                keyboard.add_hotkey("windows+shift+z", on_dictate_callback)
                print("[Ambient] 🧠 Global hotkeys 'Win+Shift+X' (Screen Solve) and 'Win+Shift+Z' (Dictate) active.")
            except Exception as e:
                print(f"[Ambient] Ambient hotkey registration error: {e}")

# Global instance
ambient_engine = AmbientAwarenessEngine()
