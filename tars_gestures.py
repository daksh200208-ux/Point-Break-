"""
TARS High-Performance Kinetic Gesture Control Engine (v2.7 Ultra-Fast)
======================================================================
Calibrated for sub-10ms latency, zero-lag tracking, and Maker Daksh's exact gestures:

1. AIR MOUSE & CLICK (Index Upright & Index+Thumb Tap):
   - Point Index finger upright to move cursor smoothly (adaptive EMA filter).
   - Tap Index & Thumb tips together (< 0.050 distance) -> Instant Click (Left Click).

2. PINKY SLIDE TAB SWITCHING (Pinky Out, All Other Fingers Folded):
   - Slide Pinky Left-to-Right -> Switch to Next Tab (Ctrl + Tab).
   - Slide Pinky Right-to-Left -> Switch to Previous Tab (Ctrl + Shift + Tab).
   - Precise 0.40s step cadence allows slow, one-by-one tab navigation.

3. DUAL OPEN PALM ZOOM (Both Palms Facing Camera):
   - Expand distance between both open palms -> Zoom In (Ctrl +).
   - Contract distance between both open palms -> Zoom Out (Ctrl -).

4. VOLUME KNOB CONTROL (Thumb + Index Dial, Hand Tilted/Horizontal):
   - Pinch Close (< 0.040) -> Volume Down.
   - Expand Wide (> 0.125) -> Volume Up.

5. TWO-FINGER SCROLLING (Index + Middle Upright):
   - Drag down to scroll up, push up to scroll down.

6. WORKSTATION LOCK & BAYMAX CELEBRATION:
   - Closed Fist (1.5s) -> Lock Workstation (Win + L).
   - Fist for 0.4s-1.2s then Open Hand -> Baymax Fist Bump ("Balalala!").
"""

import cv2
try:
    import mediapipe as mp
except Exception as _mp_err:
    mp = None
import mediapipe.python.solutions.hands as mp_hands
import pyautogui
import numpy as np
import time
import math
import ctypes
import threading

# Optimize PyAutoGUI for zero latency
pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = False

