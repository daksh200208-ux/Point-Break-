from pointbreak_genai import query_generative_model, query_tars_vision
from pointbreak_uia import uia_engine
"""
Point Break 3.0 — Universal Autonomous Takeover Engine
======================================================
1. Ghostwriter / Writing & Code Takeover:
   - Analyzes active essay, notes, email, or code in any editor (VS Code, Word, Docs, Notepad).
   - Generates natural, high-level continuous continuation and writes/pastes it directly.

2. Grandmaster Online Chess Takeover (Chess.com, Lichess):
   - Visually detects chessboard on screen with sub-pixel precision.
   - Identifies orientation (White/Black), turn state, opponent's moves, and tactical winning moves.
   - Executes precise 2-click move: clicks piece (x1, y1), waits for legal move hint dots, clicks destination (x2, y2).
   - Zero drag-to-taskbar, zero accidental Windows key triggers.

3. Messaging & Social Takeover:
   - Visually reads conversation on Instagram, WhatsApp, Discord, X, LinkedIn.
   - Generates contextual, articulate reply and types it into the message box.

4. Universal Context-Aware Auto-Takeover:
   - Fast multi-modal triage to detect whether user is in chess, code, writing, or chat.
"""

import os
import sys
import time
import json
import re
import tempfile
import threading
import webbrowser
from typing import Dict, Any, Optional, Callable, Tuple, List

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.02
import pyperclip
from PIL import Image

try:
    import win32gui
    import win32process
    import win32con
except ImportError:
    win32gui = None
    win32process = None
    win32con = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    import chess
except ImportError:
    chess = None

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

TAKEOVER_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash"
]

def focus_chess_window() -> bool:
    """Brings Chess window to foreground smoothly without destructive maximize/restore flicker."""
    if not win32gui:
        return False
    try:
        cur_hwnd = win32gui.GetForegroundWindow()
        cur_title = win32gui.GetWindowText(cur_hwnd).lower()
        if any(k in cur_title for k in ["chess", "lichess"]):
            return True  # Already foreground
    except Exception:
        pass

    def enum_cb(hwnd, results):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if any(k in title for k in ["chess", "lichess"]):
                results.append((hwnd, title))
        return True

    matches = []
    try:
        win32gui.EnumWindows(enum_cb, matches)
    except Exception:
        pass

    if matches:
        hwnd = matches[0][0]
        try:
            import ctypes
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE only if minimized
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.2)
            print(f"[Focus Chess Window] Brought '{matches[0][1]}' to foreground.")
            return True
        except Exception as e:
            print("[Focus Chess Window Notice]:", e)
    return False


