# LectureLift — public YouTube lecture study website

LectureLift generates lecture notes, university-style practice questions, answer explanations, and flashcards from a YouTube transcript.

## What works in this project
- Responsive website for mobile and desktop.
- Accepts YouTube watch, short, embed and Shorts links.
- Tries to retrieve available captions with `youtube-transcript-api`.
- Lets a user paste the transcript when automatic retrieval fails.
- Sends the transcript to an AI model on the server and displays the returned study pack.
- Keeps the AI API key on the server, not in browser JavaScript.
- Includes a basic per-IP request limit (default: 5 generations/hour/IP).

## Important transcript limitation
A YouTube URL is not the same as a transcript. The app can automatically retrieve captions only when captions are available and the transcript service can access them. Some videos have no captions, and YouTube may block or rate-limit automated transcript retrieval. The fallback is to open the video on YouTube, select **Show transcript** (if available), copy it, and paste it into LectureLift.

Do not attempt to bypass access controls. For a more dependable large-scale service, consider a legitimate caption/transcription provider with terms that allow this use.

## Publish online (Render + GitHub)

You need your own GitHub account and hosting account. I cannot publish it into your accounts without your login/authorization.

1. Download and unzip `LectureLift_Public.zip`.
2. In GitHub, create a **new public repository** named `lecturelift` (or another name).
3. Upload the files from this folder to the repository root. Ensure `index.html`, `server.py`, `requirements.txt`, and `render.yaml` are at the root, not inside an extra nested folder.
4. Create an account at Render and choose **New → Web Service**. Connect the `lecturelift` repository.
5. Render should detect the included `render.yaml`. If asked to enter settings manually:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn server:app`
6. In the Render service dashboard, open **Environment** and add:
   - Key: `OPENAI_API_KEY`
   - Value: your secret API key from your AI provider account
   - Optional key `OPENAI_MODEL`, value `gpt-4o-mini` (or a model available to your API account)
7. Save and deploy. Open the public `onrender.com` URL shown in the dashboard.
8. Test `/health` at the end of the URL; it should show `{"status":"ok"}`. Then test a video with captions and one where you paste the transcript.

## Security and operating costs
- Never paste an API key into `index.html`, a public GitHub file, or a message.
- The included 5-per-hour IP limit is a basic starting point, not complete abuse prevention. For a larger public launch, use persistent rate-limit storage such as Redis, monitoring, stricter quotas, and possibly student sign-in.
- AI API usage may cost money. Set a budget/usage alert with your AI provider before sharing the site widely.
- The default in-memory rate-limit storage resets when the server restarts and is not shared across multiple server instances. Set `RATELIMIT_STORAGE_URI` to a managed Redis URL for persistent, shared limits.
- Do not promise perfect notes. Students should check output against course slides and assigned readings.

## Run locally
Python 3.10+ recommended.

```bash
pip install -r requirements.txt
```

Set the key in your terminal, never in source code.

macOS/Linux:
```bash
export OPENAI_API_KEY="your-secret-key"
python server.py
```

Windows PowerShell:
```powershell
$env:OPENAI_API_KEY="your-secret-key"
python server.py
```

Then open http://127.0.0.1:5000

## Environment variables
- `OPENAI_API_KEY` — required for generation.
- `OPENAI_MODEL` — optional; defaults to `gpt-4o-mini`.
- `GENERATE_LIMIT` — optional; defaults to `5 per hour`.
- `RATELIMIT_STORAGE_URI` — optional; defaults to in-memory storage.

## Copyright / academic integrity
Use videos and transcripts you are permitted to use. LectureLift is for learning and revision; check generated facts and follow your institution's rules on AI use.
