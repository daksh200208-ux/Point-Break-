import os
import time
import scipy.io.wavfile
import pocket_tts
from pocket_tts.models.tts_model import TTSModel, load_config
from pocket_tts import export_model_state

def main():
    weights_file = r"C:\Users\hp\.cache\huggingface\hub\models--openensemble--pocket-tts\snapshots\0c22ea94220f3f98cad12df9a21e1158daa20037\languages\english\model.safetensors"
    config_path = r"C:\Users\hp\AppData\Local\Programs\Python\Python311\Lib\site-packages\pocket_tts\config\english.yaml"
    
    model_config = load_config(config_path)
    model_config.weights_path = weights_file

    print("[1/4] Loading Pocket TTS model with voice cloning weights...")
    model = TTSModel._from_pydantic_config_with_weights(
        model_config, temp=0.3, sampler_decode_steps=1, noise_clamp=None, eos_threshold=-4.0
    )

    tars_dir = r"C:\Users\hp\.gemini\antigravity\scratch\jarvis\assets\voices\tars"
    ref_path = os.path.join(tars_dir, "tars_ref_honesty.wav")
    
    print(f"[2/4] Cloning TARS voice from reference: {ref_path}")
    t0 = time.time()
    voice_state = model.get_state_for_audio_prompt(ref_path)
    print(f"[+] TARS Voice profile extracted in {time.time() - t0:.2f}s!")

    # Export to reusable .safetensors for instant loading
    safetensors_path = os.path.join(tars_dir, "tars_voice.safetensors")
    print(f"[3/4] Exporting portable voice state to: {safetensors_path}")
    export_model_state(voice_state, safetensors_path)
    print(f"[+] Saved {os.path.getsize(safetensors_path)} bytes safetensors profile!")

    # Generate sample speech
    test_phrase = "Hello Cooper. Setting humor to 75%. Honesty parameter confirmed at 90%. Ready when you are."
    print(f"[4/4] Generating speech in cloned TARS voice:\n      \"{test_phrase}\"")
    t0 = time.time()
    audio = model.generate_audio(voice_state, test_phrase)
    dur_speech = time.time() - t0
    
    out_wav = os.path.join(tars_dir, "tars_sample_speech.wav")
    scipy.io.wavfile.write(out_wav, model.sample_rate, audio.numpy())
    audio_dur = len(audio) / model.sample_rate
    print(f"[+] SUCCESS! Generated {audio_dur:.2f}s of audio in {dur_speech:.2f}s ({audio_dur/dur_speech:.2f}x real-time speed)!")
    print(f"[+] Audio saved to: {out_wav}")

if __name__ == "__main__":
    main()
