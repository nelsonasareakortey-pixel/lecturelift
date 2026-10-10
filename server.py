import json
import os
import re
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from openai import OpenAI
from youtube_transcript_api import YouTubeTranscriptApi

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE_DIR))
app.config["MAX_CONTENT_LENGTH"] = 110 * 1024  # request body cap
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
)

def get_video_id(url: str) -> str:
    patterns = [
        r"(?:https?://)?(?:www\.)?youtube\.com/watch\?.*?[&?]v=([A-Za-z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})",
        r"(?:https?://)?(?:www\.)?youtube\.com/(?:embed|shorts)/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Please enter a valid YouTube video URL.")

def fetch_transcript(video_id: str) -> str:
    # This only works when captions are available and the transcript service can access them.
    fetched = YouTubeTranscriptApi().fetch(video_id)
    return " ".join(segment.text for segment in fetched)

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "The transcript is too large. Please paste a shorter transcript section."}), 413

@app.get("/")
def home():
    return send_from_directory(str(BASE_DIR), "index.html")

@app.get("/health")
def health():
    return jsonify({"status": "ok"})

@app.post("/api/generate")
@limiter.limit(os.environ.get("GENERATE_LIMIT", "5 per hour"))
def generate():
    try:
        data = request.get_json(silent=True) or {}
        url = str(data.get("url", "")).strip()
        if len(url) > 500:
            return jsonify({"error": "The YouTube link is too long."}), 400
        video_id = get_video_id(url)
        transcript = str(data.get("transcript", "")).strip()

        if len(transcript) > 100000:
            return jsonify({"error": "Please keep the transcript under 100,000 characters."}), 413

        if not transcript:
            try:
                transcript = fetch_transcript(video_id)
            except Exception:
                return jsonify({
                    "error": "I couldn't retrieve captions automatically. This can happen when captions are disabled or YouTube blocks transcript access. Open the video on YouTube, choose 'Show transcript' if available, copy the transcript, paste it into the transcript box, and try again."
                }), 422

        if len(transcript) < 80:
            return jsonify({"error": "The transcript is too short. Paste more of the lecture transcript and try again."}), 422

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            app.logger.error("OPENAI_API_KEY is not configured.")
            return jsonify({"error": "The AI service is not configured yet. The site owner needs to add the OPENAI_API_KEY secret in the hosting dashboard."}), 503

        client = OpenAI(api_key=api_key)
        question_count = str(data.get("questionCount", "15 questions"))
        style = str(data.get("style", "Detailed lecture notes"))
        level = str(data.get("level", "University / Level 100"))
        question_types = str(data.get("questionTypes", "Mixed: MCQ + short answer + essay"))

        prompt = f"""
Create a high-quality study pack from the supplied lecture transcript.
Audience level: {level}
Notes style: {style}
Practice question count: {question_count}
Question format: {question_types}

Rules:
- Ground lecture-specific claims in the transcript. Do not invent claims about what the lecturer said.
- Correct clear speech-to-text errors only when context strongly supports the correction; flag uncertainty.
- Make notes useful for university revision, with headings, learning objectives, definitions, explanations, examples, key takeaways, and a concise revision summary.
- Provide numbered practice questions without answers in the questions section.
- Provide matching answers with short explanations; essay questions should include a marking guide/key points.
- Include 10–15 concise flashcards, one per line.
- If the transcript appears incomplete, say so in the notes.
- Return a valid JSON object with exactly four string keys: notes, questions, answers, flashcards.

TRANSCRIPT:
{transcript[:90000]}
"""
        completion = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "Return only valid JSON with the requested four string fields."},
                {"role": "user", "content": prompt},
            ],
        )
        content = completion.choices[0].message.content
        pack = json.loads(content or "{}")
        for key in ("notes", "questions", "answers", "flashcards"):
            if not isinstance(pack.get(key), str):
                pack[key] = str(pack.get(key, ""))
        return jsonify({key: pack[key] for key in ("notes", "questions", "answers", "flashcards")})

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("Study pack generation failed")
        return jsonify({"error": "The study pack could not be generated right now. Please try again later."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
