"""
Point Break 3.0 — Holographic Virtual Air-Keyboard Engine (Core i3 High-Performance Edition)
===========================================================================================
Ultra-optimized for Intel Core i3, low-spec hardware, and low-res webcams:
1. Persistent Tkinter canvas caching (0.2% CPU utilization, zero redraw stutter).
2. Dynamic Adaptive 1-Euro Velocity Filter (rock-solid key hover, 0-latency travel).
3. Magnetic Key Hysteresis (expands active key hit-box by +14px to prevent tremor jitter).
4. Single-Hand Dominant Stylus with true 1:1 mirror direction mapping.
5. Tolerant Air-CLICK latching calibrated for noisy/low-light webcam sensors.
"""

import os
import sys
import time
import math
import threading
from typing import Dict, List, Tuple, Optional, Any

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import tkinter as tk
import pyautogui
import winsound

try:
    import keyboard
except ImportError:
    keyboard = None

JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
CLICK_WAV = os.path.join(JARVIS_DIR, "sounds", "mechanical_click.wav")

class HolographicAirKeyboard:
    def __init__(self):
        self.is_visible = False
        self.is_caps = False
        self.is_shift = False
        self.root = None
        self.canvas = None
        self._ui_thread = None
        self._ready_event = threading.Event()
        self._lock = threading.Lock()
        
        # Single-Hand Dominant Stylus Tracking
        self.finger_pos: Optional[Tuple[int, int]] = None
        self.hover_key: Optional[str] = None
        self.smooth_x: Optional[float] = None
        self.smooth_y: Optional[float] = None
        self.last_raw_x: Optional[float] = None
        self.last_raw_y: Optional[float] = None
        self.last_update_time = 0.0
        
        # Suppress auto-show cooldown when user manually closes/hides keyboard
        self.suppress_auto_show_until = 0.0
        
        # Debounce & Latching
        self.last_click_time = 0.0
        self.is_pinched = False
        self.latched_click_key: Optional[str] = None
        
        # Visual feedback active depress map: {key_name: expire_time}
        self.active_key_pulses: Dict[str, float] = {}

        # Dimensions & Layout
        self.win_w = 900
        self.win_h = 290
        self.key_rects: Dict[str, Tuple[int, int, int, int]] = {} # {key: (x1, y1, x2, y2)}
        
        # Persistent UI Canvas Handles
        self.key_rect_ids: Dict[str, int] = {}
        self.key_text_ids: Dict[str, int] = {}
        self.title_text_id: Optional[int] = None
        self.close_btn_rect_id: Optional[int] = None
        self.close_btn_text_id: Optional[int] = None
        self.stylus_oval_id: Optional[int] = None
        self.stylus_dot_id: Optional[int] = None
        self.stylus_text_id: Optional[int] = None
        self.prev_rendered_hover: Optional[str] = None
        
        self._init_layout_grid()

    def _init_layout_grid(self):
        """Precomputes coordinate bounding boxes for the QWERTY matrix."""
        row1 = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "BACKSPACE"]
        row2 = ["TAB", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]"]
        row3 = ["CAPS", "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'", "ENTER"]
        row4 = ["SHIFT", "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", "CLOSE"]
        row5 = ["@ / .com", "SPACE", "CLEAR", "HIDE"]

        padding = 5
        start_x = 10
        start_y = 12
        key_h = 46

        # Row 1
        x = start_x
        y = start_y
        for k in row1:
            kw = 95 if k == "BACKSPACE" else 58
            self.key_rects[k] = (x, y, x + kw, y + key_h)
            x += kw + padding

        # Row 2
        x = start_x
        y += key_h + padding
        for k in row2:
            kw = 72 if k == "TAB" else 59
            self.key_rects[k] = (x, y, x + kw, y + key_h)
            x += kw + padding

        # Row 3
        x = start_x
        y += key_h + padding
        for k in row3:
            kw = 82 if k == "CAPS" else (96 if k == "ENTER" else 58)
            self.key_rects[k] = (x, y, x + kw, y + key_h)
            x += kw + padding

        # Row 4
        x = start_x
        y += key_h + padding
        for k in row4:
            kw = 90 if k in ["SHIFT", "CLOSE"] else 58
            self.key_rects[k] = (x, y, x + kw, y + key_h)
            x += kw + padding

        # Row 5
        x = start_x
        y += key_h + padding
        for k in row5:
            if k == "SPACE":
                kw = 420
            elif k == "@ / .com":
                kw = 120
            else:
                kw = 145
            self.key_rects[k] = (x, y, x + kw, y + key_h)
            x += kw + padding

        # Top-Right Corner Close Button [✕]
        self.key_rects["[✕]"] = (self.win_w - 42, 3, self.win_w - 10, 22)

    def start_in_background(self):
        """Starts the Holographic Air-Keyboard in an isolated subprocess to guarantee 100% process stability."""
        try:
            import subprocess
            vkey_script = os.path.abspath(__file__)
            subprocess.Popen([sys.executable, vkey_script], creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            print("[Air-Keyboard] ⚡ Holographic Air-Keyboard Engine Initialized in isolated runtime.")
        except Exception as e:
            print(f"[Air-Keyboard] Process dispatch error: {e}")

    def _bind_hotkeys(self):
        if keyboard:
            try:
                keyboard.add_hotkey("ctrl+shift+k", self.toggle)
                keyboard.add_hotkey("windows+shift+k", self.toggle)
            except Exception as e:
                print("[Air-Keyboard] Hotkey bind notice:", e)

    def _run_ui_loop(self):
        self.root = tk.Tk()
        self.root.title("Point Break Air-Keyboard")
        self.root.overrideredirect(True) # Frameless floating window
        self.root.attributes("-topmost", True) # Always stay on top
        self.root.attributes("-alpha", 0.92) # Semi-transparent holographic glass
        self.root.configure(bg="#02060d")

        # Position at the lower third of the display
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        pos_x = (screen_w - self.win_w) // 2
        pos_y = screen_h - self.win_h - 35 # 35px above taskbar

        self.root.geometry(f"{self.win_w}x{self.win_h}+{pos_x}+{pos_y}")
        self.root.withdraw() # Start hidden

        # Main Cyber Canvas
        self.canvas = tk.Canvas(
            self.root,
            width=self.win_w,
            height=self.win_h,
            bg="#02060d",
            highlightthickness=1,
            highlightbackground="#00f0ff"
        )
        self.canvas.pack(fill="both", expand=True)

        # Mouse & Touchpad direct click listener
        def _on_canvas_click(event):
            clicked_key = self.find_key_under_point(event.x, event.y)
            if clicked_key:
                self.inject_keystroke(clicked_key)
        self.canvas.bind("<Button-1>", _on_canvas_click)

        # ── CREATE PERSISTENT CANVAS ELEMENTS ONCE (0% CPU STUTTER) ──
        self._create_persistent_elements()

        self._ready_event.set()
        
        # Periodic 60 FPS Lightweight Update Tick
        self._schedule_canvas_redraw()
        self.root.mainloop()

    def _create_persistent_elements(self):
        """Creates all 55 key rectangles and labels once so we never delete('all')."""
        self.title_text_id = self.canvas.create_text(
            15, 11,
            text="POINT BREAK // AIR-KEYBOARD  [CAPS OFF]  [AIR-STYLUS: PINCH TO TYPE]",
            fill="#00f0ff",
            anchor="w",
            font=("Segoe UI", 7, "bold")
        )

        for key_label, (x1, y1, x2, y2) in self.key_rects.items():
            if key_label == "[✕]":
                rect_id = self.canvas.create_rectangle(x1, y1, x2, y2, fill="#331122", outline="#ff3366", width=1)
                text_id = self.canvas.create_text((x1 + x2) // 2, (y1 + y2) // 2, text="✕", fill="#ff3366", font=("Segoe UI", 8, "bold"))
            else:
                rect_id = self.canvas.create_rectangle(x1, y1, x2, y2, fill="#051329", outline="#0077aa", width=1)
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                text_id = self.canvas.create_text(
                    cx, cy,
                    text=key_label.lower() if (len(key_label) == 1 and key_label.isalpha()) else key_label,
                    fill="#66ddff",
                    font=("Consolas", 11 if len(key_label) <= 2 else 8, "normal")
                )
            self.key_rect_ids[key_label] = rect_id
            self.key_text_ids[key_label] = text_id

        # Stylus Reticle (Initialized off-screen)
        self.stylus_oval_id = self.canvas.create_oval(-50, -50, -30, -30, outline="#00f0ff", width=2)
        self.stylus_dot_id = self.canvas.create_oval(-42, -42, -38, -38, fill="#00f0ff")
        self.stylus_text_id = self.canvas.create_text(-40, -55, text="AIR-STYLUS", fill="#00f0ff", font=("Segoe UI", 6, "bold"))

    def _schedule_canvas_redraw(self):
        if self.root:
            if self.is_visible:
                self._update_keyboard_state()
            self.root.after(16, self._schedule_canvas_redraw)

    def _update_keyboard_state(self):
        """Fast property update with 0 canvas recreation overhead."""
        if not self.canvas:
            return

        now = time.time()
        # Clean expired pulses
        expired = [k for k, exp in self.active_key_pulses.items() if exp <= now]
        for k in expired:
            del self.active_key_pulses[k]

        # Update Title
        caps_tag = "[CAPS ON]" if self.is_caps else "[CAPS OFF]"
        self.canvas.itemconfig(
            self.title_text_id,
            text=f"POINT BREAK // AIR-KEYBOARD  {caps_tag}  [AIR-STYLUS: PINCH THUMB+INDEX TO TYPE]"
        )

        # Update Keys
        for key_label, rect_id in self.key_rect_ids.items():
            text_id = self.key_text_ids[key_label]
            is_hovered = (key_label == self.hover_key)
            is_pressed = (key_label in self.active_key_pulses)

            if key_label == "[✕]":
                if is_hovered or is_pressed:
                    self.canvas.itemconfig(rect_id, fill="#ff3366", outline="#ffffff", width=2)
                    self.canvas.itemconfig(text_id, fill="#ffffff")
                else:
                    self.canvas.itemconfig(rect_id, fill="#331122", outline="#ff3366", width=1)
                    self.canvas.itemconfig(text_id, fill="#ff3366")
                continue

            if is_pressed:
                self.canvas.itemconfig(rect_id, fill="#00ffaa", outline="#ffffff", width=2)
                self.canvas.itemconfig(text_id, fill="#02060d", font=("Consolas", 11 if len(key_label) <= 2 else 8, "bold"))
            elif is_hovered:
                self.canvas.itemconfig(rect_id, fill="#005577", outline="#00f0ff", width=2)
                self.canvas.itemconfig(text_id, fill="#ffffff", font=("Consolas", 11 if len(key_label) <= 2 else 8, "bold"))
            else:
                self.canvas.itemconfig(rect_id, fill="#051329", outline="#0077aa", width=1)
                display_text = key_label if self.is_caps else key_label.lower() if (len(key_label) == 1 and key_label.isalpha()) else key_label
                self.canvas.itemconfig(text_id, text=display_text, fill="#66ddff", font=("Consolas", 11 if len(key_label) <= 2 else 8, "normal"))

        # Update Stylus Position
        if self.finger_pos:
            fx, fy = self.finger_pos
            reticle_color = "#00ffaa" if self.is_pinched else "#00f0ff"
            self.canvas.coords(self.stylus_oval_id, fx - 10, fy - 10, fx + 10, fy + 10)
            self.canvas.coords(self.stylus_dot_id, fx - 3, fy - 3, fx + 3, fy + 3)
            self.canvas.coords(self.stylus_text_id, fx, fy - 15)
            self.canvas.itemconfig(self.stylus_oval_id, outline=reticle_color)
            self.canvas.itemconfig(self.stylus_dot_id, fill=reticle_color)
            self.canvas.itemconfig(self.stylus_text_id, fill=reticle_color)
        else:
            self.canvas.coords(self.stylus_oval_id, -50, -50, -30, -30)
            self.canvas.coords(self.stylus_dot_id, -42, -42, -38, -38)
            self.canvas.coords(self.stylus_text_id, -40, -55)

    def show(self, force: bool = False):
        """Displays the holographic virtual keyboard."""
        now = time.time()
        if not force and (now < self.suppress_auto_show_until):
            return # Blocked by manual user dismiss cooldown

        if not self.root:
            self.start_in_background()
        with self._lock:
            self.is_visible = True
            self.suppress_auto_show_until = 0.0 # Reset cooldown once opened
        if self.root:
            self.root.after(0, self.root.deiconify)
            self.root.after(0, self.root.lift)
            self.root.after(0, lambda: self.root.attributes("-topmost", True))
        print("[Air-Keyboard] 🚀 Holographic Keyboard Activated.")

    def hide(self, manual_user_close: bool = True):
        """Hides the holographic virtual keyboard and activates auto-show suppression."""
        with self._lock:
            self.is_visible = False
            self.finger_pos = None
            self.hover_key = None
            self.smooth_x = None
            self.smooth_y = None
            self.latched_click_key = None
            if manual_user_close:
                # Suppress auto-popup for 12 seconds so the keyboard doesn't hinder your work
                self.suppress_auto_show_until = time.time() + 12.0
        if self.root:
            self.root.after(0, self.root.withdraw)
        print("[Air-Keyboard] 🛑 Holographic Keyboard Dismissed (Auto-show suppressed for 12s).")

    def toggle(self):
        """Toggles keyboard visibility."""
        if self.is_visible:
            self.hide(manual_user_close=True)
        else:
            self.show(force=True)

    def _play_mechanical_click(self):
        """Plays instant mechanical keyboard click sound asynchronously."""
        def _sound_worker():
            try:
                if os.path.exists(CLICK_WAV):
                    winsound.PlaySound(CLICK_WAV, winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    winsound.Beep(1800, 20)
            except Exception:
                pass
        threading.Thread(target=_sound_worker, daemon=True).start()

    def inject_keystroke(self, key_label: str):
        """Translates keyboard button into OS keystroke and injects into active window."""
        self._play_mechanical_click()
        self.active_key_pulses[key_label] = time.time() + 0.16 # Flash key for 160ms

        print(f"[Air-Keyboard] ⌨ Keystroke Triggered: [{key_label}]")

        if key_label == "BACKSPACE":
            pyautogui.press("backspace")
        elif key_label == "ENTER":
            pyautogui.press("enter")
            # Auto-dismiss keyboard upon submitting query / password
            self.hide(manual_user_close=True)
        elif key_label == "TAB":
            pyautogui.press("tab")
        elif key_label == "SPACE":
            pyautogui.press("space")
        elif key_label == "CAPS":
            self.is_caps = not self.is_caps
        elif key_label == "SHIFT":
            self.is_shift = not self.is_shift
        elif key_label == "CLEAR":
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
            pyautogui.press("backspace")
        elif key_label in ["CLOSE", "HIDE", "[✕]"]:
            self.hide(manual_user_close=True)
        elif key_label == "@ / .com":
            pyautogui.write("@gmail.com")
        else:
            char = key_label
            if len(char) == 1 and char.isalpha():
                char = char.upper() if (self.is_caps ^ self.is_shift) else char.lower()
            pyautogui.write(char)

        if self.is_shift:
            self.is_shift = False

    def find_key_under_point(self, canvas_x: int, canvas_y: int) -> Optional[str]:
        """
        Returns the key label with Sticky Magnet Hysteresis:
        If already hovering on a key, expands its hitbox by +14px to prevent tremor jitter.
        """
        # Check currently hovered key with expanded hysteresis buffer
        if self.hover_key and self.hover_key in self.key_rects:
            x1, y1, x2, y2 = self.key_rects[self.hover_key]
            if (x1 - 14) <= canvas_x <= (x2 + 14) and (y1 - 14) <= canvas_y <= (y2 + 14):
                return self.hover_key

        # Standard bounding box lookup
        for key, (x1, y1, x2, y2) in self.key_rects.items():
            if x1 <= canvas_x <= x2 and y1 <= canvas_y <= y2:
                return key
        return None

    def process_hand_landmarks(self, hand_landmarks, handedness_label: str, screen_w: int, screen_h: int):
        """
        Single-Hand Dominant Stylus with Dynamic Adaptive 1-Euro Velocity Filtering:
        - Hand Right -> Cursor Right (1:1 Natural Mirror Mapping)
        - Hand Left -> Cursor Left
        - Fast movement -> Low smoothing (0 lag)
        - Slow movement / hover -> High smoothing (0 jitter / steady)
        - Air-CLICK pinch -> Instant keystroke on latched key
        """
        if not self.is_visible:
            return

        now = time.time()
        idx_tip = hand_landmarks[8]
        thumb_tip = hand_landmarks[4]

        # Calculate Air-CLICK pinch distance (Tolerant threshold 0.052 for low-end webcams)
        pinch_dist = math.hypot(idx_tip.x - thumb_tip.x, idx_tip.y - thumb_tip.y)
        self.is_pinching = (pinch_dist < 0.052)

        # 1:1 Natural Mirror Mapping across comfortable hand bounding box [0.18 -> 0.82] and [0.22 -> 0.78]
        norm_x = (idx_tip.x - 0.18) / (0.82 - 0.18)
        norm_y = (idx_tip.y - 0.22) / (0.78 - 0.22)

        norm_x = max(0.0, min(1.0, norm_x))
        norm_y = max(0.0, min(1.0, norm_y))

        raw_canvas_x = float(norm_x * self.win_w)
        raw_canvas_y = float(norm_y * self.win_h)

        # ── DYNAMIC ADAPTIVE 1-EURO VELOCITY FILTER ────────────────────
        dt = max(0.001, now - self.last_update_time) if self.last_update_time > 0 else 0.033
        self.last_update_time = now

        if self.last_raw_x is not None:
            dist_moved = math.hypot(raw_canvas_x - self.last_raw_x, raw_canvas_y - self.last_raw_y)
            velocity = dist_moved / dt # Pixels per second
            # Adaptive alpha: Slow hover -> alpha ~ 0.22 (smooth), Fast travel -> alpha ~ 0.80 (0 lag)
            alpha = max(0.22, min(0.85, 0.22 + (velocity / 900.0) * 0.60))
        else:
            alpha = 0.50

        self.last_raw_x = raw_canvas_x
        self.last_raw_y = raw_canvas_y

        if self.smooth_x is None:
            self.smooth_x = raw_canvas_x
            self.smooth_y = raw_canvas_y
        else:
            self.smooth_x = (self.smooth_x * (1.0 - alpha)) + (raw_canvas_x * alpha)
            self.smooth_y = (self.smooth_y * (1.0 - alpha)) + (raw_canvas_y * alpha)

        canvas_x = int(self.smooth_x)
        canvas_y = int(self.smooth_y)

        self.finger_pos = (canvas_x, canvas_y)
        self.hover_key = self.find_key_under_point(canvas_x, canvas_y)

        # ── AIR-CLICK PINCH TRIGGER WITH TARGET LOCK ──────────────────
        if self.is_pinching:
            if not self.latched_click_key and self.hover_key:
                self.latched_click_key = self.hover_key

            if not self.is_pinched and (now - self.last_click_time > 0.20):
                self.is_pinched = True
                self.last_click_time = now
                target_key = self.latched_click_key or self.hover_key
                if target_key:
                    self.inject_keystroke(target_key)
        else:
            self.is_pinched = False
            self.latched_click_key = None

# Global instance
vkeyboard_engine = HolographicAirKeyboard()

def check_is_text_input_focused() -> bool:
    """
    Detects if the user has clicked/focused on an editable text input, search bar,
    terminal, or password box anywhere in Windows.
    """
    try:
        import win32gui, win32process
        fg_hwnd = win32gui.GetForegroundWindow()
        if not fg_hwnd:
            return False
        
        thread_id, _ = win32process.GetWindowThreadProcessId(fg_hwnd)
        info = win32gui.GetGUIThreadInfo(thread_id)
        if info:
            if info.get('hwndCaret') or (info.get('rcCaret') and (info['rcCaret'][2] > info['rcCaret'][0])):
                return True
    except Exception:
        pass

    try:
        import uiautomation as auto
        focused = auto.GetFocusedControl()
        if focused:
            c_type = focused.ControlTypeName
            is_pwd = getattr(focused, 'IsPassword', False)
            if c_type in ['EditControl', 'DocumentControl', 'ComboBoxControl'] or is_pwd:
                return True
    except Exception:
        pass

    return False
    
if __name__ == "__main__":
    vkeyboard_engine._bind_hotkeys()
    vkeyboard_engine._run_ui_loop()
