"""
TARS Voice Synthesizer & Communicator (Pocket TTS)
=================================================
Zero-shot cloned voice of TARS from Interstellar (voiced by Bill Irwin).
Powered by Kyutai Labs' 100M parameter Continuous Audio Language Model (Pocket TTS).
Runs 100% locally on CPU without external API keys or cloud dependencies.
"""

import os
import sys
import time
import argparse
import numpy as np
import scipy.io.wavfile
import winsound
from pathlib import Path

# Paths
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
VOICE_DIR = os.path.join(MODULE_DIR, "assets", "voices", "tars")
DEFAULT_VOICE_STATE = os.path.join(VOICE_DIR, "tars_voice.safetensors")
DEFAULT_REF_AUDIO = os.path.join(VOICE_DIR, "tars_ref_honesty.wav")

_MODEL_INSTANCE = None
_TARS_VOICE_STATE = None

def get_tars_model_and_voice():
    """Lazily loads and caches the Pocket TTS model and TARS voice profile."""
    global _MODEL_INSTANCE, _TARS_VOICE_STATE
    if _MODEL_INSTANCE is not None and _TARS_VOICE_STATE is not None:
        return _MODEL_INSTANCE, _TARS_VOICE_STATE

    import torch
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
    model, voice_state = get_tars_model_and_voice()
    
    if output_path is None:
        temp_dir = os.path.join(MODULE_DIR, "scratch", "audio")
        os.makedirs(temp_dir, exist_ok=True)
        timestamp = int(time.time() * 1000)
        output_path = os.path.join(temp_dir, f"tars_{timestamp}.wav")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    audio_tensor = model.generate_audio(voice_state, text)
    data = audio_tensor.numpy().astype(np.float32)

    # ── STUDIO AMPLITUDE & LOUDNESS NORMALIZATION ──
    # Pocket TTS generates low raw amplitude tensors (~0.01-0.08 peak).
    # Normalize to 0.95 peak (-0.45 dBFS) to ensure loud, clear, room-filling cinematic volume.
    max_amp = np.max(np.abs(data))
    if max_amp > 1e-5:
        target_peak = 0.95
        normalized = data * (target_peak / max_amp)
    else:
        normalized = data

    pcm16 = (np.clip(normalized, -1.0, 1.0) * 32767).astype(np.int16)
    scipy.io.wavfile.write(output_path, model.sample_rate, pcm16)
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
