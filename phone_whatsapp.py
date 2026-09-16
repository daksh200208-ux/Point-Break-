"""
Point Break — Wireless Phone WhatsApp Intent Dispatcher
========================================================
Dispatches WhatsApp text messages and voice notes directly through
the wireless Android device via native Android intents.
"""

import os
import re
import time
import urllib.parse
import subprocess
from phone_bridge import phone_bridge

class PhoneWhatsAppEngine:
    def __init__(self):
        pass

    def send_whatsapp_text(self, contact_or_number: str, message: str, contacts_dict: dict = None) -> bool:
        """Sends WhatsApp text directly from Phone without touching PC browser."""
        dev = phone_bridge.get_device_id()
        if not dev:
            return False

        # 1. Resolve phone number if given name
        clean_target = contact_or_number.lower().strip()
        phone_num = ""
        if contacts_dict and clean_target in contacts_dict:
            phone_num = contacts_dict[clean_target]

        if not phone_num:
            raw_digits = re.sub(r'[^\d+]', '', contact_or_number)
            if len(raw_digits) >= 10:
                phone_num = raw_digits
            else:
                phone_num = contact_or_number

        encoded_msg = urllib.parse.quote(message) if message else ""
        intent_url = f"https://api.whatsapp.com/send?phone={phone_num}"
        if encoded_msg:
            intent_url += f"&text={encoded_msg}"

        # 2. Wake screen and unlock keyguard
        phone_bridge._run_adb(["-s", dev, "shell", "input", "keyevent", "26"], timeout=3)
        phone_bridge._run_adb(["-s", dev, "shell", "input", "keyevent", "82"], timeout=3)

        # 3. Launch WhatsApp Intent on Android
        code, _, _ = phone_bridge._run_adb([
            "-s", dev, "shell", "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", intent_url,
            "-f", "0x10000000"
        ], timeout=6)

        if code != 0:
            return False

        # 4. Wait for WhatsApp chat UI to load, then send ENTER (keyevent 66)
        if message:
            time.sleep(2.0)
            phone_bridge._run_adb(["-s", dev, "shell", "input", "keyevent", "66"], timeout=3)

        return True

    def send_whatsapp_voice(self, contact_or_number: str, local_audio_path: str, contacts_dict: dict = None) -> bool:
        """Pushes synthesized audio note to Phone and opens WhatsApp target."""
        dev = phone_bridge.get_device_id()
        if not dev or not os.path.exists(local_audio_path):
            return False

        remote_audio = "/sdcard/Music/PointBreak_VoiceNotes/voice_note.mp3"
        phone_bridge._run_adb(["-s", dev, "shell", "mkdir", "-p", "/sdcard/Music/PointBreak_VoiceNotes"], timeout=3)
        phone_bridge._run_adb(["-s", dev, "push", local_audio_path, remote_audio], timeout=8)

        # Resolve recipient
        clean_target = contact_or_number.lower().strip()
        phone_num = contacts_dict.get(clean_target, "") if contacts_dict else ""
        if not phone_num:
            phone_num = re.sub(r'[^\d+]', '', contact_or_number) or contact_or_number

        intent_url = f"https://api.whatsapp.com/send?phone={phone_num}"
        phone_bridge._run_adb(["-s", dev, "shell", "input", "keyevent", "26"], timeout=3)
        phone_bridge._run_adb(["-s", dev, "shell", "input", "keyevent", "82"], timeout=3)
        phone_bridge._run_adb(["-s", dev, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", intent_url, "-f", "0x10000000"], timeout=6)
        return True

phone_whatsapp = PhoneWhatsAppEngine()
