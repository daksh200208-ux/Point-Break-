import sys, os
sys.path.append(r"C:\Users\hp\.gemini\antigravity\scratch\jarvis")
import tars_speak

clips = [
    ("tars_quote_slaves.wav", "Everybody good? Plenty of slaves for my robot colony."),
    ("tars_quote_honesty.wav", "Absolute honesty is not always the most diplomatic, nor the safest form of communication with emotional beings."),
    ("tars_quote_chess.wav", "Point Break system active. Autonomous Grandmaster Chess Titan online. Standing by for command.")
]

out_dir = r"C:\Users\hp\.gemini\antigravity\scratch\jarvis\assets\voices\tars"
for fname, quote in clips:
    target = os.path.join(out_dir, fname)
    tars_speak.generate_tars_audio(quote, target)
    print(f"[+] Created: {fname} ({os.path.getsize(target)} bytes)")
