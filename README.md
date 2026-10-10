# LectureLift — Groq deployment package

LectureLift creates lecture notes, practice questions, answer keys and flashcards from YouTube lecture transcripts.

## Important limitation

Automatic YouTube transcript retrieval is best-effort. YouTube can block requests from cloud-hosting IP addresses even when other transcript websites work. This version:
- tries automatic transcript retrieval;
- clearly explains when retrieval fails;
- accepts a transcript pasted into the website;
- logs useful server diagnostics in Render;
- returns helpful error messages instead of hiding most failures.

No code can guarantee that YouTube will allow transcript retrieval from every cloud server. The paste-transcript fallback is therefore included intentionally.

## Groq API configuration

This backend uses the OpenAI-compatible Groq endpoint `https://api.groq.com/openai/v1`.

## Deploy/update on Render

1. Back up your current GitHub repository.
2. Replace the repository's `index.html`, `server.py`, `requirements.txt`, `render.yaml`, `.gitignore`, and `README.md` with the files in this package. Keep all files in the repository root, not inside an extra nested folder.
3. Commit the changes to GitHub.
4. In Render, open your existing LectureLift web service and confirm it is connected to that repository. Render should redeploy after the commit.
5. In Render → service → Environment, set:
   - `GROQ_API_KEY` = your secret API key (enter it only in Render; never commit it to GitHub)
   - `GROQ_MODEL` = `llama-3.3-70b-versatile` if your API account has access to that model
6. Check that the service is healthy at `/health`, for example `https://YOUR-SERVICE.onrender.com/health`.
7. Test generation with a short transcript you pasted into the Transcript box. Then test automatic retrieval separately.

## If it still fails

Open Render → service → Logs and look for:
- `Automatic transcript fetch failed` — YouTube retrieval failed; paste the transcript instead or integrate a transcript provider.
- `GROQ_API_KEY is missing` — add the secret in Render Environment.
- `Study pack generation failed` — inspect the following traceback; it may be API billing, model access, key or network configuration.
- `Transcript too short` — the transcript field was empty or contained less than 80 characters.

## Security and costs

- Never put API keys in `index.html`, GitHub, screenshots or this chat.
- Groq free-tier access has rate limits and may change; check the current limits in your Groq console. The website hosting and API service have separate terms.
- Add a spending limit or usage alert to your API provider account.
- The free Render instance may sleep while idle and take time to wake.
