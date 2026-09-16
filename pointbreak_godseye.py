"""
Point Break — God's Eye (Argus Engine Integration)
==================================================
Swaps God's Eye with the lightweight Argus global camera intelligence matrix.
Visualizes 229,000+ public traffic & CCTV cameras across 126+ countries on a GPU-accelerated HUD & 3D Globe.
Runs on an ultra-lightweight (< 15MB RAM) local server with zero system strain.
"""

import os
import sys
import webbrowser
import threading
from typing import Optional

JARVIS_DIR = os.path.dirname(os.path.abspath(__file__))
ARGUS_DIR = os.path.join(JARVIS_DIR, "argus")
sys.path.insert(0, ARGUS_DIR)

try:
    import argus_unified_server
except ImportError:
    argus_unified_server = None

ARGUS_PORT = 8787

class GodsEyeBridge:
    def __init__(self, port: int = ARGUS_PORT):
        self.port = port
        self.server_started = False
        self._lock = threading.Lock()

    def ensure_server_running(self):
        with self._lock:
            if not self.server_started and argus_unified_server:
                argus_unified_server.start_server_background(self.port)
                self.server_started = True

    def get_url(self) -> str:
        return f"http://localhost:{self.port}"

    def launch(self, query: str = "", speak_fn=None) -> bool:
        """Launches the Argus God's Eye Tactical Suite directly in the browser."""
        self.ensure_server_running()
        url = self.get_url()
        low = query.lower()

        spoken_msg = "Deploying God's Eye Argus global surveillance interface. Visualizing 229,000 live camera nodes across 126 countries."
        if "cctv" in low or "traffic" in low:
            spoken_msg = "Accessing God's Eye optical CCTV surveillance matrix."
        elif "globe" in low or "orbit" in low or "satellite" in low:
            spoken_msg = "Deploying God's Eye 3D orbital globe surveillance projection."

        if speak_fn:
            speak_fn(spoken_msg)
        else:
            print(f"[God's Eye] {spoken_msg}")

        webbrowser.open(url)
        return True

gods_eye_bridge = GodsEyeBridge()
velocity_bridge = gods_eye_bridge
