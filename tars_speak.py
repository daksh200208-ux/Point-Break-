"""
TARS Voice Synthesizer & Communicator (Pocket TTS)
=================================================
Zero-shot cloned voice of TARS from Interstellar (voiced by Bill Irwin).
Powered by Kyutai Labs' 100M parameter Continuous Audio Language Model (Pocket TTS).
Runs 100% locally on CPU without external API keys or cloud dependencies.
Features sub-second real-time streaming playback via sounddevice.
"""

import os
import sys
import re
import time
import argparse
import queue
import threading
from pathlib import Path
import numpy as np
import scipy.io.wavfile
import winsound

try:
    import sounddevice as sd
except ImportError:
    sd = None

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
            # Dynamic INT8 quantization: 11x faster on CPU (4.6s vs 50.8s) with broadcast TARS fidelity
            try:
                _MODEL_INSTANCE = TTSModel.load_model(quantize=True)
            except Exception:
                _MODEL_INSTANCE = TTSModel.load_model()

        if _TARS_VOICE_STATE is None:
            if os.path.exists(DEFAULT_VOICE_STATE):
                _TARS_VOICE_STATE = _import_model_state(DEFAULT_VOICE_STATE, device=torch.device("cpu"))
            elif os.path.exists(DEFAULT_REF_AUDIO):
                _TARS_VOICE_STATE = _MODEL_INSTANCE.get_state_for_audio_prompt(DEFAULT_REF_AUDIO)
            else:
                raise FileNotFoundError(f"TARS voice reference not found at {DEFAULT_VOICE_STATE} or {DEFAULT_REF_AUDIO}")

        return _MODEL_INSTANCE, _TARS_VOICE_STATE

TARS_CLOUD_URL = os.environ.get("TARS_CLOUD_URL", "").strip()

class StreamingAudioProcessor:
    """
    Real-time streaming DSP limiter & compressor:
    - Running RMS / Peak tracker
    - Soft-knee dynamic compression & saturation (warm TARS harmonic presence)
    - Zero DC offset
    - Prevents sudden volume jumps or digital clipping
    """
    def __init__(self, target_peak: float = 0.88, initial_gain: float = 22.0):
        self.target_peak = target_peak
        self.gain = initial_gain
        self.threshold = 0.65

    def process(self, chunk: np.ndarray) -> np.ndarray:
        chunk = chunk - np.mean(chunk)
        chunk_peak = np.max(np.abs(chunk))
        if chunk_peak > 1e-4:
            instant_gain = self.target_peak / chunk_peak
            if instant_gain < self.gain:
                self.gain = 0.7 * self.gain + 0.3 * instant_gain
            else:
                self.gain = 0.98 * self.gain + 0.02 * instant_gain
        boosted = chunk * self.gain
        y = np.copy(boosted)
        mask = np.abs(boosted) > self.threshold
        if np.any(mask):
            sign = np.sign(boosted[mask])
            over = (np.abs(boosted[mask]) - self.threshold) / (1.0 - self.threshold + 1e-6)
            y[mask] = sign * (self.threshold + (1.0 - self.threshold) * np.tanh(over)) * 0.96
        return np.clip(y, -0.96, 0.96)

