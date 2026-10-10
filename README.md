# LectureLift upgrade starter

This is a starter project for upgrading a YouTube-to-notes site with Groq-generated detailed notes and Wikimedia Commons image search.

## Important
This is a starter/demo, not a drop-in replacement for your existing deployed website. It does not extract YouTube transcripts itself. Paste a transcript into the demo, or connect your existing transcript extraction code to the notes endpoint. Back up your current project before merging these files.

## Run locally
1. Install a recent Node.js LTS release.
2. Run `npm install`.
3. Copy `.env.example` to `.env`.
4. Add a real Groq API key and a currently supported model name to `.env`.
5. Run `npm start`.
6. Open `http://localhost:10000`.

Never commit `.env` or expose the API key in frontend code.

## Render
Deploy as a Render Web Service. Build command: `npm install`. Start command: `npm start`. Add `GROQ_API_KEY` and `GROQ_MODEL` in the Render service Environment settings.

If your existing site is a Render Static Site, you can keep it separate and deploy this backend as a Web Service. In that case, change frontend fetch URLs to the backend URL and configure CORS on the server.

## Current features
- `/api/generate-notes`: uses Groq to generate structured JSON study notes.
- `/api/search-images?q=...`: searches Wikimedia Commons and returns image URLs and attribution/licensing metadata.
- Simple responsive frontend to test note rendering and image search.

## Before production
- Add authentication or rate limiting to prevent API abuse and unexpected costs.
- Add transcript chunking for long videos.
- Validate model output schema and handle malformed JSON.
- Review image licenses and attribution requirements.
- Configure CORS carefully if frontend and backend are on different origins.
- Add an image-generation provider if you want newly generated images; Groq alone does not generate images.
- Connect the endpoint to your existing YouTube transcript extraction workflow.