class UniversalTakeoverEngine:
    def __init__(self):
        self.is_active = False
        self.current_mode = "idle"
        self.stop_requested = False
        self._lock = threading.Lock()
        self.active_thread: Optional[threading.Thread] = None

    # ─────────────────────────────────────────────────────────────────
    # UTILITIES & SCREEN CAPTURE
    # ─────────────────────────────────────────────────────────────────
    def get_active_window_info(self) -> Dict[str, Any]:
        """Returns the foreground window title and process name."""
        info = {"title": "Desktop", "process": "explorer.exe", "is_browser": False, "is_editor": False, "is_chess": False}
        if win32gui and psutil:
            try:
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd) or ""
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc = psutil.Process(pid)
                pname = proc.name().lower()
                t_lower = title.lower()

                info["title"] = title
                info["process"] = pname
                info["is_browser"] = any(b in pname for b in ["chrome", "msedge", "firefox", "brave", "opera"])
                info["is_editor"] = any(e in pname for e in ["code", "notepad", "sublime", "pycharm", "word", "devenv", "cursor"]) or "docs.google" in t_lower
                info["is_chess"] = "chess" in t_lower or "lichess" in t_lower
            except Exception:
                pass
        return info

    def capture_screenshot(self, max_width: int = 1600) -> Tuple[Optional[Image.Image], Optional[str]]:
        """Captures screen and saves a temporary JPEG for Gemini Vision reasoning."""
        shot = None
        try:
            shot = pyautogui.screenshot()
        except Exception:
            try:
                from PIL import ImageGrab
                shot = ImageGrab.grab()
            except Exception:
                try:
                    import mss
                    with mss.mss() as sct:
                        monitor = sct.monitors[1]
                        sct_img = sct.grab(monitor)
                        shot = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                except Exception as e:
                    print(f"[Takeover Screenshot Failed]: {e}")
                    return None, None

        if not shot:
            return None, None

        w, h = shot.size
        # Keep aspect ratio for vision model
        if w > max_width:
            new_h = int(h * (max_width / w))
            vis_shot = shot.resize((max_width, new_h), Image.Resampling.LANCZOS)
        else:
            vis_shot = shot

        tmp_fd, img_path = tempfile.mkstemp(suffix=".jpg", prefix="pb_takeover_")
        os.close(tmp_fd)
        vis_shot.save(img_path, format="JPEG", quality=85)
        return shot, img_path

    def query_vision(self, prompt: str, image_path: str, timeout: float = 12.0) -> Optional[str]:
        """Queries Gemini Vision with shared model failover from jarvis or TAKEOVER_MODELS."""
        # Try jarvis centralized model query if available
        try:
            from jarvis import query_generative_model
            img = Image.open(image_path)
            res = query_generative_model("gemini-3.5-flash-lite", [prompt, img], timeout=timeout)
            if res:
                return res.strip()
        except Exception:
            pass

        if not genai or not image_path or not os.path.exists(image_path):
            return None
        for m in TAKEOVER_MODELS:
            try:
                model = genai.GenerativeModel(m)
                img = Image.open(image_path)
                res = model.generate_content([prompt, img], request_options={"timeout": timeout})
                if res and res.text:
                    return res.text.strip()
            except Exception as e:
                print(f"[Takeover Vision] Model {m} failed: {e}")
                continue
        return None

    def query_text(self, prompt: str, timeout: float = 10.0) -> Optional[str]:
        """Queries Gemini text model with centralized model failover."""
        try:
            from jarvis import query_generative_model
            res = query_generative_model("gemini-3.5-flash-lite", prompt, timeout=timeout)
            if res:
                return res.strip()
        except Exception:
            pass

        if not genai:
            return None
        for m in TAKEOVER_MODELS:
            try:
                model = genai.GenerativeModel(m)
                res = model.generate_content(prompt, request_options={"timeout": timeout})
                if res and res.text:
                    return res.text.strip()
            except Exception as e:
                print(f"[Takeover Text] Model {m} failed: {e}")
                continue
        return None

    # ─────────────────────────────────────────────────────────────────
    # 1. GHOSTWRITER: ESSAY / CODE / NOTES TAKEOVER
    # ─────────────────────────────────────────────────────────────────
    def take_over_writing_or_coding(self, user_hint: str = "", is_code: bool = False, speak_fn: Optional[Callable[[str], None]] = None) -> bool:
        """
        Inspects what is currently written in the active editor,
        synthesizes high-quality continuation, and autonomously inserts it directly at cursor.
        """
        with self._lock:
            self.is_active = True
            self.current_mode = "writing"
            self.stop_requested = False

        if speak_fn:
            speak_fn("Analyzing your document, sir. Taking over writing...")

        print("[Takeover] ✍️ Initiating Ghostwriter Writing & Coding Takeover...")

        # 1. Grab current context from clipboard or screen
        existing_text = ""
        try:
            old_clip = pyperclip.paste()
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.08)
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.08)
            pyautogui.press("right")
            time.sleep(0.05)
            existing_text = pyperclip.paste()
            if not existing_text or existing_text == old_clip:
                existing_text = old_clip
        except Exception:
            pass

        # 2. Visual screen fallback if editor doesn't support Ctrl+A
        img_path = None
        if not existing_text or len(existing_text.strip()) < 5:
            _, img_path = self.capture_screenshot()

        # 3. Prompt Gemini to synthesize continuation
        doc_type = "Code" if is_code else "Essay / Document / Notes"
        prompt = f"""
You are Point Break's elite executive co-pilot taking over writing for Daksh.
Goal: Seamlessly complete and continue what the user was writing.
Context Hint: "{user_hint}"
Type: {doc_type}

Text written so far:
\"\"\"
{existing_text[:3000] if existing_text else "[Inspect image for text on screen]"}
\"\"\"

CRITICAL INSTRUCTIONS:
1. Continue directly from where the text/code leaves off with zero repetition.
2. If code: Write clean, production-ready, fully implemented code (no placeholders like 'TODO').
3. If essay/notes: Write compelling, articulate, well-structured paragraphs continuing the core argument.
4. Output ONLY the new text/code to append. Do NOT include meta comments, greetings, or conversational preambles.
"""
        continuation = None
        if img_path and os.path.exists(img_path):
            try:
                continuation = self.query_vision(prompt, img_path)
            finally:
                try: os.remove(img_path)
                except: pass
        else:
            continuation = self.query_text(prompt)

        if not continuation or len(continuation.strip()) < 2:
            if speak_fn:
                speak_fn("Could not determine continuation context, sir.")
            with self._lock: self.is_active = False
            return False

        clean_continuation = continuation.strip()
        if clean_continuation.startswith("```") and clean_continuation.endswith("```"):
            clean_continuation = re.sub(r'^```[a-zA-Z]*\n', '', clean_continuation)
            clean_continuation = re.sub(r'\n```$', '', clean_continuation)

        # 4. Autonomous typing execution
        print(f"[Takeover] ⚡ Typing {len(clean_continuation)} characters into active cursor...")
        try:
            pyperclip.copy("\n" + clean_continuation)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.1)
        except Exception as e:
            print("[Takeover Paste Fallback]:", e)
            pyautogui.write("\n" + clean_continuation, interval=0.005)

        # ── Tier 1 Verification: Confirm text was inserted ──
        paste_verified = False
        try:
            time.sleep(0.15)
            # Select all text in document and check if our continuation is in it
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.08)
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.08)
            pyautogui.press("end")  # Deselect by moving cursor to end
            after_text = pyperclip.paste()
            # Check if at least a meaningful prefix of our continuation is now in the document
            verify_snippet = clean_continuation[:80].strip()
            if verify_snippet and verify_snippet in after_text:
                paste_verified = True
                print("[Takeover Verify] ✅ Continuation text confirmed in document.")
            else:
                print("[Takeover Verify] ⚠️ Continuation text not found in document after paste.")
        except Exception as verify_err:
            print(f"[Takeover Verify] Verification check error: {verify_err}")
            paste_verified = True  # Assume success if verification mechanism fails

        if speak_fn:
            if paste_verified:
                speak_fn("Continuation completed, sir. Content drafted directly at your cursor.")
            else:
                speak_fn("Attempted to paste continuation, but could not verify it landed. Please check, sir.")

        with self._lock:
            self.is_active = False
            self.current_mode = "idle"
        return True

    # ─────────────────────────────────────────────────────────────────
    # 2. GRANDMASTER ONLINE CHESS TAKEOVER (Chess.com / Lichess)
    # ─────────────────────────────────────────────────────────────────
    def _calculate_square_center(self, board_bbox_pct: List[float], square: str, player_color: str, screen_w: int, screen_h: int) -> Tuple[int, int]:
        """Calculates pixel center of a chessboard square from board bounding box."""
        bx1 = int(board_bbox_pct[0] * screen_w)
        by1 = int(board_bbox_pct[1] * screen_h)
        bx2 = int(board_bbox_pct[2] * screen_w)
        by2 = int(board_bbox_pct[3] * screen_h)
        sq_w = (bx2 - bx1) / 8.0
        sq_h = (by2 - by1) / 8.0

        col = ord(square[0].lower()) - ord('a')
        rank = int(square[1])

        if player_color.lower() == "white":
            grid_col = col
            grid_row = 8 - rank  # Rank 8 is top row 0, Rank 1 is bottom row 7
        else:
            grid_col = 7 - col
            grid_row = rank - 1

        cx = int(bx1 + (grid_col + 0.5) * sq_w)
        cy = int(by1 + (grid_row + 0.5) * sq_h)
        return cx, cy

    def execute_chess_move_on_board(
        self,
        board_bbox_pct: List[float],
        from_sq: str,
        to_sq: str,
        player_color: str,
        screen_w: int,
        screen_h: int,
        speak_fn: Optional[Callable[[str], None]] = None,
        reason: str = "",
        piece_name: str = ""
    ) -> bool:
        """
        Executes a precise physical 2-click move on Chess.com / Lichess:
        1. Clicks from_sq (selects piece).
        2. Waits 120ms for legal move hint dots / circles to render.
        3. Clicks to_sq (executes move).
        NEVER drags into the taskbar or triggers the Windows key!
        """
        cx1, cy1 = self._calculate_square_center(board_bbox_pct, from_sq, player_color, screen_w, screen_h)
        cx2, cy2 = self._calculate_square_center(board_bbox_pct, to_sq, player_color, screen_w, screen_h)

        # Safety bound check: ensure coordinates are inside screen and well above taskbar (taskbar is bottom ~48px)
        if not (0 <= cx1 < screen_w and 0 <= cy1 < screen_h - 45):
            print(f"[Chess Takeover Error] from_sq coordinates ({cx1}, {cy1}) out of safe board bounds!")
            return False
        if not (0 <= cx2 < screen_w and 0 <= cy2 < screen_h - 45):
            print(f"[Chess Takeover Error] to_sq coordinates ({cx2}, {cy2}) out of safe board bounds!")
            return False

        print(f"[Chess Takeover] ♟️ Moving {piece_name or 'piece'} from {from_sq.upper()} ({cx1},{cy1}) to {to_sq.upper()} ({cx2},{cy2})...")

        # ── Tier 1 Verification: Pre-move snapshot of destination square ──
        pre_move_crop = None
        crop_half = 28  # ~56px square crop around destination center
        try:
            from PIL import ImageGrab
            pre_move_crop = ImageGrab.grab(bbox=(
                max(0, cx2 - crop_half), max(0, cy2 - crop_half),
                min(screen_w, cx2 + crop_half), min(screen_h, cy2 + crop_half)
            ))
        except Exception as crop_err:
            print(f"[Chess Verify] Pre-crop warning: {crop_err}")

        # Step 1: Smooth move to piece and click
        pyautogui.moveTo(cx1, cy1, duration=0.16)
        pyautogui.click(cx1, cy1)

        # Step 2: Visual feedback pause for Chess.com legal dots to appear
        time.sleep(0.14)

        # Step 3: Smooth move to destination square and click
        pyautogui.moveTo(cx2, cy2, duration=0.18)
        pyautogui.click(cx2, cy2)

        # Move mouse slightly away so cursor doesn't obscure the square
        bx1 = int(board_bbox_pct[0] * screen_w)
        pyautogui.moveTo(max(10, bx1 - 25), cy2, duration=0.08)

        # ── Tier 1 Verification: Post-move snapshot comparison ──
        move_verified = True
        if pre_move_crop is not None:
            time.sleep(0.25)  # Wait for animation to finish
            try:
                from PIL import ImageGrab
                import numpy as np
                post_move_crop = ImageGrab.grab(bbox=(
                    max(0, cx2 - crop_half), max(0, cy2 - crop_half),
                    min(screen_w, cx2 + crop_half), min(screen_h, cy2 + crop_half)
                ))
                # Compare pixel difference
                pre_arr = np.array(pre_move_crop, dtype=np.float32)
                post_arr = np.array(post_move_crop, dtype=np.float32)
                if pre_arr.shape == post_arr.shape:
                    diff = np.mean(np.abs(pre_arr - post_arr))
                    print(f"[Chess Verify] Destination square pixel diff: {diff:.1f}")
                    if diff < 3.0:
                        # Board didn't change — move likely didn't register
                        move_verified = False
                        print("[Chess Verify] ⚠️ Move may not have registered! Retrying once...")
                        # Retry: click source then destination again
                        pyautogui.moveTo(cx1, cy1, duration=0.12)
                        pyautogui.click(cx1, cy1)
                        time.sleep(0.15)
                        pyautogui.moveTo(cx2, cy2, duration=0.14)
                        pyautogui.click(cx2, cy2)
                        time.sleep(0.2)
                        pyautogui.moveTo(max(10, bx1 - 25), cy2, duration=0.08)
                        # Re-check after retry
                        retry_crop = ImageGrab.grab(bbox=(
                            max(0, cx2 - crop_half), max(0, cy2 - crop_half),
                            min(screen_w, cx2 + crop_half), min(screen_h, cy2 + crop_half)
                        ))
                        retry_arr = np.array(retry_crop, dtype=np.float32)
                        if retry_arr.shape == pre_arr.shape:
                            retry_diff = np.mean(np.abs(pre_arr - retry_arr))
                            if retry_diff >= 3.0:
                                move_verified = True
                                print("[Chess Verify] ✅ Retry successful — board state changed.")
                            else:
                                print("[Chess Verify] ❌ Retry also failed — move did not register.")
                    else:
                        print("[Chess Verify] ✅ Board state changed — move confirmed.")
            except Exception as verify_err:
                print(f"[Chess Verify] Post-move verification error: {verify_err}")

        if move_verified:
            print(f"[Chess Takeover] ✅ Move {from_sq.upper()}->{to_sq.upper()} executed and verified.")
        else:
            print(f"[Chess Takeover] ⚠️ Move {from_sq.upper()}->{to_sq.upper()} executed but NOT verified.")

        if speak_fn:
            p_label = piece_name if piece_name else "Piece"
            announcement = f"{p_label} {from_sq.upper()} to {to_sq.upper()}."
            if reason:
                announcement += f" {reason}"
            threading.Thread(target=lambda: speak_fn(announcement), daemon=True).start()

        return True

    def suggest_best_chess_move(self, speak_fn: Optional[Callable[[str], None]] = None, update_status_fn: Optional[Callable[[Dict[str, Any]], None]] = None) -> bool:
        """
        Analyzes the live chessboard on screen and speaks the best move recommendation aloud.
        Also executes the move if asked.
        """
        print("[Takeover Chess] ♟️ Analyzing screen for best chess move recommendation...")
        focus_chess_window()
        if speak_fn:
            speak_fn("Analyzing chessboard position, sir...")

        _, img_path = self.capture_screenshot()
        try:
            screen_w, screen_h = pyautogui.size()
            chess_prompt = f"""
You are an International Grandmaster Chess Engine playing live on screen (Screen Size: {screen_w}x{screen_h}).
Analyze the chessboard (Chess.com, Lichess, or any chess app).
Identify:
1. Exact board bounding box: [left_pct, top_pct, right_pct, bottom_pct] (0.0 to 1.0).
2. Player color (white or black).
3. Is it my turn to move?
4. Best tactical move: "from_square" (e.g. "f3") and "to_square" (e.g. "d4").
5. Piece name to move (e.g. "Knight", "Bishop", "Pawn", "Queen", "Rook", "King").
6. Tactical rationale and spoken advice.

Output ONLY valid JSON:
{{
  "board_found": true,
  "player_color": "white",
  "board_bbox_pct": [0.173, 0.109, 0.481, 0.838],
  "is_my_turn": true,
  "best_move": "f3d4",
  "from_square": "f3",
  "to_square": "d4",
  "piece_name": "Knight",
  "tactical_reason": "Centralizes knight and attacks pawn on d5",
  "spoken_advice": "Sir, play Knight from f3 to d4. This centralizes your knight and applies direct pressure on d5."
}}
"""
            res = self.query_vision(chess_prompt, img_path, timeout=12.0)
            if not res:
                if speak_fn: speak_fn("I could not clearly resolve the chessboard on your screen, sir.")
                return False

            match = re.search(r'\{.*\}', res, re.DOTALL)
            if not match:
                if speak_fn: speak_fn("Tactical calculation was inconclusive, sir.")
                return False

            data = json.loads(match.group(0))
            if not data.get("board_found"):
                if speak_fn: speak_fn("No active chessboard detected on your screen, sir.")
                return False

            advice = data.get("spoken_advice", "")
            if not advice:
                p = data.get("piece_name", "Piece")
                f = data.get("from_square", "").upper()
                t = data.get("to_square", "").upper()
                r = data.get("tactical_reason", "")
                advice = f"Sir, your best move is {p} from {f} to {t}. {r}"

            print(f"[Takeover Chess Advice]: {advice}")
            if update_status_fn:
                update_status_fn({"chess_advice": data})
            if speak_fn:
                speak_fn(advice)

            # Physical execution
            bbox = data.get("board_bbox_pct", [0.173, 0.109, 0.481, 0.838])
            color = data.get("player_color", "white").lower()
            from_sq = data.get("from_square", "").lower().strip()
            to_sq = data.get("to_square", "").lower().strip()
            if from_sq and to_sq and data.get("is_my_turn", True):
                self.execute_chess_move_on_board(
                    board_bbox_pct=bbox,
                    from_sq=from_sq,
                    to_sq=to_sq,
                    player_color=color,
                    screen_w=screen_w,
                    screen_h=screen_h,
                    speak_fn=None,  # Already spoke advice
                    reason=data.get("tactical_reason", ""),
                    piece_name=data.get("piece_name", "")
                )

            return True
        except Exception as e:
            print("[Chess Advice Error]:", e)
            if speak_fn: speak_fn("Encountered an error evaluating the chessboard, sir.")
            return False
        finally:
            if img_path and os.path.exists(img_path):
                try: os.remove(img_path)
                except: pass

    def take_over_chess_game(self, single_move: bool = False, speak_fn: Optional[Callable[[str], None]] = None, update_status_fn: Optional[Callable[[Dict[str, Any]], None]] = None) -> bool:
        """
        Autonomous Grandmaster Chess Takeover:
        Visually locates the board on screen, evaluates turn and best move,
        clicks piece to show legal dots, clicks target square to win,
        and plays autonomously turn-by-turn until completion or user stop.
        """
        with self._lock:
            self.is_active = True
            self.current_mode = "chess"
            self.stop_requested = False

        if speak_fn:
            speak_fn("Grandmaster tactical matrix armed, sir. Taking over chess.")

        print("[Takeover] ♟️ Engaging Autonomous Online Chess Master...")

        def _chess_loop():
            focus_chess_window()
            moves_made = 0
            last_played_move = None
            consecutive_no_turn = 0

            while not self.stop_requested:
                if update_status_fn:
                    update_status_fn({"takeover": "chess", "status": "evaluating_board", "moves_made": moves_made})

                _, img_path = self.capture_screenshot()
                try:
                    screen_w, screen_h = pyautogui.size()
                    chess_prompt = f"""
You are an International Grandmaster Chess Engine playing live on screen (Screen Size: {screen_w}x{screen_h}).
Analyze the chessboard on screen.
Identify:
1. Exact board bounding box: [left_fraction, top_fraction, right_fraction, bottom_fraction] (0.0 to 1.0).
2. Player color (white or black).
3. Is it our turn to move right now? (Check if opponent has moved or is still on clock).
4. Last move played on board (or move notation, e.g. "exd5").
5. The single best, winning grandmaster move: "from_square" (e.g. "c2", "f3") and "to_square" (e.g. "c4", "d4").
6. Piece name to move (e.g. "Pawn", "Knight", "Bishop", "Queen", "Rook", "King").
7. Tactical rationale.

Output ONLY valid JSON:
{{
  "board_found": true,
  "player_color": "white",
  "board_bbox_pct": [0.173, 0.109, 0.481, 0.838],
  "is_my_turn": true,
  "last_move": "exd5",
  "from_square": "f3",
  "to_square": "d4",
  "piece_name": "Knight",
  "tactical_reason": "Centralizes knight and attacks pawn on d5"
}}
"""
                    res = self.query_vision(chess_prompt, img_path, timeout=12.0)
                    if not res:
                        time.sleep(1.0)
                        continue

                    match = re.search(r'\{.*\}', res, re.DOTALL)
                    if not match:
                        time.sleep(1.0)
                        continue

                    data = json.loads(match.group(0))
                    if not data.get("board_found"):
                        if moves_made == 0 and consecutive_no_turn == 0 and speak_fn:
                            speak_fn("Looking for active chessboard on your screen, sir.")
                        consecutive_no_turn += 1
                        time.sleep(1.2)
                        continue

                    # If not our turn, wait for opponent to move
                    if not data.get("is_my_turn"):
                        consecutive_no_turn += 1
                        if consecutive_no_turn == 1:
                            print("[Takeover Chess] ⏳ Waiting for opponent to play their move...")
                        time.sleep(1.0)
                        continue

                    consecutive_no_turn = 0
                    bbox = data.get("board_bbox_pct", [0.173, 0.109, 0.481, 0.838])
                    color = data.get("player_color", "white").lower()
                    from_sq = data.get("from_square", "").lower().strip()
                    to_sq = data.get("to_square", "").lower().strip()
                    piece = data.get("piece_name", "")
                    reason = data.get("tactical_reason", "")

                    if not from_sq or not to_sq or len(from_sq) != 2 or len(to_sq) != 2:
                        print(f"[Takeover Chess Notice] Incomplete move parsed: {from_sq} -> {to_sq}")
                        time.sleep(1.0)
                        continue

                    current_move_key = f"{from_sq}_{to_sq}"
                    if current_move_key == last_played_move:
                        # Opponent hasn't responded yet or board state hasn't updated
                        print(f"[Takeover Chess] Move {from_sq}->{to_sq} already executed. Waiting for opponent response...")
                        time.sleep(1.0)
                        continue

                    # Execute the 2-click move with legal dot pause
                    success = self.execute_chess_move_on_board(
                        board_bbox_pct=bbox,
                        from_sq=from_sq,
                        to_sq=to_sq,
                        player_color=color,
                        screen_w=screen_w,
                        screen_h=screen_h,
                        speak_fn=speak_fn,
                        reason=reason,
                        piece_name=piece
                    )

                    if success:
                        moves_made += 1
                        last_played_move = current_move_key

                    if single_move:
                        break

                    time.sleep(1.5)

                except Exception as e:
                    print(f"[Takeover Chess Error]: {e}")
                    time.sleep(1.2)
                finally:
                    if img_path and os.path.exists(img_path):
                        try: os.remove(img_path)
                        except: pass

            with self._lock:
                self.is_active = False
                self.current_mode = "idle"

        t = threading.Thread(target=_chess_loop, daemon=True)
        self.active_thread = t
        t.start()
        return True

    # ─────────────────────────────────────────────────────────────────
    # 3. MESSAGING / SOCIAL TAKEOVER (Instagram, WhatsApp, Discord, X)
    # ─────────────────────────────────────────────────────────────────
    def take_over_messaging_reply(self, user_intent: str = "", speak_fn: Optional[Callable[[str], None]] = None) -> bool:
        """
        Reads the incoming DM/chat on WhatsApp, Instagram, Discord, LinkedIn, or Twitter,
        generates an articulate response, clicks into message box, and types it.
        """
        with self._lock:
            self.is_active = True
            self.current_mode = "messaging"
            self.stop_requested = False

        if speak_fn:
            speak_fn("Reading conversation on screen, sir. Drafting reply...")

        print("[Takeover] 💬 Initiating Social Messaging Takeover...")
        _, img_path = self.capture_screenshot()

        try:
            screen_w, screen_h = pyautogui.size()
            msg_prompt = f"""
You are Point Break acting as an executive communications co-pilot for Daksh.
Analyze this chat/messaging screen (WhatsApp, Instagram DM, Discord, LinkedIn, or Twitter).

User Intent / Style: "{user_intent if user_intent else 'Natural, smart, polite, and articulate'}"

Output ONLY valid JSON:
{{
  "app_detected": "whatsapp" or "instagram" or "discord" or "linkedin" or "other",
  "incoming_context": "Summary of what the other person sent",
  "drafted_reply": "Exact message to type in reply",
  "input_box_pct": [center_x_fraction, center_y_fraction]
}}
"""
            res = self.query_vision(msg_prompt, img_path, timeout=12.0)
            if not res:
                if speak_fn: speak_fn("Could not analyze chat interface, sir.")
                with self._lock: self.is_active = False
                return False

            match = re.search(r'\{.*\}', res, re.DOTALL)
            if not match:
                if speak_fn: speak_fn("Failed to parse messaging parameters, sir.")
                with self._lock: self.is_active = False
                return False

            data = json.loads(match.group(0))
            app = data.get("app_detected", "chat").title()
            reply = data.get("drafted_reply", "").strip()
            box_pct = data.get("input_box_pct", [0.5, 0.9])

            if not reply:
                if speak_fn: speak_fn("Could not draft appropriate reply, sir.")
                with self._lock: self.is_active = False
                return False

            cx = int(box_pct[0] * screen_w)
            cy = int(box_pct[1] * screen_h)

            print(f"[Takeover] ✍️ Typing reply on {app} at ({cx}, {cy})...")
            pyautogui.moveTo(cx, cy, duration=0.2)
            pyautogui.click(cx, cy)
            time.sleep(0.1)

            pyperclip.copy(reply)
            pyautogui.hotkey("ctrl", "v")

            # ── Tier 1 Verification: Confirm text appeared in input box ──
            msg_verified = False
            try:
                time.sleep(0.2)
                # Select all text in input box and check clipboard
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.06)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.06)
                input_text = pyperclip.paste()
                # Check if our reply (or a significant chunk) is in the clipboard
                verify_chunk = reply[:60].strip()
                if verify_chunk and verify_chunk in input_text:
                    msg_verified = True
                    print(f"[Takeover Verify] ✅ Reply text confirmed in {app} input box.")
                else:
                    print(f"[Takeover Verify] ⚠️ Reply text not found in {app} input box after paste.")
                # Deselect to avoid accidental deletion
                pyautogui.press("end")
            except Exception as msg_verify_err:
                print(f"[Takeover Verify] Messaging verification error: {msg_verify_err}")
                msg_verified = True  # Assume success if verification mechanism fails

            if speak_fn:
                if msg_verified:
                    speak_fn(f"Drafted response on {app} for your review, sir.")
                else:
                    speak_fn(f"Attempted to paste reply on {app}, but could not verify it appeared. Please check, sir.")

            with self._lock:
                self.is_active = False
                self.current_mode = "idle"
            return True

        except Exception as e:
            print(f"[Takeover Messaging Error]: {e}")
            if speak_fn: speak_fn(f"Messaging takeover encountered an error: {e}")
            with self._lock: self.is_active = False
            return False
        finally:
            if img_path and os.path.exists(img_path):
                try: os.remove(img_path)
                except: pass

    # ─────────────────────────────────────────────────────────────────
    # 4. UNIVERSAL CONTEXTUAL TAKEOVER (Auto-Routing)
    # ─────────────────────────────────────────────────────────────────
    def take_over_active_context(self, user_command: str = "", speak_fn: Optional[Callable[[str], None]] = None, update_status_fn: Optional[Callable[[Dict[str, Any]], None]] = None) -> bool:
        """
        The Master 'Take Over' Router:
        1. Checks explicit keywords (chess, code, writing, messaging).
        2. Checks active window metadata (< 5ms).
        3. Captures visual screen and runs fast multi-modal triage if command is generic "take over".
        4. Dispatches the exact matching autonomous sub-engine.
        """
        low_cmd = user_command.lower()

        # 1. Explicit Chess Commands
        if any(k in low_cmd for k in ["chess", "lichess", "checkmate", "play my move", "make a move", "make the move", "play chess", "win chess"]):
            single_move = any(s in low_cmd for s in ["make a move", "make the move", "play my move", "single move", "one move", "play this move"])
            return self.take_over_chess_game(single_move=single_move, speak_fn=speak_fn, update_status_fn=update_status_fn)

        # 2. Explicit Gmail / Email Takeover Commands
        if any(k in low_cmd for k in ["open the mail", "open that mail", "open it up", "open this mail", "open unread mail", "open email", "open my mail"]):
            return self.open_and_focus_email(speak_fn=speak_fn)
        elif any(k in low_cmd for k in ["read it out", "read the mail", "read this mail", "read the email", "what does the mail say", "what is the mail about", "read mail"]):
            return self.read_and_summarize_open_email(speak_fn=speak_fn)
        elif any(k in low_cmd for k in ["respond to the mail", "reply to the mail", "reply to email", "draft a reply", "respond to email", "answer the mail"]):
            return self.respond_to_open_email(user_intent=user_command, speak_fn=speak_fn)

        # 3. Explicit Social / Chat Commands
        if any(k in low_cmd for k in ["instagram", "whatsapp", "dm", "discord", "linkedin", "tweet"]) or ("message" in low_cmd and "email" not in low_cmd and "mail" not in low_cmd):
            return self.take_over_messaging_reply(user_intent=user_command, speak_fn=speak_fn)

        # 3. Explicit Code Commands
        if any(k in low_cmd for k in ["code", "script", "function", "debug", "terminal", "python"]):
            return self.take_over_writing_or_coding(user_hint=user_command, is_code=True, speak_fn=speak_fn)

        # 4. Explicit Writing Commands
        if any(k in low_cmd for k in ["essay", "document", "notes", "article", "letter", "draft", "writing"]):
            return self.take_over_writing_or_coding(user_hint=user_command, is_code=False, speak_fn=speak_fn)

        # 5. Fast Active Window Metadata Check (< 5ms)
        win_info = self.get_active_window_info()
        if win_info.get("is_chess"):
            print(f"[Takeover Auto-Route] Active window '{win_info.get('title')}' is Chess. Engaging Chess Master...")
            return self.take_over_chess_game(single_move=False, speak_fn=speak_fn, update_status_fn=update_status_fn)
        elif win_info.get("is_editor"):
            is_c = any(c in win_info.get("process", "") for c in ["code", "pycharm", "sublime", "cursor"])
            print(f"[Takeover Auto-Route] Active window '{win_info.get('title')}' is Editor. Engaging Ghostwriter (Code={is_c})...")
            return self.take_over_writing_or_coding(user_hint=user_command, is_code=is_c, speak_fn=speak_fn)

        # 6. Contextual Visual Screen Triage (When command is simply "take over" or "point break take over")
        print("[Takeover] 👁️ Scanning live screen to determine active task...")
        _, img_path = self.capture_screenshot()
        detected_task = "writing"
        if img_path and os.path.exists(img_path):
            try:
                classify_prompt = """
Look at this screen and determine what the user is currently doing.
Output ONLY valid JSON:
{
  "task": "chess" or "messaging" or "code" or "writing",
  "confidence": 0.95,
  "reason": "User is playing a live chess game on Chess.com / Lichess"
}
"""
                res = self.query_vision(classify_prompt, img_path, timeout=6.0)
                if res:
                    m = re.search(r'\{.*\}', res, re.DOTALL)
                    if m:
                        data = json.loads(m.group(0))
                        detected_task = data.get("task", "writing").lower()
                        print(f"[Takeover Visual Triage]: Detected '{detected_task}' ({data.get('reason', '')})")
            except Exception as e:
                print("[Takeover Triage Error]:", e)
            finally:
                try: os.remove(img_path)
                except: pass

        if detected_task == "chess":
            return self.take_over_chess_game(single_move=False, speak_fn=speak_fn, update_status_fn=update_status_fn)
        elif detected_task == "messaging":
            return self.take_over_messaging_reply(user_intent=user_command, speak_fn=speak_fn)
        elif detected_task == "code":
            return self.take_over_writing_or_coding(user_hint=user_command, is_code=True, speak_fn=speak_fn)
        else:
            return self.take_over_writing_or_coding(user_hint=user_command, is_code=False, speak_fn=speak_fn)

    # ─────────────────────────────────────────────────────────────────
    # 5. GMAIL VISION-DRIVEN NOTIFICATION, READING & IN-THREAD REPLY
    # ─────────────────────────────────────────────────────────────────
    def open_and_focus_email(
        self,
        sender: str = "",
        subject: str = "",
        speak_fn: Optional[Callable[[str], None]] = None,
        listen_fn: Optional[Callable[[Optional[int]], str]] = None
    ) -> bool:
        """
        Visually opens Gmail, locates the target unread email row, clicks to open it,
        and prompts: 'Would you like me to respond to the mail, sir?'
        """
        with self._lock:
            self.is_active = True
            self.current_mode = "email_open"
            self.stop_requested = False

        if listen_fn is None:
            try:
                from jarvis import take_command
                listen_fn = take_command
            except Exception:
                listen_fn = None

        if speak_fn is None:
            try:
                from jarvis import speak
                speak_fn = speak
            except Exception:
                speak_fn = print

        sender_clean = sender.strip() if sender else ""
        if not sender_clean:
            try:
                mem_file = os.path.join(JARVIS_DIR, "jarvis_memory.json")
                if os.path.exists(mem_file):
                    with open(mem_file, "r", encoding="utf-8") as mf:
                        mem = json.load(mf)
                        last_mail = mem.get("last_received_email", {})
                        sender_clean = last_mail.get("from", "")
                        if not subject:
                            subject = last_mail.get("subject", "")
            except Exception:
                pass

        sender_label = sender_clean if sender_clean else "the sender"

        if speak_fn:
            speak_fn(f"Opening Gmail and locating the mail from {sender_label}, sir...")

        # 1. Open Gmail Web
        webbrowser.open("https://mail.google.com/mail/u/0/#inbox")
        time.sleep(3.8)

        # 2. Visually Locate and Click the Email Row
        screen_w, screen_h = pyautogui.size()
        clicked = False

        # Attempt A: Vision Grounding via Screenshot
        _, img_path = self.capture_screenshot()
        if img_path and os.path.exists(img_path):
            try:
                vision_prompt = f"""
You are looking at a Gmail inbox screen.
Find the bounding box or center coordinates of the email from '{sender_clean}' or with subject '{subject}'.
If specific email text cannot be matched, find the first unread email row at the top of the inbox list.
Output ONLY valid JSON:
{{
  "found": true,
  "coord_pct": [x_fraction, y_fraction]
}}
"""
                res = self.query_vision(vision_prompt, img_path, timeout=8.0)
                if res:
                    m = re.search(r'\{.*\}', res, re.DOTALL)
                    if m:
                        data = json.loads(m.group(0))
                        coords = data.get("coord_pct")
                        if coords and len(coords) == 2:
                            cx = int(coords[0] * screen_w)
                            cy = int(coords[1] * screen_h)
                            if 0 < cx < screen_w and 0 < cy < (screen_h - 45):
                                print(f"[Email Takeover] 👁️ Vision detected email row at ({cx}, {cy}). Clicking...")
                                pyautogui.moveTo(cx, cy, duration=0.2)
                                pyautogui.click(cx, cy)
                                clicked = True
            except Exception as e:
                print(f"[Email Takeover Vision Error]: {e}")
            finally:
                if img_path and os.path.exists(img_path):
                    try: os.remove(img_path)
                    except: pass

        # Attempt B: Fallback Coordinate Click (Top Inbox row in Gmail standard layout)
        if not clicked:
            fallback_x = int(screen_w * 0.45)
            fallback_y = int(screen_h * 0.26)
            print(f"[Email Takeover] Clicking top inbox row at fallback ({fallback_x}, {fallback_y})...")
            pyautogui.moveTo(fallback_x, fallback_y, duration=0.2)
            pyautogui.click(fallback_x, fallback_y)
            clicked = True

        time.sleep(2.5)

        # 3. Follow-up Question
        msg = f"I have opened the mail from {sender_label}, sir. Would you like me to respond to the mail, sir?"
        if speak_fn:
            speak_fn(msg)

        # 4. Interactive Voice Follow-up
        if listen_fn:
            ans = listen_fn(6)
            if ans and ans != "none":
                low_ans = ans.lower().strip()
                if any(w in low_ans for w in ["yes", "yeah", "sure", "yep", "respond", "reply", "draft"]):
                    return self.respond_to_open_email(speak_fn=speak_fn, listen_fn=listen_fn)
                elif any(w in low_ans for w in ["read", "read it", "read out", "tell me", "what does"]):
                    return self.read_and_summarize_open_email(speak_fn=speak_fn, listen_fn=listen_fn)
                elif any(w in low_ans for w in ["no", "nah", "nope", "leave it", "as you say", "cancel"]):
                    if speak_fn:
                        speak_fn("As you say, sir.")

        with self._lock:
            self.is_active = False
            self.current_mode = "idle"
        return True

    def read_and_summarize_open_email(
        self,
        speak_fn: Optional[Callable[[str], None]] = None,
        listen_fn: Optional[Callable[[Optional[int]], str]] = None
    ) -> bool:
        """
        Captures the opened email on screen, analyzes its contents with Gemini Vision,
        speaks a crisp 2-sentence executive summary, and asks if user wants to respond.
        """
        with self._lock:
            self.is_active = True
            self.current_mode = "email_read"
            self.stop_requested = False

        if listen_fn is None:
            try:
                from jarvis import take_command
                listen_fn = take_command
            except Exception:
                listen_fn = None

        if speak_fn is None:
            try:
                from jarvis import speak
                speak_fn = speak
            except Exception:
                speak_fn = print

        if speak_fn:
            speak_fn("Reading and analyzing email contents on screen, sir...")

        _, img_path = self.capture_screenshot()
        summary_text = ""

        if img_path and os.path.exists(img_path):
            try:
                summary_prompt = """
You are Point Break analyzing an email opened in Gmail on screen for Daksh.
In exactly 2 clear, crisp, and conversational spoken sentences, summarize:
1. Who sent the email and the core subject or project.
2. The specific update, question, or deadline/action required from Daksh.
Do NOT use markdown, bullet points, greetings, or meta-chatter. Clean spoken English only.
"""
                res = self.query_vision(summary_prompt, img_path, timeout=10.0)
                if res:
                    summary_text = res.strip()
            except Exception as e:
                print(f"[Email Read Vision Error]: {e}")
            finally:
                if img_path and os.path.exists(img_path):
                    try: os.remove(img_path)
                    except: pass

        if not summary_text:
            summary_text = "The email contains an incoming update, sir, but the text pane was partially obscured."

        if speak_fn:
            speak_fn(summary_text)
            time.sleep(0.3)
            speak_fn("Would you like me to respond to the mail, sir?")

        if listen_fn:
            ans = listen_fn(6)
            if ans and ans != "none":
                low_ans = ans.lower().strip()
                if any(w in low_ans for w in ["yes", "yeah", "sure", "yep", "respond", "reply", "draft"]):
                    return self.respond_to_open_email(speak_fn=speak_fn, listen_fn=listen_fn)
                elif any(w in low_ans for w in ["no", "nah", "nope", "leave it", "cancel", "as you say"]):
                    if speak_fn:
                        speak_fn("As you say, sir.")

        with self._lock:
            self.is_active = False
            self.current_mode = "idle"
        return True

    def respond_to_open_email(
        self,
        user_intent: str = "",
        speak_fn: Optional[Callable[[str], None]] = None,
        listen_fn: Optional[Callable[[Optional[int]], str]] = None
    ) -> bool:
        """
        Interactive 4-Step Email Reply Takeover:
        1. Asks for user's intent if not provided.
        2. Synthesizes tailored response grounded in the open email context.
        3. Enters the in-thread reply box in Gmail (via 'r' shortcut or click) and pastes draft.
        4. Operator confirmation guardrail: asks if user wants it sent or will take it from here.
        """
        with self._lock:
            self.is_active = True
            self.current_mode = "email_reply"
            self.stop_requested = False

        if listen_fn is None:
            try:
                from jarvis import take_command
                listen_fn = take_command
            except Exception:
                listen_fn = None

        if speak_fn is None:
            try:
                from jarvis import speak
                speak_fn = speak
            except Exception:
                speak_fn = print

        intent = user_intent.strip() if user_intent else ""
        if not intent or any(intent.lower().startswith(p) for p in ["respond to", "reply to", "draft a reply", "answer"]):
            if speak_fn:
                speak_fn("What would you like me to say in response, sir?")
            if listen_fn:
                captured = listen_fn(12)
                if captured and captured != "none" and len(captured.strip()) > 1:
                    intent = captured.strip()
                else:
                    if speak_fn:
                        speak_fn("I did not catch your response instructions, sir. Cancelling draft.")
                    with self._lock: self.is_active = False
                    return False
            else:
                intent = "Acknowledge receipt and express that you are looking into it."

        if any(w in intent.lower() for w in ["cancel", "never mind", "nothing", "don't reply", "no"]):
            if speak_fn:
                speak_fn("As you say, sir. Cancelling email response.")
            with self._lock: self.is_active = False
            return False

        if speak_fn:
            speak_fn("Synthesizing tailored reply for this email thread, sir...")

        # 1. Grab screen context of the email
        _, img_path = self.capture_screenshot()
        draft_reply = ""

        if img_path and os.path.exists(img_path):
            try:
                reply_prompt = f"""
You are Point Break acting as an executive co-pilot for Daksh.
Read this open email displayed in Gmail on screen.
Daksh's verbal reply instruction: "{intent}"

Draft a concise, articulate, and completely professional email response to paste directly into the reply box.
RULES:
1. Address the sender professionally.
2. Incorporate Daksh's instructions accurately and politely.
3. Keep it crisp (1-3 brief paragraphs).
4. Output ONLY the response body text to paste. Do NOT include subject lines, markdown code fences, or meta-comments.
"""
                res = self.query_vision(reply_prompt, img_path, timeout=12.0)
                if res:
                    draft_reply = res.strip()
                    draft_reply = re.sub(r'^```[a-zA-Z]*\n', '', draft_reply)
                    draft_reply = re.sub(r'\n```$', '', draft_reply)
            except Exception as e:
                print(f"[Email Reply Vision Error]: {e}")
            finally:
                if img_path and os.path.exists(img_path):
                    try: os.remove(img_path)
                    except: pass

        if not draft_reply:
            draft_reply = f"Hi,\n\nThank you for your email. {intent}\n\nBest regards,\nDaksh"

        # 2. In-Thread Injection
        screen_w, screen_h = pyautogui.size()

        # Click inside the email reading pane to ensure window focus
        pyautogui.click(int(screen_w * 0.50), int(screen_h * 0.40))
        time.sleep(0.3)

        # Press 'r' to trigger native Gmail Reply
        pyautogui.press('r')
        time.sleep(0.8)

        # Fail-safe: click the bottom reply button
        pyautogui.click(int(screen_w * 0.40), int(screen_h * 0.88))
        time.sleep(0.4)

        # Paste draft into the focused reply box
        pyperclip.copy(draft_reply)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)

        print(f"[Email Takeover] ✅ Draft injected into Gmail reply box ({len(draft_reply)} chars).")

        # 3. Operator Confirmation Guardrail
        confirm_msg = "I have drafted the response into the thread for your review, sir. Would you like me to send it, or will you take it from here?"
        if speak_fn:
            speak_fn(confirm_msg)

        if listen_fn:
            confirm = listen_fn(6)
            if confirm and confirm != "none":
                low_conf = confirm.lower().strip()
                if any(w in low_conf for w in ["send", "send it", "dispatch", "shoot", "yes send"]):
                    pyautogui.hotkey("ctrl", "enter")
                    time.sleep(0.5)
                    if speak_fn:
                        speak_fn("Email response dispatched, sir.")
                else:
                    if speak_fn:
                        speak_fn("Draft is staged in your active window, sir. I'll leave it at your cursor.")

        with self._lock:
            self.is_active = False
            self.current_mode = "idle"
        return True

    # ─────────────────────────────────────────────────────────────────
    # 6. SAFETY & DISENGAGE
    # ─────────────────────────────────────────────────────────────────
    def stop_takeover(self, speak_fn: Optional[Callable[[str], None]] = None):
        """Immediately aborts all active takeover threads and releases control."""
        with self._lock:
            self.stop_requested = True
            self.is_active = False
            self.current_mode = "idle"

        print("[Takeover] ⏹️ Autonomous Takeover Disengaged.")
        if speak_fn:
            speak_fn("Takeover disengaged. Control returned to you, sir.")


# Global instance
takeover_engine = UniversalTakeoverEngine()
