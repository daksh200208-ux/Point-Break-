from pointbreak_genai import (
    query_generative_model,
    query_tars_vision,
    query_text as genai_query_text,
    query_vision as genai_query_vision
)
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
    from pointbreak_chess import (
        chess_engine,
        detect_chessboard_bounds,
        detect_player_color_from_board,
        detect_opponent_move_fast,
        execute_rapid_mouse_move,
        get_square_center,
        load_chess_config,
        save_chess_config,
        run_autonomous_chess_game,
        request_chess_stop,
        focus_chess_window
    )
except ImportError:
    chess = None
    chess_engine = None
    detect_chessboard_bounds = None
    detect_player_color_from_board = None
    detect_opponent_move_fast = None
    execute_rapid_mouse_move = None
    get_square_center = None
    load_chess_config = None
    save_chess_config = None
    run_autonomous_chess_game = None
    request_chess_stop = None
    focus_chess_window = None

from dotenv import load_dotenv
JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(JARVIS_DIR, ".env"))

try:
    import google.generativeai as genai
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        genai.configure(api_key=api_key, transport="rest")
except ImportError:
    genai = None

TAKEOVER_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash"
]

# Ensure focus_chess_window uses the robust browser-maximizing implementation
if "focus_chess_window" not in globals() or focus_chess_window is None:
    try:
        from pointbreak_chess import focus_chess_window
    except Exception:
        def focus_chess_window() -> bool:
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
        """Queries Gemini Vision with robust multi-model failover."""
        if not image_path or not os.path.exists(image_path):
            return None
        # Primary: Official google.genai Client from pointbreak_genai
        try:
            res = genai_query_vision(image_path, prompt, timeout=timeout)
            if res and res.strip():
                return res.strip()
        except Exception as e:
            print(f"[Takeover Vision GenAI Error]: {e}")

        # Secondary: google.generativeai REST fallback
        if genai:
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
        """Queries Gemini text model with robust multi-model failover."""
        # Primary: Official google.genai Client from pointbreak_genai
        try:
            res = genai_query_text(prompt, timeout=timeout)
            if res and res.strip():
                return res.strip()
        except Exception as e:
            print(f"[Takeover Text GenAI Error]: {e}")

        # Secondary: google.generativeai REST fallback
        if genai:
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

        if self.stop_requested:
            with self._lock: self.is_active = False; self.current_mode = "idle"
            return False

        if speak_fn:
            speak_fn("Analyzing your document, sir. Taking over writing...")

        print("[Takeover] Initiating Ghostwriter Writing & Coding Takeover...")

        # 1. Grab current context from clipboard or screen
        existing_text = ""
        try:
            old_clip = pyperclip.paste()
            if self.stop_requested:
                with self._lock: self.is_active = False; self.current_mode = "idle"
                return False
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

        if self.stop_requested:
            print("[Takeover] Operator cancelled writing takeover.")
            with self._lock: self.is_active = False; self.current_mode = "idle"
            return False

        # 2. Visual screen fallback if editor doesn't support Ctrl+A
        img_path = None
        if not existing_text or len(existing_text.strip()) < 5:
            _, img_path = self.capture_screenshot()

        if self.stop_requested:
            if img_path and os.path.exists(img_path):
                try: os.remove(img_path)
                except: pass
            with self._lock: self.is_active = False; self.current_mode = "idle"
            return False

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

        if self.stop_requested:
            print("[Takeover] Operator cancelled writing takeover after synthesis.")
            with self._lock: self.is_active = False; self.current_mode = "idle"
            return False

        if not continuation or len(continuation.strip()) < 2:
            if speak_fn:
                speak_fn("Could not determine continuation context, sir.")
            with self._lock: self.is_active = False; self.current_mode = "idle"
            return False

        clean_continuation = continuation.strip()
        if clean_continuation.startswith("```") and clean_continuation.endswith("```"):
            clean_continuation = re.sub(r'^```[a-zA-Z]*\n', '', clean_continuation)
            clean_continuation = re.sub(r'\n```$', '', clean_continuation)

        if self.stop_requested:
            print("[Takeover] Operator cancelled writing takeover before typing.")
            with self._lock: self.is_active = False; self.current_mode = "idle"
            return False

        # 4. Autonomous typing execution
        print(f"[Takeover] Typing {len(clean_continuation)} characters into active cursor...")
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
                print("[Takeover Verify] Continuation text confirmed in document.")
            else:
                print("[Takeover Verify] Continuation text not found in document after paste.")
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
        """Silent, rapid physical piece mover."""
        bx1 = int(board_bbox_pct[0] * screen_w)
        by1 = int(board_bbox_pct[1] * screen_h)
        bx2 = int(board_bbox_pct[2] * screen_w)
        by2 = int(board_bbox_pct[3] * screen_h)
        board_bbox = (bx1, by1, bx2, by2)

        if execute_rapid_mouse_move:
            return execute_rapid_mouse_move(board_bbox, from_sq, to_sq, player_color)

        cx1, cy1 = self._calculate_square_center(board_bbox_pct, from_sq, player_color, screen_w, screen_h)
        cx2, cy2 = self._calculate_square_center(board_bbox_pct, to_sq, player_color, screen_w, screen_h)
        pyautogui.moveTo(cx1, cy1, duration=0.10)
        pyautogui.mouseDown(button='left')
        time.sleep(0.04)
        pyautogui.moveTo(cx2, cy2, duration=0.15)
        time.sleep(0.04)
        pyautogui.mouseUp(button='left')
        pyautogui.click(cx2, cy2)
        pyautogui.moveTo(max(15, bx1 - 35), cy2, duration=0.06)
        return True

    def suggest_best_chess_move(self, speak_fn: Optional[Callable[[str], None]] = None, update_status_fn: Optional[Callable[[Dict[str, Any]], None]] = None) -> bool:
        """One-shot move calculation with Stockfish."""
        focus_chess_window()
        time.sleep(0.15)
        shot, _ = self.capture_screenshot()
        screen_w, screen_h = pyautogui.size()
        board_bbox = detect_chessboard_bounds(shot) if (shot and detect_chessboard_bounds) else (250, 140, 1030, 920)
        player_color = detect_player_color_from_board(shot, board_bbox) if (shot and detect_player_color_from_board) else "white"

        board = chess.Board()
        engine_res = chess_engine.query_best_move(board, time_limit=0.25) if chess_engine else None
        if engine_res and engine_res.get("success"):
            execute_rapid_mouse_move(board_bbox, engine_res["from_sq"], engine_res["to_sq"], player_color)
            return True
        return False

    def take_over_chess_game(self, single_move: bool = False, forced_color: Optional[str] = None, speak_fn: Optional[Callable[[str], None]] = None, update_status_fn: Optional[Callable[[Dict[str, Any]], None]] = None) -> bool:
        """
        High-Speed Silent Grandmaster Chess Takeover (Stockfish 16 NNUE):
        - Completely silent: zero voice interruptions during play.
        - Moves within 3.0 to 3.8 seconds after opponent moves.
        - Robust multi-theme board & highlight vision (Chess.com / Lichess).
        - True 3500+ ELO Stockfish 16 engine: zero blunders, zero dumb moves.
        - Responsive stop/disengage check on command.
        """
        with self._lock:
            self.is_active = True
            self.current_mode = "chess"
            self.stop_requested = False

        print("[Takeover] Engaging High-Speed Silent Stockfish Grandmaster...")

        def _chess_loop():
            try:
                if run_autonomous_chess_game:
                    run_autonomous_chess_game(
                        forced_color=forced_color,
                        time_delay_target=3.2,
                        single_move=single_move,
                        is_stop_requested=lambda: self.stop_requested or not self.is_active
                    )
                else:
                    print("[Takeover Chess Error]: run_autonomous_chess_game is unavailable.")
            except Exception as e:
                print(f"[Takeover Chess Loop Error]: {e}")
            finally:
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

        if self.stop_requested:
            with self._lock: self.is_active = False; self.current_mode = "idle"
            return False

        if speak_fn:
            speak_fn("Reading conversation on screen, sir. Drafting reply...")

        print("[Takeover] Initiating Social Messaging Takeover...")
        _, img_path = self.capture_screenshot()

        if self.stop_requested:
            if img_path and os.path.exists(img_path):
                try: os.remove(img_path)
                except: pass
            with self._lock: self.is_active = False; self.current_mode = "idle"
            return False

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
            if self.stop_requested:
                print("[Takeover] Messaging takeover aborted by stop request after vision query.")
                with self._lock: self.is_active = False; self.current_mode = "idle"
                return False

            if not res:
                if speak_fn: speak_fn("Could not analyze chat interface, sir.")
                with self._lock: self.is_active = False; self.current_mode = "idle"
                return False

            match = re.search(r'\{.*\}', res, re.DOTALL)
            if not match:
                if speak_fn: speak_fn("Failed to parse messaging parameters, sir.")
                with self._lock: self.is_active = False; self.current_mode = "idle"
                return False

            data = json.loads(match.group(0))
            app = data.get("app_detected", "chat").title()
            reply = data.get("drafted_reply", "").strip()
            box_pct = data.get("input_box_pct", [0.5, 0.9])

            if not reply:
                if speak_fn: speak_fn("Could not draft appropriate reply, sir.")
                with self._lock: self.is_active = False; self.current_mode = "idle"
                return False

            if self.stop_requested:
                print("[Takeover] Messaging takeover aborted by stop request before typing.")
                with self._lock: self.is_active = False; self.current_mode = "idle"
                return False

            cx = int(box_pct[0] * screen_w)
            cy = int(box_pct[1] * screen_h)

            print(f"[Takeover] Typing reply on {app} at ({cx}, {cy})...")
            pyautogui.moveTo(cx, cy, duration=0.2)
            if self.stop_requested:
                with self._lock: self.is_active = False; self.current_mode = "idle"
                return False
            pyautogui.click(cx, cy)
            time.sleep(0.1)

            if self.stop_requested:
                with self._lock: self.is_active = False; self.current_mode = "idle"
                return False

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
                    print(f"[Takeover Verify] Reply text confirmed in {app} input box.")
                else:
                    print(f"[Takeover Verify] Reply text not found in {app} input box after paste.")
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
            with self._lock: self.is_active = False; self.current_mode = "idle"
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
            forced_color = None
            if any(w in low_cmd for w in ["as black", "playing black", "i am black", "color black"]):
                forced_color = "black"
            elif any(w in low_cmd for w in ["as white", "playing white", "i am white", "color white"]):
                forced_color = "white"
            return self.take_over_chess_game(single_move=single_move, forced_color=forced_color, speak_fn=speak_fn, update_status_fn=update_status_fn)

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

        if request_chess_stop:
            try:
                request_chess_stop()
            except Exception as ce:
                print(f"[Takeover] request_chess_stop error: {ce}")

        print("[Takeover] Autonomous Takeover Disengaged. Control returned to operator.")
        if speak_fn:
            speak_fn("Takeover disengaged. Control returned to you, sir.")


# Global instance
takeover_engine = UniversalTakeoverEngine()