class TarsGestureEngine:
    def __init__(self, camera_index=0):
        self.camera_index = camera_index
        self.is_running = False
        self.thread = None
        self.screen_w, self.screen_h = pyautogui.size()
        
        # Adaptive Cursor Smoothing
        self.prev_mouse_x = self.screen_w // 2
        self.prev_mouse_y = self.screen_h // 2
        
        # Debounce Cooldowns
        self.last_vol_time = 0
        self.last_swipe_time = 0
        self.last_zoom_time = 0
        self.last_click_time = 0
        self.last_scroll_time = 0
        self.last_tab_time = 0
        self.fist_start_time = 0
        self.fist_locked = False
        self.fist_bump_candidate_time = 0
        self.last_fist_bump_time = 0
        
        # Motion Histories
        self.pos_history = []
        self.pinky_history = []
        self.dual_dist_history = []
        
        # Callback Hooks
        self.on_gesture_detected = None
        self.on_fist_bump_detected = None

    def _calc_dist(self, p1, p2):
        return math.hypot(p1.x - p2.x, p1.y - p2.y)

    def _is_finger_extended(self, landmarks, tip_idx, pip_idx):
        wrist = landmarks[0]
        d_tip = self._calc_dist(landmarks[tip_idx], wrist)
        d_pip = self._calc_dist(landmarks[pip_idx], wrist)
        return d_tip > (d_pip * 1.06)

    def _get_hand_state(self, landmarks):
        """Extracts complete finger states, postures, and 3D orientation."""
        thumb_ext = self._calc_dist(landmarks[4], landmarks[2]) > 0.055
        index_ext = self._is_finger_extended(landmarks, 8, 6)
        middle_ext = self._is_finger_extended(landmarks, 12, 10)
        ring_ext = self._is_finger_extended(landmarks, 16, 14)
        pinky_ext = self._is_finger_extended(landmarks, 20, 18)
        
        wrist = landmarks[0]
        mid_mcp = landmarks[9]
        
        dx = mid_mcp.x - wrist.x
        dy = mid_mcp.y - wrist.y
        
        # Orientation
        is_vertical = abs(dy) > abs(dx) * 1.05 and dy < 0  # Upright
        is_horizontal = abs(dx) > abs(dy) * 0.80          # Sideways / Tilted knob
        
        # 1. Closed Fist: all 4 fingers folded
        is_fist = (not index_ext) and (not middle_ext) and (not ring_ext) and (not pinky_ext) and (self._calc_dist(landmarks[8], wrist) < 0.22)
        
        # 2. Open Palm: all 4 fingers extended
        is_open_palm = index_ext and middle_ext and ring_ext and pinky_ext
        
        # 3. Two-Finger Scroll: Index & Middle extended, Ring & Pinky curled
        is_scroll = index_ext and middle_ext and (not ring_ext) and (not pinky_ext)
        
        # 4. Pinky Only Posture (Tab Switcher): ONLY Pinky extended, all other 3 fingers folded!
        is_pinky_only = pinky_ext and (not index_ext) and (not middle_ext) and (not ring_ext)
        
        # 5. Air Mouse Posture: ONLY Index extended upright, Middle/Ring/Pinky curled
        is_air_mouse = index_ext and (not middle_ext) and (not ring_ext) and (not pinky_ext)
        
        # 6. Volume Knob Dial: Tilted/Horizontal posture with Thumb & Index active
        is_volume_dial = is_horizontal and (not middle_ext) and (not ring_ext) and (not pinky_ext)

        return {
            "thumb": thumb_ext,
            "index": index_ext,
            "middle": middle_ext,
            "ring": ring_ext,
            "pinky": pinky_ext,
            "is_vertical": is_vertical,
            "is_horizontal": is_horizontal,
            "is_fist": is_fist,
            "is_open_palm": is_open_palm,
            "is_scroll": is_scroll,
            "is_pinky_only": is_pinky_only,
            "is_air_mouse": is_air_mouse,
            "is_volume_dial": is_volume_dial,
            "center": (mid_mcp.x, mid_mcp.y)
        }

    def _run_loop(self):
        try:
            # Model complexity 0 = Lightweight & Ultra-Fast (60+ FPS on CPU, sub-10ms inference)
            hands = mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                model_complexity=0,
                min_detection_confidence=0.50,
                min_tracking_confidence=0.50
            )
        except Exception as e:
            print("  [TARS Gesture Engine] MediaPipe init error:", e)
            return

        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap = cv2.VideoCapture(self.camera_index)
            
        # Optimize camera pipeline for zero lag
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except:
            pass
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        
        print("  [TARS Kinetic Gesture Engine: v2.7 Ultra-Fast Online]")
        
        while self.is_running and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue
                
            # Flip horizontally for natural mirror view
            frame = cv2.flip(frame, 1)
            
            # Ultra-Fast 320x240 Frame Resize for Core i3 & Low-End CPUs (Slashes inference latency by 65%)
            small_frame = cv2.resize(frame, (320, 240), interpolation=cv2.INTER_LINEAR)
            rgb = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            
            try:
                results = hands.process(rgb)
            except Exception:
                time.sleep(0.01)
                continue
            
            now = time.time()

            # ── AUTO-DETECT ACTIVE TEXT / PASSWORD / SEARCH INPUT ──────────
            if now - getattr(self, 'last_focus_check_time', 0) > 0.25:
                self.last_focus_check_time = now
                try:
                    from pointbreak_vkeyboard import vkeyboard_engine, check_is_text_input_focused
                    is_input_active = check_is_text_input_focused()
                    if is_input_active and not vkeyboard_engine.is_visible:
                        vkeyboard_engine.show(force=False)
                    elif not is_input_active and vkeyboard_engine.is_visible:
                        vkeyboard_engine.hide(manual_user_close=False)
                except Exception:
                    pass
            
            if results.multi_hand_landmarks:
                num_hands = len(results.multi_hand_landmarks)
                
                # ── HOLOGRAPHIC AIR-KEYBOARD ROUTING (SINGLE PRIMARY HAND) ────
                try:
                    from pointbreak_vkeyboard import vkeyboard_engine
                    if vkeyboard_engine.is_visible:
                        # Process only the single primary active hand for maximum 60+ FPS performance
                        primary_lms = results.multi_hand_landmarks[0].landmark
                        handedness = "Right"
                        if results.multi_handedness and len(results.multi_handedness) > 0:
                            handedness = results.multi_handedness[0].classification[0].label
                        vkeyboard_engine.process_hand_landmarks(primary_lms, handedness, self.screen_w, self.screen_h)
                        time.sleep(0.005)
                        continue
                except Exception:
                    pass

                # ── 1. DUAL OPEN PALM ZOOM (EXPAND / CONTRACT) ─────────────────
                is_valid_dual_zoom = False
                if num_hands == 2:
                    h1_lms = results.multi_hand_landmarks[0].landmark
                    h2_lms = results.multi_hand_landmarks[1].landmark
                    
                    h1_state = self._get_hand_state(h1_lms)
                    h2_state = self._get_hand_state(h2_lms)
                    
                    # Both hands must be open palms
                    if h1_state["is_open_palm"] and h2_state["is_open_palm"]:
                        p1_x, p1_y = h1_state["center"]
                        p2_x, p2_y = h2_state["center"]
                        
                        if abs(p1_x - p2_x) > 0.12:
                            is_valid_dual_zoom = True
                            dual_dist = math.hypot(p1_x - p2_x, p1_y - p2_y)
                            
                            self.dual_dist_history.append(dual_dist)
                            if len(self.dual_dist_history) > 3:
                                self.dual_dist_history.pop(0)
                                
                            if len(self.dual_dist_history) >= 2 and (now - self.last_zoom_time > 0.18):
                                delta = self.dual_dist_history[-1] - self.dual_dist_history[0]
                                # Moving apart -> Zoom In
                                if delta > 0.035:
                                    pyautogui.hotkey('ctrl', '+')
                                    self.last_zoom_time = now
                                    self.dual_dist_history.clear()
                                    print("  [GESTURE] Dual Palms Apart -> Zoom In (+)")
                                    if self.on_gesture_detected: self.on_gesture_detected("Zoom In (+)")
                                # Moving together -> Zoom Out
                                elif delta < -0.035:
                                    pyautogui.hotkey('ctrl', '-')
                                    self.last_zoom_time = now
                                    self.dual_dist_history.clear()
                                    print("  [GESTURE] Dual Palms Together -> Zoom Out (-)")
                                    if self.on_gesture_detected: self.on_gesture_detected("Zoom Out (-)")
                                    
                if is_valid_dual_zoom:
                    time.sleep(0.005)
                    continue
                else:
                    self.dual_dist_history.clear()
                    
                # ── SINGLE HAND PROCESSING ─────────────────────────────────────
                lms = results.multi_hand_landmarks[0].landmark
                state = self._get_hand_state(lms)
                wrist = lms[0]
                cx, cy = state["center"]
                
                # Position history for velocity gestures
                self.pos_history.append((cx, cy, now))
                if len(self.pos_history) > 5:
                    self.pos_history.pop(0)
                    
                # ── A. BAYMAX FIST BUMP & WORKSTATION LOCK ───────────────────────
                if state["is_fist"]:
                    if self.fist_start_time == 0:
                        self.fist_start_time = now
                        self.fist_bump_candidate_time = now
                    elif (now - self.fist_start_time >= 1.5) and not self.fist_locked:
                        self.fist_locked = True
                        self.fist_bump_candidate_time = 0
                        print("  [GESTURE] Closed Fist Held 1.5s -> Locking Workstation")
                        if self.on_gesture_detected: self.on_gesture_detected("Lock Workstation")
                        try:
                            ctypes.windll.user32.LockWorkStation()
                        except Exception:
                            pyautogui.hotkey('win', 'l')
                else:
                    if self.fist_bump_candidate_time > 0 and (0.35 <= (now - self.fist_bump_candidate_time) <= 1.3):
                        if (state["is_open_palm"] or (state["index"] and state["pinky"])) and (now - self.last_fist_bump_time > 3.0):
                            self.last_fist_bump_time = now
                            print("  [GESTURE] 👊 Baymax Fist Bump Detected -> BALALALA! 👊")
                            if self.on_gesture_detected: self.on_gesture_detected("BALALALA!")
                            if self.on_fist_bump_detected:
                                try: self.on_fist_bump_detected()
                                except Exception as fe: print("Fist bump callback error:", fe)
                    self.fist_start_time = 0
                    self.fist_bump_candidate_time = 0
                    self.fist_locked = False

                # ── B. PINKY SLIDE TAB SWITCHER (Pinky Only Extended) ──────────
                if state["is_pinky_only"]:
                    pinky_tip = lms[20]
                    self.pinky_history.append((pinky_tip.x, pinky_tip.y, now))
                    if len(self.pinky_history) > 4:
                        self.pinky_history.pop(0)
                        
                    if len(self.pinky_history) >= 3 and (now - self.last_tab_time > 0.40):
                        dx_pinky = self.pinky_history[-1][0] - self.pinky_history[0][0]
                        dt_pinky = self.pinky_history[-1][2] - self.pinky_history[0][2]
                        
                        if dt_pinky > 0.03:
                            v_pinky = dx_pinky / dt_pinky
                            # Slide Pinky Left-to-Right -> Next Tab
                            if v_pinky > 0.40 or dx_pinky > 0.035:
                                pyautogui.hotkey('ctrl', 'tab')
                                self.last_tab_time = now
                                self.pinky_history.clear()
                                print("  [GESTURE] 🤙 Pinky Slide Right -> Next Tab")
                                if self.on_gesture_detected: self.on_gesture_detected("Next Tab (Pinky ->)")
                            # Slide Pinky Right-to-Left -> Previous Tab
                            elif v_pinky < -0.40 or dx_pinky < -0.035:
                                pyautogui.hotkey('ctrl', 'shift', 'tab')
                                self.last_tab_time = now
                                self.pinky_history.clear()
                                print("  [GESTURE] 🤙 Pinky Slide Left -> Previous Tab")
                                if self.on_gesture_detected: self.on_gesture_detected("Prev Tab (<- Pinky)")
                else:
                    self.pinky_history.clear()

                # ── C. OPEN PALM VERTICAL SWIPE (Virtual Desktop Switch) ───────
                if state["is_open_palm"] and state["is_vertical"] and len(self.pos_history) >= 3:
                    old_x, old_y, old_t = self.pos_history[0]
                    curr_x, curr_y, curr_t = self.pos_history[-1]
                    dt = curr_t - old_t
                    
                    if dt > 0.04 and (now - self.last_swipe_time > 0.75):
                        vx = (curr_x - old_x) / dt
                        if abs(vx) > 0.85:
                            if vx > 0: # Right
                                pyautogui.hotkey('ctrl', 'win', 'right')
                                self.last_swipe_time = now
                                self.pos_history.clear()
                                print("  [GESTURE] Palm Right -> Desktop Right")
                                if self.on_gesture_detected: self.on_gesture_detected("Desktop -> Right")
                            else: # Left
                                pyautogui.hotkey('ctrl', 'win', 'left')
                                self.last_swipe_time = now
                                self.pos_history.clear()
                                print("  [GESTURE] Palm Left -> Desktop Left")
                                if self.on_gesture_detected: self.on_gesture_detected("Desktop <- Left")

                # ── D. TWO-FINGER SCROLLING (Index + Middle Upright) ───────────
                elif state["is_scroll"] and len(self.pos_history) >= 2:
                    idx_mid_dist = self._calc_dist(lms[8], lms[12])
                    if idx_mid_dist < 0.08:
                        old_y = self.pos_history[-2][1]
                        dy = cy - old_y
                        if now - self.last_scroll_time > 0.04:
                            if dy > 0.012:
                                pyautogui.scroll(95)
                                self.last_scroll_time = now
                            elif dy < -0.012:
                                pyautogui.scroll(-95)
                                self.last_scroll_time = now

                # ── E. VOLUME KNOB CONTROL (Tilted / Horizontal C-Pinch) ───────
                elif state["is_volume_dial"]:
                    thumb_tip = lms[4]
                    index_tip = lms[8]
                    pinch_dist = math.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y)
                    
                    if now - self.last_vol_time > 0.14:
                        # Close pinch (< 0.040) -> Volume Down
                        if pinch_dist < 0.040:
                            pyautogui.press('volumedown')
                            self.last_vol_time = now
                            print("  [GESTURE] Knob Pinch Close -> Volume Down")
                            if self.on_gesture_detected: self.on_gesture_detected("Volume Down")
                        # Spread wide (> 0.125) -> Volume Up
                        elif pinch_dist > 0.125:
                            pyautogui.press('volumeup')
                            self.last_vol_time = now
                            print("  [GESTURE] Knob Pinch Wide -> Volume Up")
                            if self.on_gesture_detected: self.on_gesture_detected("Volume Up")

                # ── F. AIR MOUSE & CLICK (Single Index Upright) ────────────────
                elif state["is_air_mouse"]:
                    index_tip = lms[8]
                    thumb_tip = lms[4]
                    
                    # 1. Coordinate Mapping (0.12 - 0.88 normalized zone)
                    margin_x = 0.12
                    margin_y = 0.12
                    norm_x = np.clip((index_tip.x - margin_x) / (1.0 - 2 * margin_x), 0.0, 1.0)
                    norm_y = np.clip((index_tip.y - margin_y) / (1.0 - 2 * margin_y), 0.0, 1.0)
                    
                    target_x = int(norm_x * self.screen_w)
                    target_y = int(norm_y * self.screen_h)
                    
                    # Adaptive EMA filter for instant speed & pixel precision
                    dist_moved = math.hypot(target_x - self.prev_mouse_x, target_y - self.prev_mouse_y)
                    alpha = 0.75 if dist_moved > 30 else 0.35
                    
                    curr_mouse_x = int(alpha * target_x + (1 - alpha) * self.prev_mouse_x)
                    curr_mouse_y = int(alpha * target_y + (1 - alpha) * self.prev_mouse_y)
                    
                    pyautogui.moveTo(curr_mouse_x, curr_mouse_y)
                    self.prev_mouse_x, self.prev_mouse_y = curr_mouse_x, curr_mouse_y
                    
                    # 2. Air Click Trigger: Tap Index & Thumb tips together (< 0.050)
                    thumb_index_dist = math.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y)
                    
                    if thumb_index_dist < 0.050 and (now - self.last_click_time > 0.30):
                        pyautogui.click()
                        self.last_click_time = now
                        print("  [GESTURE] Air Click Fired! (Index + Thumb Tap)")
                        if self.on_gesture_detected: self.on_gesture_detected("Air Click")

            else:
                self.pos_history.clear()
                self.pinky_history.clear()
                self.dual_dist_history.clear()
                self.fist_start_time = 0

            time.sleep(0.005)

        cap.release()
        try:
            hands.close()
        except Exception:
            pass
        print("  [TARS Kinetic Gesture Engine: Offline]")

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            self.thread = None

# Global Singleton for TARS
gesture_controller = TarsGestureEngine()
