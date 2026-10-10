require("dotenv").config();

const express = require("express");
const Groq = require("groq-sdk");

const app = express();
const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });

app.use(express.json({ limit: "1mb" }));
app.use(express.static("public"));

function safeText(value, maxLength = 60000) {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : "";
}

app.post("/api/generate-notes", async (req, res) => {
  try {
    const transcript = safeText(req.body?.transcript);
    const educationLevel = safeText(req.body?.educationLevel, 80) || "general student";
    const detailLevel = safeText(req.body?.detailLevel, 80) || "comprehensive";

    if (!transcript) {
      return res.status(400).json({ error: "A video transcript is required." });
    }
    if (transcript.length > 60000) {
      return res.status(413).json({
        error: "Transcript is too long for this starter endpoint. Split it into chunks first."
      });
    }
    if (!process.env.GROQ_API_KEY || !process.env.GROQ_MODEL) {
      return res.status(500).json({
        error: "Server is missing GROQ_API_KEY or GROQ_MODEL environment variables."
      });
    }

    const completion = await groq.chat.completions.create({
      model: process.env.GROQ_MODEL,
      temperature: 0.3,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content: `You are LectureLift, an expert educational tutor.
Create accurate, comprehensive, well-organized study notes from a YouTube transcript.
Clearly distinguish what the video says from supplementary AI explanations.
Do not claim supplementary material was said in the video. Do not invent facts, quotes,
citations, statistics, or sources. Flag uncertain claims and suggest verification when needed.
Explain difficult ideas step by step. Include definitions, examples, key terms, learning objectives,
common misconceptions, key takeaways, a summary, and revision questions with answers.
Suggest relevant visuals and search phrases for suitable sections.
Return valid JSON with these keys:
title, overview, learningObjectives, sections, keyTerms,
supplementaryInformation, summary, revisionQuestions, imageSuggestions.
Each section should include heading, videoContent, explanation, importantPoints, examples,
and imageSuggestions. Keep the result useful and avoid repetition.`
        },
        {
          role: "user",
          content: `Education level: ${educationLevel}
Detail level: ${detailLevel}

Create the study notes from this transcript:
${transcript}`
        }
      ]
    });

    const content = completion.choices?.[0]?.message?.content;
    if (!content) throw new Error("The AI returned an empty response.");

    return res.json({ notes: JSON.parse(content) });
  } catch (error) {
    console.error("Note generation failed:", error.message);
    return res.status(500).json({
      error: "Could not generate notes. Check the server logs and Groq configuration."
    });
  }
});

app.get("/api/search-images", async (req, res) => {
  try {
    const query = safeText(req.query.q, 150);
    if (!query) {
      return res.status(400).json({ error: "Enter an image search query." });
    }

    const params = new URLSearchParams({
      action: "query",
      generator: "search",
      gsrsearch: query + " filetype:bitmap",
      gsrnamespace: "6",
      gsrlimit: "6",
      prop: "imageinfo",
      iiprop: "url|extmetadata",
      iiurlwidth: "800",
      format: "json",
      origin: "*"
    });

    const response = await fetch(
      "https://commons.wikimedia.org/w/api.php?" + params.toString(),
      { headers: { "User-Agent": "LectureLift/1.0 (educational notes website)" } }
    );

    if (!response.ok) throw new Error("Wikimedia image search failed.");
    const data = await response.json();
    const pages = Object.values(data.query?.pages || {});

    const images = pages.map((page) => {
      const info = page.imageinfo?.[0];
      if (!info?.url) return null;
      const meta = info.extmetadata || {};
      return {
        title: page.title,
        imageUrl: info.thumburl || info.url,
        sourceUrl: info.descriptionurl,
        license: meta.LicenseShortName?.value || "Check source page",
        attribution: meta.Artist?.value || "See source page"
      };
    }).filter(Boolean);

    res.json({ images });
  } catch (error) {
    console.error("Image search failed:", error.message);
    res.status(500).json({ error: "Could not search for images right now." });
  }
});

const PORT = process.env.PORT || 10000;
app.listen(PORT, "0.0.0.0", () => {
  console.log(`LectureLift starter backend running on port ${PORT}`);
});
