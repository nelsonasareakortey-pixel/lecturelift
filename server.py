import json
import logging
import os
import re
import time
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory, Response
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE_DIR))
app.config["MAX_CONTENT_LENGTH"] = 450 * 1024
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
app.logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

VIDEO_PATTERNS = [
    r"(?:https?://)?(?:www\.)?youtube\.com/watch\?.*?[&?]v=([A-Za-z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})",
    r"(?:https?://)?(?:www\.)?youtube\.com/(?:embed|shorts|live)/([A-Za-z0-9_-]{11})",
]
SUPADATA_BASE_URL = "https://api.supadata.ai/v1"


def get_video_id(url: str) -> str:
    if not url or len(url) > 500:
        raise ValueError("Enter a valid YouTube video link.")
    for pattern in VIDEO_PATTERNS:
        match = re.search(pattern, url.strip())
        if match:
            return match.group(1)
    raise ValueError("That link doesn't look like a supported YouTube video URL. Use a youtube.com/watch?v=..., youtu.be/..., Shorts, or embed link.")


def fetch_transcript(video_id: str) -> str:
    """Fetch YouTube captions through Supadata, polling for asynchronous jobs."""
    api_key = os.environ.get("SUPADATA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("SUPADATA_API_KEY is not configured in Render.")
    headers = {"x-api-key": api_key, "Accept": "application/json"}
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    response = requests.get(
        f"{SUPADATA_BASE_URL}/transcript",
        params={"url": video_url, "text": "true", "mode": "auto"},
        headers=headers,
        timeout=45,
    )
    if response.status_code not in (200, 202):
        try:
            payload = response.json()
            detail = payload.get("message") or payload.get("error") or response.text
        except Exception:
            detail = response.text
        raise RuntimeError(f"Supadata request failed (HTTP {response.status_code}): {str(detail)[:250]}")
    result = response.json()
    job_id = result.get("jobId")
    if job_id:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            time.sleep(3)
            job_response = requests.get(
                f"{SUPADATA_BASE_URL}/transcript/{job_id}",
                headers=headers,
                timeout=30,
            )
            if job_response.status_code != 200:
                raise RuntimeError(f"Supadata job check failed (HTTP {job_response.status_code}).")
            job = job_response.json()
            status = str(job.get("status", "")).lower()
            if status == "completed":
                result = job.get("result") or job
                break
            if status == "failed":
                error = job.get("error") or "Transcript processing failed."
                raise RuntimeError(f"Supadata processing failed: {str(error)[:250]}")
        else:
            raise RuntimeError("Supadata is still processing this video. Wait a minute and try again.")
    content = result.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("text")).strip()
    return ""


