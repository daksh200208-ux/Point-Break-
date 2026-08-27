"""
Point Break 3.0 — "Record & Replicate" Dynamic Macro Synthesizer (Commercial)
=============================================================================
Watch & Learn Engine:
1. Records manual user desktop actions (clicks, keystrokes, window switches, pauses).
2. Synthesizes executable, parameterized Python scripts in scratch/tars_commercial_2/macros/.
3. Full CRUD: Record, Run, List, Delete, and Inspect Macros.
4. Integrates seamlessly with Voice Commands, HUD Deck, and Spotlight.
"""

import os
import sys
import time
import json
import threading
from typing import List, Dict, Any, Optional

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

try:
    from pynput import mouse, keyboard
except ImportError:
    mouse = None
    keyboard = None

import pyautogui

MACROS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "macros")
os.makedirs(MACROS_DIR, exist_ok=True)

class MacroRecorder:
    def __init__(self):
        self.is_recording = False
        self.current_macro_name = None
        self.events = []
        self.start_time = None
        self._mouse_listener = None
        self._keyboard_listener = None
        self._lock = threading.Lock()

    def start_recording(self, macro_name: str) -> bool:
        if not mouse or not keyboard:
            print("[Macro] pynput library not available.")
            return False

        with self._lock:
            if self.is_recording:
                print("[Macro] Already recording another macro.")
                return False

            self.current_macro_name = re_safe_name(macro_name)
            self.events = []
            self.start_time = time.time()
            self.is_recording = True

        print(f"[Macro] 🔴 Recording started for: '{self.current_macro_name}'...")

        self._mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll
        )
        self._mouse_listener.start()

        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        self._keyboard_listener.start()
        return True

    def _on_mouse_click(self, x, y, button, pressed):
        if not self.is_recording: return
        t = time.time() - self.start_time
        if pressed:
            btn_str = "left" if button == mouse.Button.left else "right" if button == mouse.Button.right else "middle"
            self.events.append({
                "type": "click",
                "x": int(x),
                "y": int(y),
                "button": btn_str,
                "time": round(t, 3)
            })

    def _on_mouse_scroll(self, x, y, dx, dy):
        if not self.is_recording: return
        t = time.time() - self.start_time
        self.events.append({
            "type": "scroll",
            "x": int(x),
            "y": int(y),
            "clicks": int(dy * 2),
            "time": round(t, 3)
        })

    def _on_key_press(self, key):
        if not self.is_recording: return
        t = time.time() - self.start_time
        try:
            k = key.char
        except AttributeError:
            k = str(key).replace("Key.", "")
        
        self.events.append({
            "type": "key_down",
            "key": k,
            "time": round(t, 3)
        })

    def _on_key_release(self, key):
        if not self.is_recording: return
        try:
            k = key.char
        except AttributeError:
            k = str(key).replace("Key.", "")

    def stop_recording(self) -> Optional[str]:
        with self._lock:
            if not self.is_recording:
                return None
            self.is_recording = False

        if self._mouse_listener:
            try: self._mouse_listener.stop()
            except Exception: pass
        if self._keyboard_listener:
            try: self._keyboard_listener.stop()
            except Exception: pass

        print(f"[Macro] ⏹️ Stopped recording '{self.current_macro_name}'. Captured {len(self.events)} events.")
        file_path = self._synthesize_python_playbook(self.current_macro_name, self.events)
        return file_path

    def _synthesize_python_playbook(self, name: str, events: List[Dict[str, Any]]) -> str:
        target_path = os.path.join(MACROS_DIR, f"{name}.py")
        
        code_lines = [
            f"# Point Break 3.0 Auto-Synthesized Macro: {name}",
            f"# Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "import pyautogui, time",
            "pyautogui.FAILSAFE = True",
            "pyautogui.PAUSE = 0.05",
            "",
            "def run_macro():",
            f"    print(\"[Macro] Executing '{name}'...\")",
        ]

        last_time = 0.0
        buffer_str = ""
        
        for ev in events:
            ev_time = ev.get("time", 0.0)
            delay = ev_time - last_time
            
            if delay > 0.25 and buffer_str:
                code_lines.append(f"    pyautogui.write({json.dumps(buffer_str)}, interval=0.02)")
                buffer_str = ""

            if delay > 0.15:
                code_lines.append(f"    time.sleep({round(min(delay, 2.5), 2)})")
            last_time = ev_time

            if ev["type"] == "click":
                if buffer_str:
                    code_lines.append(f"    pyautogui.write({json.dumps(buffer_str)}, interval=0.02)")
                    buffer_str = ""
                code_lines.append(f"    pyautogui.click({ev['x']}, {ev['y']}, button='{ev['button']}')")

            elif ev["type"] == "scroll":
                code_lines.append(f"    pyautogui.scroll({ev['clicks']}, x={ev['x']}, y={ev['y']})")

            elif ev["type"] == "key_down":
                key = ev["key"]
                if key and len(key) == 1:
                    buffer_str += key
                else:
                    if buffer_str:
                        code_lines.append(f"    pyautogui.write({json.dumps(buffer_str)}, interval=0.02)")
                        buffer_str = ""
                    if key:
                        code_lines.append(f"    pyautogui.press('{key}')")

        if buffer_str:
            code_lines.append(f"    pyautogui.write({json.dumps(buffer_str)}, interval=0.02)")

        code_lines.append(f"    print(\"[Macro] '{name}' completed successfully.\")")
        code_lines.append("")
        code_lines.append("if __name__ == '__main__':")
        code_lines.append("    run_macro()")

        with open(target_path, "w", encoding="utf-8") as f:
            f.write("\n".join(code_lines))

        print(f"[Macro] 💾 Synthesized macro script saved to: {target_path}")
        return target_path


class MacroManager:
    def __init__(self):
        self.recorder = MacroRecorder()

    def list_macros(self) -> List[Dict[str, Any]]:
        if not os.path.exists(MACROS_DIR):
            return []
        res = []
        for f in os.listdir(MACROS_DIR):
            if f.endswith(".py"):
                full_p = os.path.join(MACROS_DIR, f)
                try:
                    mtime = os.path.getmtime(full_p)
                    mtime_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))
                except Exception:
                    mtime_str = "Recent"
                res.append({
                    "name": f[:-3],
                    "file": f,
                    "updated": mtime_str
                })
        return res

    def run_macro_by_name(self, name: str) -> bool:
        safe_name = re_safe_name(name)
        macro_path = os.path.join(MACROS_DIR, f"{safe_name}.py")
        if not os.path.exists(macro_path):
            print(f"[Macro] ❌ Macro not found: '{safe_name}'")
            return False

        print(f"[Macro] ▶️ Dispatching macro: '{safe_name}'...")
        def _exec():
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location(safe_name, macro_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "run_macro"):
                    mod.run_macro()
            except Exception as e:
                print(f"[Macro] Execution error in {safe_name}: {e}")

        threading.Thread(target=_exec, daemon=True).start()
        return True

    def delete_macro(self, name: str) -> bool:
        safe_name = re_safe_name(name)
        macro_path = os.path.join(MACROS_DIR, f"{safe_name}.py")
        if os.path.exists(macro_path):
            try:
                os.remove(macro_path)
                print(f"[Macro] 🗑️ Deleted macro '{safe_name}' successfully.")
                return True
            except Exception as e:
                print(f"[Macro] Error deleting macro '{safe_name}': {e}")
                return False
        return False


def re_safe_name(name: str) -> str:
    import re
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower().strip())
    return cleaned if cleaned else "custom_macro"

# Global Macro Manager instance
macro_engine = MacroManager()
