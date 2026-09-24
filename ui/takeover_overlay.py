"""
Point Break Tactical Human Takeover Overlay
===========================================
Displays a sleek top-docked HUD banner when Point Break pauses execution
for manual human interaction (e.g. entering banking OTP, solving CAPTCHA).
Allows resuming the agent via button or keyboard event.
"""

import sys
import threading
import queue
import time
from typing import Optional, Callable

class TakeoverOverlay:
    def __init__(self):
        self._is_active = False
        self._resume_event = threading.Event()
        self._root = None

    @property
    def is_active(self) -> bool:
        return self._is_active

    def activate(self, reason: str = "Manual User Action Required", on_resume: Optional[Callable[[], None]] = None):
        """
        Activates the takeover banner on top of the screen and blocks until user clicks Resume.
        """
        self._is_active = True
        self._resume_event.clear()

        def _gui_worker():
            try:
                import tkinter as tk

                root = tk.Tk()
                self._root = root
                root.title("Point Break — Takeover Active")
                root.geometry("640x72")
                root.resizable(False, False)
                root.attributes("-topmost", True)
                root.overrideredirect(True) # Borderless floating bar
                root.configure(bg="#0f172a")

                # Center at top of screen
                sw = root.winfo_screenwidth()
                x = (sw - 640) // 2
                y = 12
                root.geometry(f"+{x}+{y}")

                # Inner border frame
                frame = tk.Frame(root, bg="#1e293b", highlightbackground="#3b82f6", highlightthickness=2, padx=16, pady=8)
                frame.pack(fill=tk.BOTH, expand=True)

                lbl_status = tk.Label(
                    frame,
                    text="🖐 POINT BREAK PAUSED — HUMAN IN CONTROL",
                    bg="#1e293b",
                    fg="#fbbf24",
                    font=("Segoe UI", 10, "bold")
                )
                lbl_status.pack(anchor="w")

                lbl_sub = tk.Label(
                    frame,
                    text=f"{reason} | Complete the action, then click Resume.",
                    bg="#1e293b",
                    fg="#94a3b8",
                    font=("Segoe UI", 9)
                )
                lbl_sub.pack(anchor="w")

                def _resume_clicked():
                    self._resume_event.set()
                    try:
                        root.destroy()
                    except Exception:
                        pass
                    self._is_active = False
                    if on_resume:
                        on_resume()

                btn_resume = tk.Button(
                    frame,
                    text="▶ RESUME AGENT",
                    bg="#10b981",
                    fg="#ffffff",
                    activebackground="#059669",
                    activeforeground="#ffffff",
                    font=("Segoe UI", 10, "bold"),
                    relief=tk.FLAT,
                    padx=14,
                    pady=4,
                    command=_resume_clicked,
                    cursor="hand2"
                )
                btn_resume.place(relx=1.0, rely=0.5, anchor="e", x=-10)

                # Hotkey fallback inside window if focused
                root.bind("<Escape>", lambda e: _resume_clicked())

                root.mainloop()

            except Exception as e:
                print(f"[TakeoverOverlay] GUI error: {e}")
                self._resume_event.set()
                self._is_active = False

        t = threading.Thread(target=_gui_worker, daemon=True)
        t.start()

    def wait_for_resume(self, timeout: Optional[float] = None) -> bool:
        """Blocks until the user clicks Resume or timeout expires."""
        res = self._resume_event.wait(timeout=timeout)
        self._is_active = False
        return res

    def close(self):
        """Programmatically closes the banner if open."""
        self._resume_event.set()
        self._is_active = False
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass

takeover_overlay = TakeoverOverlay()
