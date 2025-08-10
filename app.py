"""
Simple Flask application providing a real‑time voice assistant demo.

Run with uv (recommended):

    # one-time: install uv (https://github.com/astral-sh/uv)
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # create/activate venv and install deps
    uv venv
    source .venv/bin/activate
    uv sync
    # start server
    uv run python app.py

Or with pip:

    pip install -r requirements.txt
    python app.py

Navigate to http://localhost:5000 in your browser.
"""

import os
import json
import time
import uuid
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from flask_sock import Sock
from dotenv import load_dotenv
import httpx
import threading
import websocket
from langdetect import detect

load_dotenv()

app = Flask(__name__)
sock = Sock(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-assistant-web")

SONIOX_API_KEY = os.getenv("SONIOX_API_KEY", "")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

DEFAULT_SONIOX_MODEL = os.getenv("SONIOX_MODEL", "soniox/embedded/v1/rt")
DEFAULT_LANGUAGE_HINTS = os.getenv("LANGUAGE_HINTS", "en,fr,nl").split(",")
DEFAULT_ELEVEN_VOICE_EN = os.getenv("ELEVEN_VOICE_EN", "21m00Tcm4TlvDq8ikWAM")
DEFAULT_ELEVEN_VOICE_FR = os.getenv("ELEVEN_VOICE_FR", "EXAVITQu4vr4xnSDxMaL")
DEFAULT_ELEVEN_VOICE_NL = os.getenv("ELEVEN_VOICE_NL", "ErXwobaYiN019PkySvjV")
ELEVEN_MODEL_ID = os.getenv("ELEVEN_TTS_MODEL", "eleven_flash_v2_5")

def choose_eleven_voice(lang_code: str) -> str:
    lang_code = (lang_code or "en").lower()
    if lang_code.startswith("fr"):
        return DEFAULT_ELEVEN_VOICE_FR
    if lang_code.startswith("nl") or lang_code.startswith("nl-be"):
        return DEFAULT_ELEVEN_VOICE_NL
    return DEFAULT_ELEVEN_VOICE_EN

def transcribe_audio_stub(audio_bytes: bytes) -> str:
    """Placeholder function that pretends to transcribe audio to text.

    In a real application, this function would send the audio to a streaming
    transcription service like Soniox, Deepgram or another provider and return
    the recognized text. Here we simply return a fixed string for
    demonstration purposes.
    """
    # TODO: replace this stub with a call to a real STT API
    return "Transcribed text would appear here"


def generate_response_stub(prompt: str) -> str:
    """Placeholder function that pretends to generate a response using an LLM.

    In a real application, this function would send the prompt to an LLM API
    (e.g. OpenAI's Chat Completion API) and return the model's response. Here
    we return a simple canned reply.
    """
    # Use OpenAI as a simple LLM backend if API key available; otherwise stub
    if OPENAI_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            system_prompt = (
                "You are a concise, helpful voice assistant. Reply in the same language as the user."
            )
            completion = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.4,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
            )
            return completion.choices[0].message.content or ""
        except Exception as e:
            logger.exception("OpenAI call failed; falling back to stub: %s", e)
    return f"You said: {prompt}. This is a stub response."


@app.route("/")
def index():
    """Render the main page with upload and chat forms."""
    return render_template("index.html")


## Legacy upload endpoint removed for simplified live-only UI


@app.route("/respond", methods=["POST"])
def respond():
    """Handle text messages and return a stubbed LLM response."""
    data = request.get_json(force=True)
    prompt = data.get("text", "")
    if not prompt:
        return jsonify({"error": "No text provided"}), 400

    # Simple language detection for TTS voice selection
    try:
        lang_code = detect(prompt)
    except Exception:
        lang_code = "en"

    response_text = generate_response_stub(prompt)

    # Log prompt/response
    logger.info("LLM prompt: %s", prompt)
    logger.info("LLM response: %s", response_text)

    return jsonify({"response": response_text, "lang": lang_code})


@app.route("/tts", methods=["POST"])
def tts_route():
    data = request.get_json(force=True)
    text = data.get("text", "")
    lang = data.get("lang", "en")
    voice_id = data.get("voice_id") or choose_eleven_voice(lang)

    if not ELEVEN_API_KEY:
        return jsonify({"error": "Missing ELEVEN_API_KEY"}), 500
    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Stream audio back to client as audio/mpeg
    async def eleven_stream():
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": ELEVEN_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": text,
            "model_id": ELEVEN_MODEL_ID,
            "voice_settings": {"stability": 0.4, "similarity_boost": 0.8},
            "optimize_streaming_latency": 4,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as r:
                async for chunk in r.aiter_bytes():
                    if chunk:
                        yield chunk

    return Response(eleven_stream(), mimetype="audio/mpeg")


