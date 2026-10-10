import json
import logging
import os
import re
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE_DIR))
app.config["MAX_CONTENT_LENGTH"] = 450 * 1024  # allow pasted transcripts up to 400 KB
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
app.logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

VIDEO_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?.*?[&?]v=([A-Za-z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/(?:embed|shorts|live)/([A-Za-z0-9_-]{11})",
]

def get_video_id(url: str) -> str:
    if not url or len(url) > 500:
        raise ValueError("Enter a valid YouTube video link.")
    for pattern in VIDEO_PATTERNS:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    raise ValueError("That link doesn't look like a supported YouTube video URL. Use a youtube.com/watch?v=..., youtu.be/..., Shorts, or embed link.")

def fetch_transcript(video_id: str) -> str:
    """Best-effort only. Cloud-hosted IP addresses may be blocked by YouTube."""
    api = YouTubeTranscriptApi()
    transcript = api.fetch(video_id)
    parts = []
    for segment in transcript:
        text = getattr(segment, "text", "")
        if text:
            parts.append(text)
    return " ".join(parts).strip()

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "The request is too large. Please paste a shorter transcript section (under 100,000 characters)."}), 413

@app.errorhandler(429)
def too_many(_error):
    return jsonify({"error": "Too many requests in a short time. Please wait a little and try again."}), 429

@app.get("/")
def home():
    return send_from_directory(str(BASE_DIR), "index.html")

@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "LectureLift"})

@app.post("/api/generate")
def generate():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "The request body was not valid JSON. Refresh the page and try again."}), 400

    url = str(data.get("url") or "").strip()
    try:
        video_id = get_video_id(url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    transcript = str(data.get("transcript") or "").strip()
    app.logger.info("Generate request received: video_id=%s pasted_transcript_chars=%s", video_id, len(transcript))

    if len(transcript) > 100000:
        return jsonify({"error": "The transcript is over 100,000 characters. Please shorten it and try again."}), 413

    if not transcript:
        try:
            transcript = fetch_transcript(video_id)
            app.logger.info("Automatic transcript fetch succeeded: video_id=%s chars=%s", video_id, len(transcript))
        except Exception as exc:
            # Log diagnostic details on the server, but do not leak sensitive internals to the visitor.
            app.logger.warning("Automatic transcript fetch failed for %s: %s: %s", video_id, type(exc).__name__, str(exc)[:500])
            return jsonify({
                "error": "LectureLift could not fetch captions automatically. YouTube sometimes blocks transcript requests from cloud servers. Open the video on YouTube, choose Show transcript, copy the transcript, paste it into the transcript box, and retry. If you already pasted text, check that the box still contains it before submitting."
            }), 422

    if len(transcript) < 80:
        app.logger.warning("Transcript too short: video_id=%s chars=%s", video_id, len(transcript))
        return jsonify({"error": f"The transcript contains only {len(transcript)} characters. Paste at least a few complete paragraphs (80+ characters) and try again."}), 422

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        app.logger.error("OPENAI_API_KEY is missing.")
        return jsonify({"error": "The site owner has not configured the AI service. Add OPENAI_API_KEY in Render → your service → Environment, then redeploy."}), 503

    level = str(data.get("level") or "University / Level 100")[:100]
    style = str(data.get("style") or "Detailed lecture notes")[:100]
    question_count = str(data.get("questionCount") or "15")[:10]
    question_types = str(data.get("questionTypes") or "Mixed: MCQ + short answer + essay")[:100]

    prompt = f"""Create a high-quality study pack based on the lecture transcript below.
Audience level: {level}
Notes style: {style}
Number of practice questions: {question_count}
Question formats: {question_types}

Requirements:
- Base lecture-specific claims on the transcript. Do not pretend missing content was spoken.
- Correct obvious speech-to-text mistakes only when context strongly supports the correction; flag uncertainty.
- Notes should have headings, learning objectives, definitions, explanations, examples where supported, key takeaways and a concise revision summary.
- Put questions without answers in the questions field.
- Put matching answers and short explanations in the answers field. For essay questions, include a marking guide or key points.
- Include 10–15 concise flashcards in the flashcards field, one per line, formatted as "Q: ... | A: ...".
- If the transcript appears incomplete, say so in the notes.
- Return a JSON object with exactly these four string fields: notes, questions, answers, flashcards.

TRANSCRIPT:
{transcript[:85000]}
"""
    try:
        client = OpenAI(api_key=api_key, timeout=120.0, max_retries=1)
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Return valid JSON only. Include notes, questions, answers, and flashcards as strings."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        pack = json.loads(content)
        result = {}
        for key in ("notes", "questions", "answers", "flashcards"):
            value = pack.get(key, "")
            result[key] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        if not any(result.values()):
            app.logger.error("AI returned an empty study pack for video_id=%s", video_id)
            return jsonify({"error": "The AI returned an empty study pack. Please try again with a shorter transcript."}), 502
        app.logger.info("Study pack generated successfully: video_id=%s", video_id)
        return jsonify(result)
    except Exception as exc:
        app.logger.exception("Study pack generation failed: %s", type(exc).__name__)
        # Give common configuration issues a useful message without exposing the secret or full traceback.
        message = str(exc).lower()
        if "model" in message and ("not found" in message or "does not exist" in message):
            return jsonify({"error": "The configured AI model is unavailable for this API account. In Render Environment, set OPENAI_MODEL to a model available to your account, such as gpt-4o-mini if enabled."}), 502
        if "api key" in message or "authentication" in message or "unauthorized" in message:
            return jsonify({"error": "The AI API key was rejected. Check OPENAI_API_KEY in Render Environment. Never paste the key into this chat or GitHub."}), 503
        if "insufficient_quota" in message or "billing" in message or "quota" in message:
            return jsonify({"error": "The AI API account has no available quota or billing is not enabled. Check API billing on the provider dashboard."}), 503
        return jsonify({"error": "The transcript was received, but AI generation failed. Check Render Logs for the detailed server error, and verify OPENAI_API_KEY, OPENAI_MODEL and API billing."}), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