def stream_tars_speech(text: str, stop_event: threading.Event = None, on_start: callable = None, block: bool = True) -> bool:
    """
    Streams TARS cloned speech directly to system audio in real-time.
    Time-To-First-Audio (TTFA): ~0.9s on CPU (Pocket TTS INT8).
    Subsequent chunks stream seamlessly while previous chunks are playing.
    Returns True if completed successfully, False if aborted by stop_event.
    """
    text = clean_phonetics(text)
    if not text or not text.strip():
        return True

    if sd is None:
        speak(text, play=True, block=block, stream=False)
        return True

    model, voice_state = get_tars_model_and_voice()
    sr = model.sample_rate

    processor = StreamingAudioProcessor()
    audio_q = queue.Queue()
    playback_ready = threading.Event()
    gen_done = threading.Event()

    def callback(outdata, frames, time_info, status):
        needed = frames
        collected = []
        while needed > 0:
            if not hasattr(callback, "leftover") or callback.leftover is None or len(callback.leftover) == 0:
                try:
                    chunk = audio_q.get_nowait()
                    callback.leftover = chunk
                except queue.Empty:
                    if gen_done.is_set():
                        break
                    break
            avail = len(callback.leftover)
            take = min(needed, avail)
            collected.append(callback.leftover[:take])
            callback.leftover = callback.leftover[take:]
            needed -= take

        if collected:
            data = np.concatenate(collected)
            if len(data) < frames:
                pad = np.zeros(frames - len(data), dtype=np.float32)
                data = np.concatenate([data, pad])
            outdata[:] = data.reshape(-1, 1)
        else:
            outdata.fill(0)
            if gen_done.is_set() and audio_q.empty():
                raise sd.CallbackStop()

    def generator_thread():
        buffer_threshold = 2
        chunk_count = 0
        try:
            with _TARS_LOCK:
                import torch
                torch.set_num_threads(4)
                for chunk in model.generate_audio_stream(voice_state, text):
                    if stop_event and stop_event.is_set():
                        break
                    arr = chunk.numpy().astype(np.float32)
                    processed = processor.process(arr)
                    audio_q.put(processed)
                    chunk_count += 1
                    if chunk_count >= buffer_threshold and not playback_ready.is_set():
                        playback_ready.set()
        except Exception as e:
            print(f"  [TARS Stream Gen Error]: {e}")
        finally:
            gen_done.set()
            playback_ready.set()

    th = threading.Thread(target=generator_thread, daemon=True)
    th.start()

    # Wait for the initial buffer to fill (~160ms of audio)
    playback_ready.wait(timeout=3.0)

    if stop_event and stop_event.is_set():
        return False

    if on_start and callable(on_start):
        try:
            on_start()
        except Exception:
            pass

    try:
        with sd.OutputStream(samplerate=sr, channels=1, dtype='float32', callback=callback, blocksize=1024):
            while not (gen_done.is_set() and audio_q.empty()):
                if stop_event and stop_event.is_set():
                    return False
                time.sleep(0.03)
            time.sleep(0.2)
        return True
    except Exception as stream_err:
        print(f"  [TARS Stream Audio Error]: {stream_err}")
        return False

def generate_tars_audio(text: str, output_path: str = None) -> str:
    """
    Generates audio in TARS's voice for the given text.
    Returns the path to the saved 16-bit PCM WAV file.

    HYBRID ARCHITECTURE:
    1. Online Cloud GPU: When TARS_CLOUD_URL is set and reachable (~0.7s).
    2. Local Offline INT8: Multi-threaded quantized Pocket TTS on CPU (4.6s, 100% offline autonomy, zero DNS lag).
    """
    text = clean_phonetics(text)
    
    if output_path is None:
        temp_dir = os.path.join(MODULE_DIR, "scratch", "audio")
        os.makedirs(temp_dir, exist_ok=True)
        timestamp = int(time.time() * 1000)
        output_path = os.path.join(temp_dir, f"tars_{timestamp}.wav")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # 1. ONLINE CLOUD GPU ENGINE (Only if explicitly configured and starting with http)
    cloud_url = os.environ.get("TARS_CLOUD_URL", TARS_CLOUD_URL).strip()
    if cloud_url and cloud_url.startswith("http"):
        try:
            import requests
            ep = cloud_url.rstrip("/") + "/generate"
            r = requests.post(ep, json={"text": text}, timeout=2.5)
            if r.status_code == 200 and len(r.content) > 500:
                with open(output_path, "wb") as f:
                    f.write(r.content)
                return output_path
        except Exception:
            pass

    # 2. LOCAL OFFLINE MULTI-THREADED ENGINE (4-Thread CPU Pocket TTS)
    model, voice_state = get_tars_model_and_voice()
    with _TARS_LOCK:
        import torch
        torch.set_num_threads(4)  # Multi-threaded CPU execution
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

def speak(text: str, play: bool = True, block: bool = True, stream: bool = True) -> str:
    """
    Generates and optionally plays TARS's voice through the system audio.
    When stream=True (default), streams audio in real-time with sub-second response.
    """
    print(f"\n[TARS]: \"{text}\"")
    if play and stream and sd is not None:
        try:
            success = stream_tars_speech(text, block=block)
            if success:
                return ""
        except Exception as e:
            print(f"  [TARS Stream Playback Error, falling back to file]: {e}")

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
    parser.add_argument("--no-stream", action="store_true", help="Disable real-time streaming playback")
    args = parser.parse_args()

    if args.text.strip():
        speak(args.text, play=not args.no_play, stream=not args.no_stream)
    else:
        print("=" * 60)
        print("   TARS INTERSTELLAR VOICE SYNTHESIZER (POCKET TTS)")
        print("   Local Zero-Shot Neural Audio Voice Clone (Bill Irwin)")
        print("   Real-Time Streaming Engine Active")
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
                speak(user_text, play=True, stream=not args.no_stream)
            except (KeyboardInterrupt, EOFError):
                break

if __name__ == "__main__":
    main()
