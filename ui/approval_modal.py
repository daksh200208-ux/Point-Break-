"""
Point Break Tactical Desktop Approval Modal
============================================
Presents a high-contrast, dark-themed tactical modal on top of Windows for
R3/R4 authorization gates with instant hotkey support:
- [ Enter ] : Approve
- [ Esc ]   : Reject
- [ T ]     : Take Control
"""

import sys
import threading
import queue
import time
from typing import Dict, Any, Optional

def show_desktop_approval_modal(
    title: str,
    risk_level: str,
    action_name: str,
    summary: str,
    details: Dict[str, Any],
    timeout_sec: float = 60.0
) -> str:
    """
    Spawns a top-level tactical modal dialog.
    Returns: 'APPROVED', 'REJECTED', 'TAKEOVER', or 'TIMEOUT'
    """
    res_queue: queue.Queue = queue.Queue()

    def _gui_worker():
        try:
            import tkinter as tk
            from tkinter import ttk

            root = tk.Tk()
            root.title("Point Break — Authorization Gate")
            root.geometry("520x360")
            root.resizable(False, False)
            root.attributes("-topmost", True)
            root.configure(bg="#0b0f19")

            # Center window on screen
            root.update_idletasks()
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            x = (sw - 520) // 2
            y = (sh - 360) // 2
            root.geometry(f"+{x}+{y}")

            # Styling colors
            bg_card = "#131b2e"
            fg_text = "#e2e8f0"
            fg_sub = "#94a3b8"
            accent_color = "#f59e0b" if risk_level == "R3" else "#ef4444"

            # Outer frame
            container = tk.Frame(root, bg="#0b0f19", padx=24, pady=20)
            container.pack(fill=tk.BOTH, expand=True)

            # Top Header Bar
            header_frame = tk.Frame(container, bg="#0b0f19")
            header_frame.pack(fill=tk.X, pady=(0, 10))

            lbl_badge = tk.Label(
                header_frame,
                text=f"  [{risk_level} GATE]  ",
                bg=accent_color,
                fg="#000000",
                font=("Consolas", 10, "bold"),
                relief=tk.FLAT
            )
            lbl_badge.pack(side=tk.LEFT)

            lbl_title = tk.Label(
                header_frame,
                text=title,
                bg="#0b0f19",
                fg=fg_text,
                font=("Segoe UI", 12, "bold")
            )
            lbl_title.pack(side=tk.LEFT, padx=12)

            # Card Body
            card = tk.Frame(container, bg=bg_card, relief=tk.RIDGE, bd=1, padx=16, pady=14)
            card.pack(fill=tk.BOTH, expand=True, pady=10)

            lbl_act = tk.Label(
                card,
                text=f"Action: {action_name.replace('_', ' ').title()}",
                bg=bg_card,
                fg="#38bdf8",
                font=("Segoe UI", 11, "bold"),
                anchor="w"
            )
            lbl_act.pack(fill=tk.X, pady=(0, 4))

            lbl_summary = tk.Label(
                card,
                text=summary,
                bg=bg_card,
                fg=fg_text,
                font=("Segoe UI", 10),
                wraplength=450,
                justify=tk.LEFT,
                anchor="w"
            )
            lbl_summary.pack(fill=tk.X, pady=(0, 10))

            # Details List
            if details:
                det_frame = tk.Frame(card, bg="#0e1626", padx=8, pady=6)
                det_frame.pack(fill=tk.BOTH, expand=True)
                row_idx = 0
                for k, v in list(details.items())[:5]:
                    tk.Label(det_frame, text=f"{k}:", bg="#0e1626", fg=fg_sub, font=("Consolas", 9, "bold"), anchor="w").grid(row=row_idx, column=0, sticky="w", padx=4, pady=2)
                    tk.Label(det_frame, text=f"{v}", bg="#0e1626", fg="#f8fafc", font=("Consolas", 9), anchor="w").grid(row=row_idx, column=1, sticky="w", padx=4, pady=2)
                    row_idx += 1

            # Buttons Frame
            btn_frame = tk.Frame(container, bg="#0b0f19")
            btn_frame.pack(fill=tk.X, pady=(12, 0))

            def _on_approve(event=None):
                res_queue.put("APPROVED")
                root.destroy()

            def _on_reject(event=None):
                res_queue.put("REJECTED")
                root.destroy()

            def _on_takeover(event=None):
                res_queue.put("TAKEOVER")
                root.destroy()

            # Keyboard Hotkeys
            root.bind("<Return>", _on_approve)
            root.bind("<KP_Enter>", _on_approve)
            root.bind("<Escape>", _on_reject)
            root.bind("t", _on_takeover)
            root.bind("T", _on_takeover)

            btn_approve = tk.Button(
                btn_frame,
                text="✔ APPROVE (Enter)",
                bg="#10b981",
                fg="#ffffff",
                activebackground="#059669",
                activeforeground="#ffffff",
                font=("Segoe UI", 10, "bold"),
                relief=tk.FLAT,
                padx=12,
                pady=6,
                command=_on_approve,
                cursor="hand2"
            )
            btn_approve.pack(side=tk.LEFT, padx=(0, 8))

            btn_reject = tk.Button(
                btn_frame,
                text="✖ REJECT (Esc)",
                bg="#ef4444",
                fg="#ffffff",
                activebackground="#dc2626",
                activeforeground="#ffffff",
                font=("Segoe UI", 10, "bold"),
                relief=tk.FLAT,
                padx=12,
                pady=6,
                command=_on_reject,
                cursor="hand2"
            )
            btn_reject.pack(side=tk.LEFT, padx=(0, 8))

            btn_takeover = tk.Button(
                btn_frame,
                text="🖐 TAKE CONTROL (T)",
                bg="#6366f1",
                fg="#ffffff",
                activebackground="#4f46e5",
                activeforeground="#ffffff",
                font=("Segoe UI", 10, "bold"),
                relief=tk.FLAT,
                padx=12,
                pady=6,
                command=_on_takeover,
                cursor="hand2"
            )
            btn_takeover.pack(side=tk.RIGHT)

            # Timeout handler
            def _check_timeout():
                res_queue.put("TIMEOUT")
                root.destroy()

            timer = root.after(int(timeout_sec * 1000), _check_timeout)

            root.mainloop()

        except Exception as e:
            print(f"[ApprovalModal] GUI Error: {e}")
            res_queue.put("ERROR")

    t = threading.Thread(target=_gui_worker, daemon=True)
    t.start()

    try:
        decision = res_queue.get(timeout=timeout_sec + 2.0)
        return decision if decision != "ERROR" else _fallback_cli_prompt(action_name, summary, details)
    except queue.Empty:
        return "TIMEOUT"

def _fallback_cli_prompt(action_name: str, summary: str, details: Dict[str, Any]) -> str:
    """CLI fallback when GUI display is unavailable."""
    print(f"\n=======================================================")
    print(f" [TACTICAL APPROVAL REQUIRED] Action: {action_name}")
    print(f" Summary: {summary}")
    if details:
        print(f" Details: {details}")
    print(f" Options: [A]pprove | [R]eject | [T]ake Control")
    print(f"=======================================================")
    try:
        choice = input("Enter choice (A/R/T): ").strip().upper()
        if choice.startswith("A"): return "APPROVED"
        if choice.startswith("T"): return "TAKEOVER"
        return "REJECTED"
    except Exception:
        return "REJECTED"
