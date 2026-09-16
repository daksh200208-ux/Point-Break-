"""
Point Break 3.0 — Phone Hub 2.0 & Mobile Ecosystem Bridge
=========================================================
1. Wireless ADB Auto-Discovery & Reconnect.
2. Phone Screen Capture & Snapshot Mirroring.
3. Cross-Device Clipboard Synchronization (Android <-> Windows).
4. Direct Mobile SMS & App Automation.
"""

import os
import sys
import subprocess
import time
import threading
from typing import List, Dict, Any, Optional, Tuple

JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
ADB_PATH = os.path.join(JARVIS_DIR, "adb.exe")
if not os.path.exists(ADB_PATH):
    ADB_PATH = "adb"

class PhoneHub2:
    def __init__(self):
        self.connected_device = None
        self.is_clipboard_sync_active = False
        self._last_synced_clipboard = ""
        self._lock = threading.Lock()

    def run_adb(self, args: List[str]) -> Tuple[int, str]:
        """Runs an ADB command and returns (returncode, output)."""
        cmd = [ADB_PATH] + args
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            return res.returncode, res.stdout.strip()
        except Exception as e:
            return -1, str(e)

    def discover_and_connect_device(self, ip_port: Optional[str] = None) -> bool:
        """
        Discovers connected USB/Wireless devices or connects to specific IP:port.
        """
        if ip_port:
            code, out = self.run_adb(["connect", ip_port])
            if "connected" in out.lower():
                self.connected_device = ip_port
                print(f"[Phone Hub] 📱 Connected to wireless device: {ip_port}")
                return True

        code, out = self.run_adb(["devices"])
        lines = out.splitlines()[1:] # Skip 'List of devices attached'
        devices = [l.split("\t")[0] for l in lines if "\tdevice" in l]
        
        if devices:
            self.connected_device = devices[0]
            print(f"[Phone Hub] 📱 Active device detected: {self.connected_device}")
            return True

        print("[Phone Hub] No active Android device detected via ADB.")
        return False

    def capture_phone_screenshot(self, target_path: Optional[str] = None) -> Optional[str]:
        """Captures a screenshot from the connected phone and pulls to local disk."""
        if not self.connected_device and not self.discover_and_connect_device():
            return None

        if not target_path:
            target_path = os.path.join(JARVIS_DIR, "phone_screen_latest.png")

        # 1. Take screencap on device
        self.run_adb(["-s", self.connected_device, "shell", "screencap", "-p", "/sdcard/pb_screen.png"])
        # 2. Pull screencap to PC
        code, _ = self.run_adb(["-s", self.connected_device, "pull", "/sdcard/pb_screen.png", target_path])
        if code == 0 and os.path.exists(target_path):
            return target_path
        return None

    def send_phone_sms(self, phone_number: str, message: str) -> bool:
        """Sends an SMS directly through the connected Android phone."""
        if not self.connected_device and not self.discover_and_connect_device():
            return False

        # Use Android intent to trigger or send SMS
        cmd = [
            "-s", self.connected_device, "shell", "service", "call", "isms", "5", 
            "i32", "0", "s16", "com.android.mms", "s16", phone_number, "s16", "null", "s16", f"'{message}'", "s16", "null", "s16", "null"
        ]
        code, _ = self.run_adb(cmd)
        return code == 0

    def start_clipboard_sync(self):
        """Starts background clipboard synchronization between PC and Phone."""
        if self.is_clipboard_sync_active: return
        self.is_clipboard_sync_active = True

        def _sync_loop():
            import pyperclip
            while self.is_clipboard_sync_active:
                if self.connected_device:
                    try:
                        # 1. Check PC clipboard
                        pc_text = pyperclip.paste()
                        if pc_text and pc_text != self._last_synced_clipboard:
                            # Push to phone
                            self.run_adb(["-s", self.connected_device, "shell", "input", "text", f'"{pc_text}"'])
                            self._last_synced_clipboard = pc_text
                    except Exception:
                        pass
                time.sleep(2.0)

        threading.Thread(target=_sync_loop, daemon=True).start()
        print("[Phone Hub] 📋 Cross-device clipboard sync active.")

# Global instance
phone_hub = PhoneHub2()
