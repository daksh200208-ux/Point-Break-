"""
Point Break — Centralized Google GenAI Bridge
=============================================
Migrated to the official `google.genai` SDK (replaces deprecated `google.generativeai`).
Provides unified, thread-safe text and vision model inference with automatic
fallback across live verified Gemini models:
  1. gemini-3.5-flash-lite (fastest, primary)
  2. gemini-3.5-flash (high accuracy)
  3. gemini-2.5-flash (stable failover)
"""

import os
import sys
import time
import threading
from typing import Optional, List, Any, Union

_CLIENT = None
_CLIENT_LOCK = threading.Lock()
_API_KEY = None

DEFAULT_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
]

def load_api_key() -> Optional[str]:
    """Find and load the Gemini API key from environment or .env files."""
    global _API_KEY
    if _API_KEY:
        return _API_KEY

    # 1. Check direct environment variable
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if key and len(key.strip()) > 10:
        _API_KEY = key.strip()
        return _API_KEY

    # 2. Check local directory .env
    base_dirs = [
        os.path.dirname(os.path.abspath(__file__)),
        os.getcwd(),
        os.path.expanduser("~"),
    ]

    for bdir in base_dirs:
        env_path = os.path.join(bdir, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GEMINI_API_KEY=") or line.startswith("GOOGLE_API_KEY="):
                            parts = line.split("=", 1)
                            if len(parts) == 2 and parts[1].strip():
                                _API_KEY = parts[1].strip().strip('"').strip("'")
                                os.environ["GEMINI_API_KEY"] = _API_KEY
                                return _API_KEY
            except Exception:
                pass

    return None

def get_client():
    """Retrieve or initialize the google.genai Client singleton."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    with _CLIENT_LOCK:
        if _CLIENT is not None:
            return _CLIENT

        api_key = load_api_key()
        try:
            from google import genai
            if api_key:
                _CLIENT = genai.Client(api_key=api_key)
            else:
                _CLIENT = genai.Client()
            return _CLIENT
        except Exception as e:
            print(f"[Point Break GenAI] Warning: Client initialization failed: {e}")
            return None

def query_text(
    prompt: str,
    model: Optional[str] = None,
    system_instruction: Optional[str] = None,
    timeout: float = 15.0
) -> Optional[str]:
    """
    Generate text using Gemini with multi-model failover.
    Never raises an unhandled exception — returns None on failure.
    """
    client = get_client()
    if not client:
        return None

    models_to_try = [model] if model else []
    for m in DEFAULT_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    for m in models_to_try:
        try:
            config = {}
            if system_instruction:
                config["system_instruction"] = system_instruction

            resp = client.models.generate_content(
                model=m,
                contents=prompt,
                config=config if config else None
            )
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e:
            err_str = str(e)
            if "404" in err_str or "NOT_FOUND" in err_str or "429" in err_str:
                time.sleep(0.3)
                continue
            time.sleep(0.2)
            continue

    print(f"[Point Break GenAI] All models failed for text prompt.")
    return None

def query_vision(
    image_input: Any,
    prompt: str,
    model: Optional[str] = None,
    system_instruction: Optional[str] = None,
    timeout: float = 20.0
) -> Optional[str]:
    """
    Analyze image with Gemini Vision.
    Supports PIL Image, raw bytes, or file path.
    """
    client = get_client()
    if not client:
        return None

    contents = []
    try:
        if isinstance(image_input, (bytes, bytearray)):
            from PIL import Image
            import io
            pil_img = Image.open(io.BytesIO(image_input))
            contents = [pil_img, prompt]
        elif isinstance(image_input, str) and os.path.exists(image_input):
            from PIL import Image
            pil_img = Image.open(image_input)
            contents = [pil_img, prompt]
        else:
            contents = [image_input, prompt]
    except Exception as e:
        print(f"[Point Break GenAI Vision] Image prep error: {e}")
        return None

    models_to_try = [model] if model else []
    for m in DEFAULT_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    for m in models_to_try:
        try:
            config = {}
            if system_instruction:
                config["system_instruction"] = system_instruction

            resp = client.models.generate_content(
                model=m,
                contents=contents,
                config=config if config else None
            )
            if resp and resp.text:
                return resp.text.strip()
        except Exception as e:
            err_str = str(e)
            if "404" in err_str or "NOT_FOUND" in err_str:
                continue
            time.sleep(0.3)
            continue

    print(f"[Point Break GenAI] All models failed for vision prompt.")
    return None

def query_generative_model(model_name: str, content: Any, system_instruction: Optional[str] = None, timeout: float = 12.0) -> Optional[str]:
    if isinstance(content, list) and len(content) >= 2:
        img_item = None
        txt_item = ""
        for item in content:
            if isinstance(item, str):
                txt_item = item
            else:
                img_item = item
        if img_item:
            return query_vision(img_item, txt_item, model=model_name, system_instruction=system_instruction, timeout=timeout)
        else:
            joined_txt = " ".join([str(c) for c in content])
            return query_text(joined_txt, model=model_name, system_instruction=system_instruction, timeout=timeout)
    else:
        txt = str(content) if not isinstance(content, str) else content
        return query_text(txt, model=model_name, system_instruction=system_instruction, timeout=timeout)

def query_tars_vision(image_bytes: bytes, user_query: str) -> Optional[str]:
    system_instruction = (
        "You are Point Break — Daksh's personal AI visual perception system. "
        "Sharp, observant, and concise like JARVIS. "
        "Describe or analyze the image with calm, direct clarity."
    )
    return query_vision(image_bytes, user_query, system_instruction=system_instruction)
