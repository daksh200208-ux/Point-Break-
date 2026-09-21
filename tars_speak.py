"""
TARS Voice Synthesizer & Communicator (Pocket TTS)
=================================================
Zero-shot cloned voice of TARS from Interstellar (voiced by Bill Irwin).
Powered by Kyutai Labs' 100M parameter Continuous Audio Language Model (Pocket TTS).
Runs 100% locally on CPU without external API keys or cloud dependencies.
"""

import os
import sys
import re
import time
import argparse
import numpy as np
import scipy.io.wavfile
import winsound
from pathlib import Path

def clean_phonetics(text: str) -> str:
    """
    Phonetically maps proper names and words to prevent English TTS grapheme slurring.
    'Daksh' -> 'Duck-sh' ensures the 'k' and 'sh' consonants are enunciated crisply (/dʌkʃ/).
    """
    if not text:
        return text
    text = re.sub(r'\bDaksh\b', 'Duck-sh', text)
    text = re.sub(r'\bdaksh\b', 'duck-sh', text)
    text = re.sub(r'\bDAKSH\b', 'DUCK-SH', text)
    return text

import threading

# Paths
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
VOICE_DIR = os.path.join(MODULE_DIR, "assets", "voices", "tars")
DEFAULT_VOICE_STATE = os.path.join(VOICE_DIR, "tars_voice.safetensors")
DEFAULT_REF_AUDIO = os.path.join(VOICE_DIR, "tars_ref_honesty.wav")

_MODEL_INSTANCE = None
_TARS_VOICE_STATE = None
_TARS_LOCK = threading.Lock()

def get_tars_model_and_voice():
    """Lazily loads and caches the Pocket TTS model and TARS voice profile with thread safety."""
    global _MODEL_INSTANCE, _TARS_VOICE_STATE
    with _TARS_LOCK:
        if _MODEL_INSTANCE is not None and _TARS_VOICE_STATE is not None:
            return _MODEL_INSTANCE, _TARS_VOICE_STATE

        import torch
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from pocket_tts import TTSModel
        from pocket_tts.models.tts_model import _import_model_state

        if _MODEL_INSTANCE is None:
            # Standard load uses the voice-cloning capable model
            _MODEL_INSTANCE = TTSModel.load_model()

        if _TARS_VOICE_STATE is None:
            if os.path.exists(DEFAULT_VOICE_STATE):
                _TARS_VOICE_STATE = _import_model_state(DEFAULT_VOICE_STATE, device=torch.device("cpu"))
            elif os.path.exists(DEFAULT_REF_AUDIO):
                _TARS_VOICE_STATE = _MODEL_INSTANCE.get_state_for_audio_prompt(DEFAULT_REF_AUDIO)
            else:
                raise FileNotFoundError(f"TARS voice reference not found at {DEFAULT_VOICE_STATE} or {DEFAULT_REF_AUDIO}")

        return _MODEL_INSTANCE, _TARS_VOICE_STATE