# Serve static files for worklets
@app.route('/static/<path:filename>')
def static_files(filename: str):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)


@sock.route('/ws/stt')
def stt_proxy(ws_client):
    """Proxy between browser and Soniox RT WS to improve reliability and enable logging.

    Protocol:
    - Client first sends a JSON config: { language_hints: [..], sample_rate_hz: 48000 }
    - Then client sends raw PCM S16LE binary frames. We forward directly to Soniox.
    - We forward Soniox JSON messages back to the client as text.
    - On client close, we send EOS to Soniox and close.
    """
    if not SONIOX_API_KEY:
        ws_client.send(json.dumps({"type": "error", "message": "Missing SONIOX_API_KEY"}))
        return

    # Wait for initial JSON config from client
    try:
        raw_first = ws_client.receive()
        if isinstance(raw_first, (bytes, bytearray)):
            # If audio is sent before config, close
            ws_client.send(json.dumps({"type": "error", "message": "Expected JSON config first"}))
            return
        cfg_msg = json.loads(raw_first or '{}')
    except Exception as e:
        ws_client.send(json.dumps({"type": "error", "message": f"Invalid config: {e}"}))
        return

    language_hints = cfg_msg.get('language_hints') or DEFAULT_LANGUAGE_HINTS
    sample_rate_hz = int(cfg_msg.get('sample_rate_hz') or 48000)
    model = cfg_msg.get('model') or DEFAULT_SONIOX_MODEL

    # Connect to Soniox
    soniox_url = 'wss://stt-rt.soniox.com/transcribe-websocket'
    try:
        ws_sr = websocket.create_connection(soniox_url, sslopt={"cert_reqs": 0})
    except Exception as e:
        ws_client.send(json.dumps({"type": "error", "message": f"Failed to connect Soniox: {e}"}))
        return

    # Send Soniox config
    soniox_config = {
        "api_key": SONIOX_API_KEY,
        "model": model,
        "audio_format": "pcm_s16le",
        "sample_rate_hz": sample_rate_hz,
        "language_hints": language_hints,
        "interim_results": True,
    }
    try:
        ws_sr.send(json.dumps(soniox_config))
    except Exception as e:
        ws_client.send(json.dumps({"type": "error", "message": f"Failed to send config to Soniox: {e}"}))
        try:
            ws_sr.close()
        except Exception:
            pass
        return

    stop_flag = {"stop": False}

    def pipe_sr_to_client():
        try:
            while not stop_flag["stop"]:
                msg = ws_sr.recv()
                if msg is None:
                    break
                # Soniox sends text JSON; forward as-is
                if isinstance(msg, (bytes, bytearray)):
                    # Ignore unexpected binary from Soniox
                    continue
                ws_client.send(msg)
        except Exception:
            # Connection closed or errored
            pass

    t = threading.Thread(target=pipe_sr_to_client, daemon=True)
    t.start()

    # Receive audio from client and forward
    try:
        while True:
            frame = ws_client.receive()
            if frame is None:
                break
            if isinstance(frame, (bytes, bytearray)):
                try:
                    ws_sr.send_binary(frame)
                except Exception:
                    break
            else:
                # JSON text from client: check eos
                try:
                    obj = json.loads(frame)
                    if obj.get('eos'):
                        try:
                            ws_sr.send(json.dumps({"eos": True}))
                        except Exception:
                            pass
                        break
                except Exception:
                    continue
    finally:
        stop_flag["stop"] = True
        try:
            ws_sr.close()
        except Exception:
            pass

# Simple WebSocket endpoint to forward STT events to/from client if needed in future
# For now, we will do Soniox WS directly from client with a temp key endpoint below.

@app.route("/soniox-temp-key", methods=["POST"])
def soniox_temp_key():
    if not SONIOX_API_KEY:
        return jsonify({"error": "Missing SONIOX_API_KEY"}), 500

    # In real implementation, call Soniox to mint a temporary key.
    # If not available, return main key for dev, but DO NOT do this in prod.
    # Placeholder returns an opaque session token we generate to demo flow.
    # Replace with actual temp key creation using Soniox API when available.
    # We log the request for debugging.
    lang_hints = request.json.get("language_hints") if request.is_json else None
    logger.info("Issuing dev temp key; language_hints=%s", lang_hints)
    # WARNING: For demo only. Do not expose real key to browser in production.
    return jsonify({
        "temp_key": SONIOX_API_KEY,
        "model": DEFAULT_SONIOX_MODEL,
        "language_hints": lang_hints or DEFAULT_LANGUAGE_HINTS,
    })


if __name__ == "__main__":
    # Enable debug mode for development; remove debug=True in production
    app.run(debug=True)
