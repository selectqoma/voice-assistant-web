"""
Simple Flask application providing a bare‑bones interface for a voice assistant demo.

This app serves a single web page (index.html) where users can upload an audio file
to simulate a speech‑to‑text (STT) request and send a text message to simulate
a large language model (LLM) response. Both endpoints currently return hard‑coded
placeholders, since integrating real speech APIs requires network access and
authentication. In a production environment you would replace the placeholder
functions with actual API calls to your preferred STT, LLM and TTS services.

To run this app locally:

    pip install -r requirements.txt
    python app.py

Then navigate to http://localhost:5000 in your browser.
"""

from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

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
    # TODO: replace this stub with a call to your preferred language model
    return f"You said: {prompt}. This is a stub response."


@app.route("/")
def index():
    """Render the main page with upload and chat forms."""
    return render_template("index.html")


@app.route("/transcribe", methods=["POST"])
def transcribe():
    """Handle audio file uploads and return a transcribed placeholder."""
    file = request.files.get("audio")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    # Read file bytes for processing (unused in stub)
    audio_bytes = file.read()
    text = transcribe_audio_stub(audio_bytes)
    return jsonify({"transcription": text})


@app.route("/respond", methods=["POST"])
def respond():
    """Handle text messages and return a stubbed LLM response."""
    data = request.get_json(force=True)
    prompt = data.get("text", "")
    if not prompt:
        return jsonify({"error": "No text provided"}), 400

    response_text = generate_response_stub(prompt)
    return jsonify({"response": response_text})


if __name__ == "__main__":
    # Enable debug mode for development; remove debug=True in production
    app.run(debug=True)
