#!/usr/bin/env python3
"""
Point Break - Universal Hold-to-Talk Voice Typing Engine
========================================================
Hold Ctrl+Shift+Space to activate continuous speech-to-text
that types directly into any focused Windows application.
Release the keys to stop.
"""
import sys, os, time, threading
sys.stdout.reconfigure(encoding="utf-8")

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None

try:
    import pyautogui
except ImportError:
    pyautogui = None


HOTKEY_COMBO = "ctrl+shift+space"
HOTKEY_DISPLAY = "Ctrl+Shift+Space"


class VoiceTypingEngine:
    """Hold-to-talk voice typing that injects text at cursor position."""

    def __init__(self):
        self._active = False
        self._listening = False
        self._recognizer = sr.Recognizer() if sr else None
        self._mic = None
        self._thread = None
        self._daemon_running = False
        self._hotkey_registered = False
        self._stop_event = threading.Event()

    def _on_hotkey_press(self):
        """Called when Ctrl+Shift+Space is pressed (held down)."""
        if self._listening:
            return
        self._listening = True
        self._stop_event.clear()
        print(f"[Voice Typing] ACTIVATED - listening...")
        self._thread = threading.Thread(target=self._listen_and_type, daemon=True)
        self._thread.start()

    def _on_hotkey_release(self):
        """Called when Ctrl+Shift+Space is released."""
        if not self._listening:
            return
        self._listening = False
        self._stop_event.set()
        print("[Voice Typing] DEACTIVATED - stopped listening")

    def _listen_and_type(self):
        """Continuously listen to speech and type it into the active window."""
        if not self._recognizer or not sr:
            print("[Voice Typing] speech_recognition not available")
            return

        try:
            mic = sr.Microphone()
        except Exception as e:
            print(f"[Voice Typing] Microphone error: {e}")
            self._listening = False
            return

        with mic as source:
            self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
            while self._listening and not self._stop_event.is_set():
                try:
                    audio = self._recognizer.listen(source, timeout=2, phrase_time_limit=5)
                    if not self._listening or self._stop_event.is_set():
                        break
                    try:
                        text = self._recognizer.recognize_google(audio, language="en-IN")
                        if text and text.strip() and pyautogui:
                            # Type the transcribed text at cursor position
                            # Use write for ASCII, hotkey paste for Unicode
                            try:
                                import pyperclip
                                pyperclip.copy(text + " ")
                                pyautogui.hotkey("ctrl", "v")
                            except Exception:
                                pyautogui.write(text + " ", interval=0.02)
                            print(f"[Voice Typing] Typed: {text}")
                    except sr.UnknownValueError:
                        pass  # Could not understand - continue listening
                    except sr.RequestError as e:
                        print(f"[Voice Typing] Recognition API error: {e}")
                except sr.WaitTimeoutError:
                    pass  # Timeout waiting for speech - loop again if still held
                except Exception as e:
                    print(f"[Voice Typing] Listen error: {e}")
                    break

    def start_daemon(self, speak_fn=None, update_status_fn=None):
        """Start the voice typing hotkey daemon in the background."""
        if self._daemon_running:
            if speak_fn:
                speak_fn("Voice typing is already active, sir. Hold Ctrl Shift Space to dictate.", block=False)
            return True

        if not keyboard:
            if speak_fn:
                speak_fn("The keyboard library is required for voice typing. Please install it with pip install keyboard.", block=False)
            return False

        if not sr:
            if speak_fn:
                speak_fn("Speech recognition library is required. Please install it with pip install SpeechRecognition.", block=False)
            return False

        try:
            # Register hold-to-talk hotkey
            keyboard.on_press_key("space", lambda e: self._on_hotkey_press()
                if keyboard.is_pressed("ctrl") and keyboard.is_pressed("shift") else None,
                suppress=False)
            keyboard.on_release_key("space", lambda e: self._on_hotkey_release()
                if not (keyboard.is_pressed("ctrl") and keyboard.is_pressed("shift")) else None,
                suppress=False)

            self._daemon_running = True
            self._hotkey_registered = True

            if speak_fn:
                speak_fn(
                    f"Universal voice typing engine is online, sir. "
                    f"Hold {HOTKEY_DISPLAY} to dictate into any application. "
                    f"Release to stop. Zero friction, zero lag.",
                    block=False
                )
            if update_status_fn:
                update_status_fn({"voice_typing": True, "voice_typing_hotkey": HOTKEY_DISPLAY})

            print(f"[Voice Typing] Daemon started. Hotkey: {HOTKEY_DISPLAY}")
            return True

        except Exception as e:
            print(f"[Voice Typing] Daemon start error: {e}")
            if speak_fn:
                speak_fn("Failed to initialize voice typing engine, sir.", block=False)
            return False

    def stop_daemon(self, speak_fn=None, update_status_fn=None):
        """Stop the voice typing daemon."""
        if not self._daemon_running:
            if speak_fn:
                speak_fn("Voice typing was not active, sir.", block=False)
            return

        self._listening = False
        self._stop_event.set()
        self._daemon_running = False

        if keyboard and self._hotkey_registered:
            try:
                keyboard.unhook_all()
                self._hotkey_registered = False
            except Exception:
                pass

        if speak_fn:
            speak_fn("Voice typing engine deactivated, sir.", block=False)
        if update_status_fn:
            update_status_fn({"voice_typing": False})

        print("[Voice Typing] Daemon stopped.")

    def toggle(self, speak_fn=None, update_status_fn=None):
        """Toggle voice typing on/off."""
        if self._daemon_running:
            self.stop_daemon(speak_fn, update_status_fn)
        else:
            self.start_daemon(speak_fn, update_status_fn)

    @property
    def is_active(self):
        return self._daemon_running


# Module-level singleton
voice_typing_engine = VoiceTypingEngine()
