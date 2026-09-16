"""
Point Break — Two-Way Phone Media & Screenshot Engine
======================================================
1. Capture phone screen directly to PC Desktop and pass to Vision AI.
2. Push PC desktop snapshots directly to Phone Gallery / Photos.
"""

import os
import time
import datetime
import subprocess
from pathlib import Path
from phone_bridge import phone_bridge

class PhoneMediaEngine:
    def __init__(self):
        self.user_desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(self.user_desktop, exist_ok=True)

    def capture_phone_screen(self, custom_save_path: str = None) -> str:
        """Saves high-res phone screen to Desktop and returns path."""
        dev = phone_bridge.get_device_id()
        if not dev:
            return None

        remote_temp = "/sdcard/Download/pb_screen_temp.png"
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = custom_save_path or os.path.join(self.user_desktop, f"Phone_Screenshot_{ts}.png")

        # 1. Take screencap on device
        code, _, _ = phone_bridge._run_adb(["-s", dev, "shell", "screencap", "-p", remote_temp], timeout=8)
        if code != 0:
            return None

        # 2. Pull to PC
        code_pull, _, _ = phone_bridge._run_adb(["-s", dev, "pull", remote_temp, local_path], timeout=8)
        if code_pull == 0 and os.path.exists(local_path):
            # Clean remote temp
            phone_bridge._run_adb(["-s", dev, "shell", "rm", "-f", remote_temp], timeout=3)
            return local_path

        return None

    def push_screenshot_to_phone(self, local_filepath: str = None) -> bool:
        """Pushes a local screenshot / image directly to Phone Pictures/PointBreak and notifies Gallery."""
        dev = phone_bridge.get_device_id()
        if not dev:
            return False

        # If no file provided, capture PC desktop screenshot now
        temp_created = False
        if not local_filepath or not os.path.exists(local_filepath):
            import pyautogui
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            local_filepath = os.path.join(self.user_desktop, f"PC_Snapshot_{ts}.png")
            img = pyautogui.screenshot()
            img.save(local_filepath)
            temp_created = True

        filename = os.path.basename(local_filepath)
        remote_dir = "/sdcard/Pictures/PointBreak"
        remote_path = f"{remote_dir}/{filename}"

        # Ensure directory exists
        phone_bridge._run_adb(["-s", dev, "shell", "mkdir", "-p", remote_dir], timeout=4)

        # Push file
        code_push, _, _ = phone_bridge._run_adb(["-s", dev, "push", local_filepath, remote_path], timeout=8)
        if code_push != 0:
            return False

        # Trigger Android Media Scanner Broadcast
        phone_bridge._run_adb([
            "-s", dev, "shell", "am", "broadcast",
            "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d", f"file://{remote_path}"
        ], timeout=5)

        return True

phone_media = PhoneMediaEngine()
