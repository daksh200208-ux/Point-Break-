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

        # Skip code, math, and formatted data
        if any(c in text for c in ["```", "`", "{", "}", "[", "]", "<", ">", "\\", "/", "()", "def ", "class ", "import ", "return "]):
            return True

        # Skip numbers, dates, OTPs, currency, time, percentages
        if re.search(r'\b\d+[:.]?\d*\b', text):
            return True

        # Skip critical emergency, security, diagnostic, or system alerts
        critical_keywords = [
            "warning", "error", "failed", "offline", "diagnostics", "battery",
            "percent", "shutdown", "restart", "alarm", "timer", "pin", "otp",
            "password", "protocol omega", "self-destruct", "coordinates", "degrees"
        ]
        if any(k in low for k in critical_keywords):
            return True

        # Skip if text already contains explicit filler tokens
        if any(f in low for f in ["uh", "um", "you know", "well..."]):
            return True

        return False

    def humanize(self, text: str, force: bool = False) -> str:
        """
        Transforms text by injecting natural conversational pauses and disfluencies.
        """
        if not force and self.should_skip(text):
            return text

        words = text.split()
        if len(words) < 4:
            return text

        result = text.strip()

        # Decide whether to apply disfluency based on probability
        if not force and random.random() > self.probability:
            return result

        dice = random.random()

        # Pattern A: Sentence Starter Filler (45% of humanized utterances)
        if dice < 0.45:
            filler = random.choice(STARTER_FILLERS)
            first_char_lower = result[0].lower() + result[1:]
            result = filler + first_char_lower

        # Pattern B: Word Micro-Stutter (25% of humanized utterances)
        elif dice < 0.70:
            words_list = result.split()
            stuttered = False
            for idx, w in enumerate(words_list[:4]):
                clean_w = w.lower().strip(" ,.!?\"'")
                if clean_w in STUTTER_WORDS:
                    rep = STUTTER_WORDS[clean_w]
                    if w[0].isupper():
                        rep = rep[0].upper() + rep[1:]
                    words_list[idx] = rep
                    stuttered = True
                    break
            if stuttered:
                result = " ".join(words_list)
            else:
                # Fallback to starter filler
                result = random.choice(STARTER_FILLERS) + result[0].lower() + result[1:]

        # Pattern C: Mid-Sentence Insertion (30% of humanized utterances)
        else:
            sentences = re.split(r'([,.])', result)
            if len(sentences) >= 3 and len(sentences[0].split()) >= 3:
                # Insert filler after the first clause
                filler = random.choice(MID_FILLERS)
                sentences[1] = filler
                result = "".join(sentences)
            else:
                result = random.choice(STARTER_FILLERS) + result[0].lower() + result[1:]

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