def generate_tars_audio(text: str, output_path: str = None) -> str:
    """
    Generates audio in TARS's voice for the given text.
    Returns the path to the saved 16-bit PCM WAV file.
    """
    text = clean_phonetics(text)
    model, voice_state = get_tars_model_and_voice()
    
    if output_path is None:
        temp_dir = os.path.join(MODULE_DIR, "scratch", "audio")
        os.makedirs(temp_dir, exist_ok=True)
        timestamp = int(time.time() * 1000)
        output_path = os.path.join(temp_dir, f"tars_{timestamp}.wav")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with _TARS_LOCK:
        audio_tensor = model.generate_audio(voice_state, text)
    data = audio_tensor.numpy().astype(np.float32)

    # ── STUDIO DYNAMIC RANGE COMPRESSION & BROADCAST LOUDNESS ──
    # 1. Remove DC offset
    data = data - np.mean(data)

    # 2. Initial peak normalization to 0.85 to establish consistent headroom
    raw_peak = np.max(np.abs(data))
    if raw_peak > 1e-5:
        data = data * (0.85 / raw_peak)

    # 3. Soft-knee dynamic range compression & saturation
    # Boosts vocal body by ~2.8x (+9 dB) while smoothly compressing transient peaks (plosives)
    gain = 2.8
    boosted = data * gain
    threshold = 0.65
    y = np.copy(boosted)
    mask_high = np.abs(boosted) > threshold
    if np.any(mask_high):
        sign = np.sign(boosted[mask_high])
        over = (np.abs(boosted[mask_high]) - threshold) / (1.0 - threshold)
        y[mask_high] = sign * (threshold + (1.0 - threshold) * np.tanh(over)) * 0.96

    # 4. Smooth edge tapering & zero-padding (eliminates start/end clicks, pops, and vocoder scratchiness)
    sr = model.sample_rate
    fade_in_len = int(sr * 0.020)   # 20ms smooth raised-cosine fade-in
    fade_out_len = int(sr * 0.030)  # 30ms smooth raised-cosine fade-out
    if len(y) > (fade_in_len + fade_out_len):
        fade_in = 0.5 * (1.0 - np.cos(np.linspace(0, np.pi, fade_in_len, dtype=np.float32)))
        y[:fade_in_len] *= fade_in
        fade_out = 0.5 * (1.0 + np.cos(np.linspace(0, np.pi, fade_out_len, dtype=np.float32)))
        y[-fade_out_len:] *= fade_out
        y[0] = 0.0
        y[-1] = 0.0

    # 4b. Lead-in and lead-out true silence buffer (prevents soundcard DMA DAC step-clicks)
    pad_in = np.zeros(int(sr * 0.015), dtype=np.float32)
    pad_out = np.zeros(int(sr * 0.025), dtype=np.float32)
    y = np.concatenate([pad_in, y, pad_out])

    # 5. Convert to 16-bit PCM dual-channel stereo (powers both left & right speakers at 100%)
    pcm16 = (np.clip(y, -0.96, 0.96) * 32767).astype(np.int16)
    if pcm16.ndim == 1:
        stereo_pcm16 = np.column_stack((pcm16, pcm16))
    else:
        stereo_pcm16 = pcm16

    scipy.io.wavfile.write(output_path, model.sample_rate, stereo_pcm16)
    return output_path

def speak(text: str, play: bool = True, block: bool = True) -> str:
    """
    Generates and optionally plays TARS's voice through the system audio.
    """
    print(f"\n[TARS]: \"{text}\"")
    wav_file = generate_tars_audio(text)

    if play and sys.platform == "win32":
        flags = winsound.SND_FILENAME
        if not block:
            flags |= winsound.SND_ASYNC
        winsound.PlaySound(wav_file, flags)

    return wav_file

def main():
    parser = argparse.ArgumentParser(description="TARS Voice Synthesizer (Pocket TTS)")
    parser.add_argument("text", nargs="?", default="", help="Text to speak in TARS's voice")
    parser.add_argument("--out", "-o", default=None, help="Output WAV file path")
    parser.add_argument("--no-play", action="store_true", help="Do not play audio automatically")
    args = parser.parse_args()

    if args.text.strip():
        speak(args.text, play=not args.no_play)
    else:
        print("=" * 60)
        print("   TARS INTERSTELLAR VOICE SYNTHESIZER (POCKET TTS)")
        print("   Local Zero-Shot Neural Audio Voice Clone (Bill Irwin)")
        print("=" * 60)
        print("Type any text below to hear TARS speak (type 'exit' to quit):\n")

        while True:
            try:
                user_text = input("TARS > ").strip()
                if not user_text:
                    continue
                if user_text.lower() in ("exit", "quit", "q"):
                    print("TARS: Shutting down speech interface.")
                    break
                speak(user_text, play=True)
            except (KeyboardInterrupt, EOFError):
                break

if __name__ == "__main__":
    main()
