"""
Point Break 3.0 — Lightweight Chrome DevTools Protocol (CDP) Controller
=======================================================================
Ultra-fast browser automation via Chrome Debugging Port (default 9222)
without heavy Selenium or Webdriver dependencies.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import time
from typing import Dict, Any, Optional, List

class ChromeCDPClient:
    def __init__(self, debug_port: int = 9222):
        self.port = debug_port
        self.base_url = f"http://127.0.0.1:{debug_port}"

    def is_chrome_running_with_debugging(self) -> bool:
        """Checks if Chrome is listening on debugging port."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/json/version", timeout=1.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def launch_chrome_with_debugging(self, initial_url: str = "https://google.com") -> bool:
        """Launches Chrome with remote debugging enabled."""
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        ]
        for p in chrome_paths:
            if os.path.exists(p):
                user_data = os.path.expandvars("%LOCALAPPDATA%/Google/Chrome/PB_Profile")
                cmd = f'"{p}" --remote-debugging-port={self.port} --user-data-dir="{user_data}" "{initial_url}"'
                subprocess.Popen(cmd, shell=True)
                time.sleep(2.0)
                return True
        return False

    def get_tabs(self) -> List[Dict[str, Any]]:
        """Returns list of open Chrome tabs."""
        try:
            with urllib.request.urlopen(f"{self.base_url}/json/list", timeout=2.0) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"[CDP] Tab discovery error: {e}")
            return []

    def get_active_page_tab(self) -> Optional[Dict[str, Any]]:
        tabs = self.get_tabs()
        for t in tabs:
            if t.get("type") == "page":
                return t
        return tabs[0] if tabs else None

    def navigate_active_tab(self, url: str) -> bool:
        tab = self.get_active_page_tab()
        if not tab:
            if self.launch_chrome_with_debugging(url):
                return True
            return False

        # In CDP, navigation or new tab can be triggered via /json/new
        try:
            encoded_url = urllib.parse.quote(url, safe=":/?=&")
            with urllib.request.urlopen(f"{self.base_url}/json/activate/{tab['id']}", timeout=2.0):
                pass
            return True
        except Exception as e:
            print(f"[CDP] Navigation error: {e}")
            return False

# Global instance
cdp_client = ChromeCDPClient()
