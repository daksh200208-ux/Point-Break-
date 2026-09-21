"""
Point Break Humanized Speech Engine
===================================
Injects realistic human disfluencies ("uhhh", "you know", "um", breathing pauses,
micro-hesitations, and syllable stutters) into text prior to Neural TTS synthesis.
Provides Point Break with an authentic, organic, and living vocal presence.
"""

import re
import random
from typing import Optional

# Natural sentence-starter fillers
STARTER_FILLERS = [
    "Well... uh, ",
    "Right, so... uh, ",
    "Let's see... um, ",
    "Uh, ",
    "Um... ",
    "Right... you know, ",
    "Hold on... uh, ",
    "Actually... um, ",
]

# Natural mid-sentence fillers
MID_FILLERS = [
    ", you know, ",
    "... uh, ",
    "... um, ",
    ", I mean, ",
]

# Words eligible for natural micro-stutters
STUTTER_WORDS = {
    "i": "I- I",
    "it": "it- it",
    "it's": "it- it's",
    "we": "we- we",
    "that": "th- that",
    "the": "the- the",
    "there": "th- there",
    "you": "you- you",
}

class HumanizeVoiceEngine:
    """
    Intelligently humanizes text for speech synthesis while safeguarding
    critical data, code, numbers, and system diagnostics.
    """

    def __init__(self, enabled: bool = True, probability: float = 0.35):
        self.enabled = enabled
        self.probability = probability

    def should_skip(self, text: str) -> bool:
        """Determines if text should bypass humanization for safety & clarity."""
        if not self.enabled or not text or len(text.strip()) < 12:
            return True

        low = text.lower()

        # Skip pure code, syntax blocks, or URLs
        if any(c in text for c in ["```", "`", "{", "}", "[", "]", "<", ">", "\\", "http://", "https://", "def ", "class ", "import ", "return "]):
            return True

        # Skip pure digit streams (e.g. raw OTPs or phone numbers)
        if re.fullmatch(r'[\d\s\-:.]+', text.strip()):
            return True

        # Skip critical emergency security or system alerts
        critical_keywords = [
            "protocol omega", "self-destruct", "emergency shutdown", "pin code", "auth token"
        ]
        if any(k in low for k in critical_keywords):
            return True

        # Skip if text already contains explicit filler tokens
        if any(f in low for f in [" uh ", " um ", " you know ", "well..."]):
            return True

        return False

    def humanize(self, text: str, force: bool = False) -> str:
        """
        Transforms text by injecting natural conversational pauses and human disfluencies ("uh", "um", "well"),
        replacing awkward punctuation silences with organic speech flow.
        """
        if not force and self.should_skip(text):
            return text

        words = text.split()
        if len(words) < 3:
            return text

        result = text.strip()

        # 1. Mid-Sentence Comma Smoothing (replaces awkward dead-air punctuation stops with natural "uh/um")
        if "," in result:
            def _replace_comma(match):
                if random.random() < 0.85:
                    return random.choice([", uh, ", ", um, ", ", you know, ", ", well, "])
                return match.group(0)
            result = re.sub(r',\s+', _replace_comma, result)

        # 2. Mid-Sentence Period Smoothing (replaces dead stops between sentences with fluid human thinking bridges)
        if re.search(r'\.\s+[A-Za-z]', result):
            def _replace_period(match):
                nxt = match.group(1)
                if random.random() < 0.75:
                    bridge = random.choice(["... uh, ", "... um, ", "... so, ", ". Well, "])
                    return bridge + nxt.lower()
                return ". " + nxt
            result = re.sub(r'\.\s+([A-Za-z])', _replace_period, result)

        # 3. Sentence Starter Vocalization (starts response with natural human thinking cadence)
        if not any(result.lower().startswith(f.lower().strip(" ,...")) for f in ["well", "uh", "um", "right", "let's see"]):
            if random.random() < 0.45:
                starter = random.choice(STARTER_FILLERS)
                first_char_lower = result[0].lower() + result[1:]
                result = starter + first_char_lower

        # Clean any accidental double punctuation or spacing
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r',\s*,', ',', result)
        result = re.sub(r'\.\s*\.', '...', result)
        return result.strip()


# Module-level singleton
humanize_engine = HumanizeVoiceEngine(enabled=True, probability=0.35)

def humanize_speech(text: str, force: bool = False) -> str:
    """Helper function to humanize speech for edge_tts."""
    return humanize_engine.humanize(text, force=force)