@app.post("/api/ask")
def ask_ai():
    """Answer a student's question, optionally grounded in the current lecture's saved study pack."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "The request body was not valid JSON. Refresh the page and try again."}), 400
    question = str(data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Type a question first."}), 400
    if len(question) > 5000:
        return jsonify({"error": "Please keep your question under 5,000 characters."}), 413
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return jsonify({"error": "The AI service is not configured. The site owner must add GROQ_API_KEY in Render Environment."}), 503
    language = str(data.get("outputLanguage") or "English")[:40]
    lecture_title = str(data.get("lectureTitle") or "").strip()[:250]
    context = str(data.get("context") or "").strip()[:18000]
    system_prompt = (
        f"You are LectureLift's helpful study tutor. Answer in {language}. "
        "Explain concepts clearly for a student, use headings or steps when helpful, and give examples where useful. "
        "If lecture context is provided, prioritize it and clearly distinguish it from general knowledge. "
        "If the context does not contain the answer, say so briefly and then offer a general explanation if possible. "
        "Do not invent quotes or claim that something was in the lecture unless it appears in the supplied context."
    )
    user_prompt = f"Question:\n{question}"
    if context:
        user_prompt = f"Selected lecture: {lecture_title or 'Current lecture'}\n\nSaved lecture study-pack context:\n{context}\n\n{user_prompt}"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=90.0, max_retries=1)
        response = client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=0.3,
            max_tokens=3000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        answer = (response.choices[0].message.content or "").strip()
        if not answer:
            return jsonify({"error": "The AI returned an empty answer. Please try asking in a different way."}), 502
        return jsonify({"answer": answer})
    except Exception as exc:
        app.logger.exception("Ask AI request failed: %s", type(exc).__name__)
        message = str(exc).lower()
        if "model" in message and ("not found" in message or "does not exist" in message):
            return jsonify({"error": "The configured Groq model is unavailable. Check GROQ_MODEL in Render Environment."}), 502
        if "api key" in message or "authentication" in message or "unauthorized" in message:
            return jsonify({"error": "Groq rejected the API key. Check GROQ_API_KEY in Render Environment."}), 503
        if "quota" in message or "rate limit" in message or "billing" in message:
            return jsonify({"error": "The AI provider has reached a usage limit. Check your Groq account and try again later."}), 503
        return jsonify({"error": "LectureLift could not get an AI answer just now. Check Render Logs and try again."}), 502


@app.get("/api/search-images")
def search_images():
    """Search Wikimedia Commons for educational visuals and return attribution metadata."""
    query = str(request.args.get("q") or "").strip()[:150]
    if not query:
        return jsonify({"error": "Enter a topic to search for images."}), 400
    params = {
        "action": "query", "generator": "search",
        "gsrsearch": query + " filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": 6, "prop": "imageinfo", "iiprop": "url|extmetadata",
        "iiurlwidth": 900, "format": "json",
    }
    try:
        response = requests.get(
            "https://commons.wikimedia.org/w/api.php", params=params,
            headers={"User-Agent": "LectureLift/1.0 (educational study notes)"}, timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        pages = (payload.get("query") or {}).get("pages") or {}
        images = []
        for page in pages.values():
            info_list = page.get("imageinfo") or []
            if not info_list:
                continue
            info = info_list[0]
            meta = info.get("extmetadata") or {}
            images.append({
                "title": page.get("title", "Educational image"),
                "imageUrl": info.get("thumburl") or info.get("url"),
                "sourceUrl": info.get("descriptionurl"),
                "license": (meta.get("LicenseShortName") or {}).get("value", "Check source page"),
                "attribution": (meta.get("Artist") or {}).get("value", "See source page"),
            })
        return jsonify({"images": images})
    except Exception as exc:
        app.logger.warning("Image search failed: %s", type(exc).__name__)
        return jsonify({"error": "Image search is temporarily unavailable. Please try again."}), 502


@app.post("/api/generate-image")
def generate_image():
    """Optional AI illustration endpoint using Hugging Face Inference Providers."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A valid JSON request is required."}), 400
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "Describe the educational image you want."}), 400
    if len(prompt) > 1200:
        return jsonify({"error": "Keep the image prompt under 1,200 characters."}), 413
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        return jsonify({"error": "AI image generation is optional and not configured yet. Add HF_TOKEN in Render Environment. Image search still works without it."}), 503
    model = os.environ.get("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell").strip()
    endpoint = f"https://router.huggingface.co/hf-inference/models/{model}"
    try:
        response = requests.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "Accept": "image/*"},
            json={"inputs": "Educational textbook illustration. Clear composition, accurate subject matter, no decorative text or watermark. " + prompt},
            timeout=120,
        )
        if not response.ok:
            app.logger.warning("Image generation provider returned HTTP %s", response.status_code)
            return jsonify({"error": "The image provider could not generate this image. Check HF_TOKEN, HF_IMAGE_MODEL, and your provider access/usage limits."}), 502
        content_type = response.headers.get("Content-Type", "image/png").split(";")[0]
        if not content_type.startswith("image/"):
            return jsonify({"error": "The image provider did not return an image. Check the selected model and provider settings."}), 502
        return Response(response.content, mimetype=content_type, headers={"Cache-Control": "no-store"})
    except requests.RequestException as exc:
        app.logger.warning("Image generation request failed: %s", type(exc).__name__)
        return jsonify({"error": "AI image generation timed out or is temporarily unavailable. Please try again."}), 502


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
    return jsonify({"status": "ok", "service": "LectureLift Studio"})


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
            app.logger.info("Supadata transcript fetch succeeded: video_id=%s chars=%s", video_id, len(transcript))
        except Exception as exc:
            app.logger.warning("Automatic transcript fetch failed for %s: %s: %s", video_id, type(exc).__name__, str(exc)[:500])
            detail = str(exc)
            if "SUPADATA_API_KEY is not configured" in detail:
                return jsonify({"error": "Automatic captions are not configured. Add SUPADATA_API_KEY in Render → your service → Environment, then redeploy."}), 503
            if "HTTP 401" in detail or "HTTP 403" in detail:
                return jsonify({"error": "Supadata rejected the API key. Check SUPADATA_API_KEY in Render Environment."}), 503
            if "HTTP 429" in detail:
                return jsonify({"error": "The transcript service has reached a usage limit. Check your Supadata dashboard or paste the transcript manually."}), 503
            return jsonify({"error": "LectureLift could not fetch this video's transcript automatically. Check that the video is public and captions are available, or paste the transcript into the transcript box and retry. Check Render Logs for details if the problem continues."}), 422
    if len(transcript) < 80:
        app.logger.warning("Transcript too short: video_id=%s chars=%s", video_id, len(transcript))
        return jsonify({"error": f"The transcript contains only {len(transcript)} characters. Paste at least a few complete paragraphs (80+ characters) and try again."}), 422
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        app.logger.error("GROQ_API_KEY is missing.")
        return jsonify({"error": "The site owner has not configured the AI service. Add GROQ_API_KEY in Render → your service → Environment, then redeploy."}), 503
    level = str(data.get("level") or "University / Level 100")[:100]
    style = str(data.get("style") or "Detailed lecture notes")[:100]
    question_count = str(data.get("questionCount") or "15")[:10]
    question_types = str(data.get("questionTypes") or "Mixed: MCQ + short answer + essay")[:100]
    output_language = str(data.get("outputLanguage") or "English")[:40]
    prompt = f"""Create a detailed, accurate LectureLift study pack from the YouTube lecture transcript below.

OUTPUT LANGUAGE: {output_language}
Write every field in {output_language}, even if the transcript is in another language.
Audience level: {level}
Notes style: {style}
Number of practice questions: {question_count}
Question formats: {question_types}

NOTES QUALITY REQUIREMENTS:
- Make notes meaningfully more detailed than a short transcript summary. Explain main concepts, how they work, why they matter, and how ideas connect.
- Organize notes with a title, headings, subheadings, definitions, numbered steps where useful, examples, comparisons, and key takeaways.
- Start with "LEARNING OBJECTIVES" and a short "LECTURE OVERVIEW".
- Include a section called "WHAT THE VIDEO COVERS". Keep lecture-specific claims grounded in the transcript.
- Include a separate section called "SUPPLEMENTARY EXPLANATIONS (AI-ADDED)". Add relevant background knowledge, simpler explanations, practical examples, analogies, and useful context beyond the transcript. Never imply this material was spoken by the lecturer.
- If an extra fact is uncertain or needs checking, label it for verification instead of presenting it as certain.
- Correct obvious speech-to-text errors only when context strongly supports the correction; flag ambiguity.
- Do not invent quotations, statistics, sources, page numbers, citations, or experiments.
- Finish notes with "KEY TAKEAWAYS" and "QUICK REVISION SUMMARY".
- Avoid repetition and keep notes comprehensive but readable. Aim for 1,200–1,800 words when the transcript has enough substance; use fewer for short or incomplete lectures.
- Put questions without answers in the questions field.
- Put matching answers and short explanations in the answers field. For essay questions, include a marking guide or key points.
- Include 8–10 concise flashcards, one per line, formatted as "Q: ... | A: ...".
- Suggest 3–5 educational visual ideas relevant to the actual topic. Use specific search phrases; prefer diagrams for processes, anatomy, systems, and abstract concepts. Do not claim images already exist or were generated.
- Return one valid JSON object with exactly these fields: "notes" (string), "questions" (string), "answers" (string), "flashcards" (string), "imageSuggestions" (array of short strings).

TRANSCRIPT (limited to keep generation reliable):
{transcript[:45000]}
"""
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1", timeout=120.0, max_retries=1)
        response = client.chat.completions.create(
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            temperature=0.2,
            # Groq JSON mode can fail if the completion ends before a full JSON object.
            # Give it a generous output budget while keeping the requested pack concise.
            max_tokens=10000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": f"Return valid JSON only. Include notes, questions, answers, and flashcards as strings, plus imageSuggestions as an array of strings. Write all fields in {output_language}, regardless of the source transcript language."},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        pack = json.loads(content)
        result = {}
        for key in ("notes", "questions", "answers", "flashcards"):
            value = pack.get(key, "")
            result[key] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        suggestions = pack.get("imageSuggestions", [])
        if isinstance(suggestions, str):
            try:
                suggestions = json.loads(suggestions)
            except Exception:
                suggestions = [suggestions]
        if not isinstance(suggestions, list):
            suggestions = []
        result["imageSuggestions"] = [str(item).strip()[:180] for item in suggestions[:5] if str(item).strip()]
        if not any(result.values()):
            app.logger.error("AI returned an empty study pack for video_id=%s", video_id)
            return jsonify({"error": "The AI returned an empty study pack. Please try again with a shorter transcript."}), 502
        app.logger.info("Study pack generated successfully: video_id=%s", video_id)
        return jsonify(result)
    except Exception as exc:
        app.logger.exception("Study pack generation failed: %s", type(exc).__name__)
        message = str(exc).lower()
        if "model" in message and ("not found" in message or "does not exist" in message):
            return jsonify({"error": "The configured AI model is unavailable for this API account. In Render Environment, set GROQ_MODEL to a model available to your Groq account. Check https://console.groq.com/docs/models for current model IDs."}), 502
        if "api key" in message or "authentication" in message or "unauthorized" in message:
            return jsonify({"error": "The AI API key was rejected. Check GROQ_API_KEY in Render Environment. Never paste the key into this chat or GitHub."}), 503
        if "insufficient_quota" in message or "billing" in message or "quota" in message:
            return jsonify({"error": "The AI API account has no available quota or billing is not enabled. Check API billing on the provider dashboard."}), 503
        if "json_validate_failed" in message or "failed to generate json" in message or "max completion tokens reached" in message:
            return jsonify({"error": "The AI response was too long to finish as valid JSON. Please retry; LectureLift now limits the transcript and requests a more compact study pack. If it keeps happening, use a shorter transcript or choose a model with a larger output limit in Render Environment."}), 502
        return jsonify({"error": "The transcript was received, but AI generation failed. Check Render Logs for the detailed server error, and verify GROQ_API_KEY, GROQ_MODEL and your Groq usage limits."}), 502


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
