"""
Point Break 3.0 — Next-Gen Spotlight / Floating Command Palette (Alt + Space)
============================================================================
Raycast / Spotlight style translucent overlay for instant desktop commands,
app launching, macro triggering, and generative AI queries.
"""

import os
import sys
import threading
import time
import tkinter as tk
from typing import Callable, Optional

try:
    import keyboard
except ImportError:
    keyboard = None

class SpotlightPalette:
    def __init__(self, command_callback: Optional[Callable[[str], None]] = None):
        self.callback = command_callback
        self.root = None
        self.entry = None
        self.is_visible = False
        self._tk_thread = None
        self._ready_event = threading.Event()

    def start_in_background(self):
        """Starts the Spotlight Palette in an isolated subprocess to ensure 100% process & UI thread safety."""
        try:
            import subprocess
            spotlight_script = os.path.abspath(__file__)
            subprocess.Popen([sys.executable, spotlight_script], creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            print("[Spotlight] 🛸 Global hotkey 'Alt + Space' active in isolated runtime.")
        except Exception as e:
            print(f"[Spotlight] Process spawn error: {e}")

    def _run_ui(self):
        self.root = tk.Tk()
        self.root.title("Point Break Spotlight")
        self.root.overrideredirect(True) # Frameless
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg="#02060d")

        # Dimensions & Centering
        width = 680
        height = 70
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = (screen_w - width) // 2
        y = int(screen_h * 0.22) # Top center

        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.withdraw() # Start hidden

        # Container Frame with Neon Border
        outer_frame = tk.Frame(self.root, bg="#00f0ff", padx=1, pady=1)
        outer_frame.pack(fill="both", expand=True)

        inner_frame = tk.Frame(outer_frame, bg="#040e1f", padx=15, pady=12)
        inner_frame.pack(fill="both", expand=True)

        # Icon
        icon_lbl = tk.Label(inner_frame, text="⚡", bg="#040e1f", fg="#00f0ff", font=("Segoe UI", 16))
        icon_lbl.pack(side="left", padx=(0, 10))

        # Command Entry
        self.entry = tk.Entry(
            inner_frame, 
            bg="#040e1f", 
            fg="#e2f1f8", 
            insertbackground="#00f0ff",
            font=("Rajdhani", 16, "bold"),
            relief="flat",
            highlightthickness=0
        )
        self.entry.pack(side="left", fill="both", expand=True)
        self.entry.bind("<Return>", self._on_submit)
        self.entry.bind("<Escape>", lambda e: self.hide())
        
        # Subtext / Hint
        hint_lbl = tk.Label(inner_frame, text="ESC TO CLOSE", bg="#040e1f", fg="#0088ff", font=("Segoe UI", 8, "bold"))
        hint_lbl.pack(side="right", padx=(10, 0))

        self.root.bind("<FocusOut>", lambda e: self.hide())
        self._ready_event.set()
        self.root.mainloop()

    def _bind_global_hotkey(self):
        if keyboard:
            try:
                keyboard.add_hotkey("alt+space", self.toggle)
                print("[Spotlight] 🛸 Global hotkey 'Alt + Space' active.")
            except Exception as e:
                print(f"[Spotlight] Hotkey registration error: {e}")

    def show(self):
        if not self.root: return
        def _show():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.entry.delete(0, tk.END)
            self.entry.focus_set()
            self.is_visible = True
        self.root.after(0, _show)

    def hide(self):
        if not self.root or not self.is_visible: return
        def _hide():
            self.root.withdraw()
            self.is_visible = False
        self.root.after(0, _hide)

    def toggle(self):
        if self.is_visible:
            self.hide()
        else:
            self.show()

    def _on_submit(self, event=None):
        cmd = self.entry.get().strip()
        self.hide()
        if cmd:
            print(f"[Spotlight] Dispatched directive: '{cmd}'")
            if self.callback:
                threading.Thread(target=self.callback, args=(cmd,), daemon=True).start()
            else:
                try:
                    import urllib.request, urllib.parse
                    url = f"http://127.0.0.1:8000/api/command?query={urllib.parse.quote(cmd)}"
                    urllib.request.urlopen(url, timeout=2.0)
                except Exception as ex:
                    print(f"[Spotlight] HTTP dispatch error: {ex}")

# Global instance
spotlight_engine = SpotlightPalette()

if __name__ == "__main__":
    spotlight_engine._bind_global_hotkey()
    spotlight_engine._run_ui()
