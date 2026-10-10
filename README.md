# LectureLift Studio

An original lecture-to-learning workspace with a responsive dashboard, YouTube lecture player, editable personal notes, generated study packs, flashcards, quiz review, collections, local library search and export/backup.

## Stack
- Flask API
- Supadata transcript API (automatic YouTube transcript retrieval)
- Groq API via OpenAI-compatible client
- Vanilla HTML/CSS/JavaScript frontend

## Environment variables
- `SUPADATA_API_KEY`: required for automatic transcript retrieval.
- `GROQ_API_KEY`: required for study-pack generation.
- `GROQ_MODEL`: optional; must be a model enabled for your Groq account.

Never commit API keys to GitHub.

## Deploy to Render
1. Upload `index.html`, `server.py`, `requirements.txt`, `render.yaml`, and `.gitignore` to your GitHub repository.
2. In Render, create or open the Web Service linked to the repository.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn server:app`
5. In Environment, add `SUPADATA_API_KEY` and `GROQ_API_KEY`; keep their values private. Ensure `GROQ_MODEL` is a model available in your Groq account.
6. Deploy and test `/health`, then generate a pack from a public YouTube video with captions.

## Features
- Overview dashboard and study stats
- Generate notes, questions, answers and flashcards from YouTube videos
- Side-by-side YouTube player and generated content
- Editable personal notes, timestamp placeholder, copy and download
- Local library, search, collections, flashcard review
- Quiz question review, JSON backup/import, text export
- 25-minute focus timer
- Responsive mobile layout

## Current storage limitation
This starter stores saved study packs, personal notes and collections in the current browser's local storage. They are not cloud-synced and there is no account login yet. For a production multi-user service, add authentication, a database, per-user access controls, rate limiting and privacy/data deletion policies.
