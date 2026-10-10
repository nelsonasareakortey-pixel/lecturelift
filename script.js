const transcriptInput = document.querySelector("#transcript");
const generateButton = document.querySelector("#generate");
const statusEl = document.querySelector("#status");
const resultsEl = document.querySelector("#results");
const notesEl = document.querySelector("#notes");

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function addList(parent, title, items) {
  if (!Array.isArray(items) || !items.length) return;
  parent.append(element("h3", "", title));
  const list = element("ul");
  items.forEach((item) => {
    const value = typeof item === "string" ? item :
      (item.question ? `${item.question}${item.answer ? " — " + item.answer : ""}` : JSON.stringify(item));
    list.append(element("li", "", value));
  });
  parent.append(list);
}

function renderNotes(notes) {
  notesEl.replaceChildren();
  const intro = element("article", "note-card");
  intro.append(element("h2", "", notes.title || "Your study notes"));
  if (notes.overview) intro.append(element("p", "", notes.overview));
  addList(intro, "Learning objectives", notes.learningObjectives);
  notesEl.append(intro);

  (notes.sections || []).forEach((section) => {
    const card = element("article", "note-card");
    card.append(element("h2", "", section.heading || "Study section"));
    if (section.videoContent) {
      card.append(element("span", "tag", "From the video"));
      card.append(element("p", "", section.videoContent));
    }
    if (section.explanation) {
      card.append(element("span", "tag", "Expanded explanation"));
      card.append(element("p", "", section.explanation));
    }
    addList(card, "Important points", section.importantPoints);
    addList(card, "Examples", section.examples);
    addList(card, "Image ideas", section.imageSuggestions);
    const search = element("form", "image-search");
    const input = element("input");
    input.type = "search";
    input.placeholder = "Search images for this section";
    input.value = section.heading || "";
    input.setAttribute("aria-label", "Image search query");
    const button = element("button", "", "Find images");
    button.type = "submit";
    search.append(input, button);
    search.addEventListener("submit", async (event) => {
      event.preventDefault();
      await searchImages(input.value, card);
    });
    card.append(search);
    notesEl.append(card);
  });

  addGenericSection(notesEl, "Key terms", notes.keyTerms);
  addGenericSection(notesEl, "Supplementary AI information", notes.supplementaryInformation);
  if (notes.summary) {
    const card = element("article", "note-card");
    card.append(element("h2", "", "Summary"), element("p", "", notes.summary));
    notesEl.append(card);
  }
  addGenericSection(notesEl, "Revision questions and answers", notes.revisionQuestions);
}

function addGenericSection(parent, title, items) {
  if (!items || (Array.isArray(items) && !items.length)) return;
  const card = element("article", "note-card");
  card.append(element("h2", "", title));
  if (Array.isArray(items)) {
    const list = element("ul");
    items.forEach((item) => {
      if (typeof item === "string") list.append(element("li", "", item));
      else {
        const label = item.term || item.question || item.title || "";
        const detail = item.definition || item.answer || item.explanation || item.description || "";
        const li = element("li");
        li.append(element("strong", "", label));
        if (detail) li.append(document.createTextNode(` — ${detail}`));
        list.append(li);
      }
    });
    card.append(list);
  } else {
    card.append(element("p", "", String(items)));
  }
  parent.append(card);
}

async function searchImages(query, card) {
  const existing = card.querySelector(".image-results");
  if (existing) existing.remove();
  const holder = element("div", "image-results");
  holder.append(element("p", "", "Searching for relevant images…"));
  card.append(holder);
  try {
    const response = await fetch(`/api/search-images?q=${encodeURIComponent(query)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Image search failed");
    holder.replaceChildren();
    if (!data.images?.length) {
      holder.append(element("p", "", "No images found for this search."));
      return;
    }
    data.images.forEach((image) => {
      const item = element("div", "image-result");
      const link = element("a", "", image.title || "Open image source");
      link.href = image.sourceUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const img = document.createElement("img");
      img.src = image.imageUrl;
      img.alt = image.title || query;
      img.loading = "lazy";
      const meta = element("p", "image-meta", `License: ${image.license}. Attribution: ${image.attribution}. Check the source page before reuse.`);
      item.append(link, img, meta);
      holder.append(item);
    });
  } catch (error) {
    holder.replaceChildren(element("p", "", error.message));
  }
}

generateButton.addEventListener("click", async () => {
  const transcript = transcriptInput.value.trim();
  if (!transcript) {
    statusEl.textContent = "Paste a transcript first. Connect your existing YouTube transcript extractor here.";
    transcriptInput.focus();
    return;
  }

  generateButton.disabled = true;
  statusEl.textContent = "Generating detailed notes…";
  resultsEl.hidden = true;

  try {
    const response = await fetch("/api/generate-notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcript,
        educationLevel: document.querySelector("#educationLevel").value,
        detailLevel: document.querySelector("#detailLevel").value
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not generate notes.");
    renderNotes(data.notes);
    resultsEl.hidden = false;
    statusEl.textContent = "Your notes are ready. Use the image search fields to find supporting visuals.";
  } catch (error) {
    statusEl.textContent = error.message;
  } finally {
    generateButton.disabled = false;
  }
});
