#!/usr/bin/env python3
"""
Point Break - Contextual Smart Reply & Message Negotiator
=========================================================
Reads on-screen conversation context via screenshot + vision AI.
Generates tone-appropriate reply options (Firm / Diplomatic / Casual).
Copies best reply to clipboard and optionally types it.
"""
import sys, os, re, json, threading, time
sys.stdout.reconfigure(encoding="utf-8")

try:
    import pyautogui
    import pyperclip
except ImportError:
    pyautogui = None
    pyperclip = None

try:
    from PIL import ImageGrab
    import io, base64
except ImportError:
    ImageGrab = None


class SmartReplyEngine:
    """Reads on-screen messages and generates contextual reply options."""

    def __init__(self):
        self.last_replies = []
        self.last_context = ""

    def _capture_screen(self):
        """Capture the active screen region as base64 JPEG."""
        if not ImageGrab:
            return None
        try:
            import io
            screenshot = ImageGrab.grab()
            buffer = io.BytesIO()
            screenshot.save(buffer, format="JPEG", quality=70)
            return buffer.getvalue()
        except Exception as e:
            print(f"[Smart Reply] Screenshot error: {e}")
            return None

    def _analyze_conversation(self, image_bytes, query_ai_fn):
        """Use Gemini vision to read the on-screen conversation."""
        if not query_ai_fn or not image_bytes:
            return None
        try:
            import google.generativeai as genai
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(image_bytes))
            model = genai.GenerativeModel("gemini-2.0-flash")

            prompt = (
                "You are Point Break's visual conversation analyzer. "
                "Look at this screenshot of a messaging app (WhatsApp, Email, LinkedIn, Teams, Slack, etc.). "
                "Identify:\n"
                "1. The platform (WhatsApp/Email/LinkedIn/Teams/Slack/SMS/Other)\n"
                "2. The contact name or sender\n"
                "3. The last 3-5 messages in the conversation thread\n"
                "4. The tone of the conversation (formal/casual/angry/negotiation/friendly)\n"
                "5. What the other person is asking or saying in their latest message\n\n"
                "Return ONLY a JSON object with keys: platform, contact, messages (array of {sender, text}), "
                "tone, latest_intent. No markdown, no code fences."
            )

            response = model.generate_content([prompt, img])
            text = response.text.strip()
            # Clean any markdown fences
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            return json.loads(text)
        except Exception as e:
            print(f"[Smart Reply] Vision analysis error: {e}")
            return None

    def _generate_replies(self, context, query_ai_fn):
        """Generate 3 reply options using AI based on conversation context."""
        if not query_ai_fn or not context:
            return []
        try:
            import google.generativeai as genai
            model = genai.GenerativeModel("gemini-2.0-flash")

            platform = context.get("platform", "messaging app")
            contact = context.get("contact", "the sender")
            tone = context.get("tone", "neutral")
            latest = context.get("latest_intent", "")
            messages = context.get("messages", [])
            msg_text = "\n".join(f"  {m.get('sender','?')}: {m.get('text','')}" for m in messages[-5:])

            prompt = (
                f"You are Point Break's Smart Reply engine. Based on this {platform} conversation with {contact}:\n\n"
                f"Conversation:\n{msg_text}\n\n"
                f"Detected tone: {tone}\n"
                f"Latest intent from them: {latest}\n\n"
                f"Generate exactly 3 reply options:\n"
                f"1. FIRM - Direct, assertive, no-nonsense reply\n"
                f"2. DIPLOMATIC - Polite, professional, tactful reply\n"
                f"3. CASUAL - Friendly, relaxed, conversational reply\n\n"
                f"Each reply should be appropriate for {platform}. "
                f"Return ONLY a JSON array of 3 objects with keys: tone, reply. "
                f"No markdown, no code fences, no explanation."
            )

            response = model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            return json.loads(text)
        except Exception as e:
            print(f"[Smart Reply] Reply generation error: {e}")
            return []

    def generate_smart_reply(self, speak_fn=None, update_status_fn=None, query_ai_fn=None, auto_type=False):
        """Main entry: capture screen, analyze conversation, generate replies."""
        if speak_fn:
            speak_fn("Analyzing the conversation on your screen, sir. Give me a moment.", block=False)
        if update_status_fn:
            update_status_fn({"status": "smart_reply", "analyzing": True})

        # Step 1: Capture screen
        image_bytes = self._capture_screen()
        if not image_bytes:
            if speak_fn:
                speak_fn("Could not capture the screen. Make sure the messaging app is visible, sir.", block=False)
            return []

        # Step 2: Analyze conversation via vision
        context = self._analyze_conversation(image_bytes, query_ai_fn)
        if not context:
            if speak_fn:
                speak_fn("I could not read the conversation on screen. Please ensure the chat is clearly visible, sir.", block=False)
            return []

        self.last_context = context
        platform = context.get("platform", "the app")
        contact = context.get("contact", "them")

        if speak_fn:
            speak_fn(f"I can see a {platform} conversation with {contact}. Generating reply options now.", block=False)

        # Step 3: Generate reply options
        replies = self._generate_replies(context, query_ai_fn)
        if not replies:
            if speak_fn:
                speak_fn("Could not generate reply options. The conversation context may be unclear, sir.", block=False)
            return []

        self.last_replies = replies

        # Step 4: Copy the diplomatic reply to clipboard (safest default)
        best_reply = replies[1] if len(replies) > 1 else replies[0]  # Diplomatic is index 1
        reply_text = best_reply.get("reply", "")

        if pyperclip and reply_text:
            try:
                pyperclip.copy(reply_text)
            except Exception:
                pass

        # Step 5: Speak summary
        if speak_fn:
            firm = replies[0].get("reply", "N/A")[:60] if len(replies) > 0 else "N/A"
            diplo = replies[1].get("reply", "N/A")[:60] if len(replies) > 1 else "N/A"
            casual = replies[2].get("reply", "N/A")[:60] if len(replies) > 2 else "N/A"

            speak_fn(
                f"Three options ready for {contact} on {platform}. "
                f"Firm: {firm}. "
                f"Diplomatic: {diplo}. "
                f"Casual: {casual}. "
                f"I have copied the diplomatic reply to your clipboard. Press Ctrl V to paste it, sir.",
                block=False
            )

        # Step 6: Auto-type if requested
        if auto_type and pyautogui and reply_text:
            time.sleep(1.0)
            try:
                pyautogui.hotkey("ctrl", "v")
            except Exception as e:
                print(f"[Smart Reply] Auto-type error: {e}")

        if update_status_fn:
            update_status_fn({"status": "standby", "analyzing": False})

        return replies


# Module-level singleton
smart_reply_engine = SmartReplyEngine()
