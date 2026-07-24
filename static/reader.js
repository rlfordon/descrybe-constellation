// descrybe-constellation: case-reader view (ux-spec.md Phase 3). Swaps the
// Case tab's #case-card for #case-reader on "Read case" -- sticky mini-
// header (back/PDF/passage nav), a [Needs verification] block for
// unanchorable passages above the opinion, and the sanitized opinion body
// with server-injected highlight markup. Vanilla JS, classic script (no
// modules) loaded after app.js -- shares its top-level globals ($, getJSON,
// setStatus, switchTab, currentGraph) via the same global scope.

let readerState = null; // { caseId, anchored: [{n, ...}], activeIndex }

function passageElementFor(n) {
  // Server marks exact hits with <mark class="passage-hit" data-passage="N">
  // and normalized/fuzzy hits with the enclosing paragraph's
  // class="passage-para" data-passage="N ..." (space-separated when a
  // paragraph carries more than one passage) -- either shape matches here.
  return document.querySelector(`#reader-body [data-passage~="${n}"]`);
}

function escapeForDisplay(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : text;
  return div.innerHTML;
}

function renderUnanchored(unanchored) {
  const el = $("reader-unanchored");
  if (!unanchored || !unanchored.length) {
    el.style.display = "none";
    el.innerHTML = "";
    return;
  }
  el.style.display = "block";
  el.innerHTML = unanchored.map((p) => (
    '<div class="nv-passage">' +
    '<p class="nv-label">[Needs verification] &mdash; passage returned by Descrybe ' +
    "but not located in the CourtListener text</p>" +
    `<p class="nv-text">${escapeForDisplay(p.text)}</p>` +
    "</div>"
  )).join("");
}

function updatePassageCounter() {
  const el = $("reader-passage-counter");
  if (!readerState || !readerState.anchored.length) {
    el.textContent = "no located passages";
    return;
  }
  el.textContent = `passage ${readerState.activeIndex + 1} of ${readerState.anchored.length}`;
}

function buildReaderGutter() {
  const gutter = $("reader-gutter");
  gutter.innerHTML = "";
  if (!readerState || !readerState.anchored.length) return;
  const body = $("reader-body");
  // Layout settles after innerHTML swap -- measure on the next frame so
  // offsetTop/scrollHeight reflect the just-rendered document (same
  // discipline as the timeline axis fix: never compute positions from a
  // stale layout).
  requestAnimationFrame(() => {
    const total = body.scrollHeight || 1;
    readerState.anchored.forEach((p, i) => {
      const el = passageElementFor(p.n);
      if (!el) return;
      const tick = document.createElement("div");
      tick.className = "reader-tick";
      tick.style.top = `${((el.offsetTop / total) * 100).toFixed(2)}%`;
      tick.title = `passage ${i + 1} of ${readerState.anchored.length}`;
      tick.addEventListener("click", () => jumpToPassage(i));
      gutter.appendChild(tick);
    });
  });
}

function jumpToPassage(index) {
  if (!readerState || !readerState.anchored.length) return;
  readerState.activeIndex = (index + readerState.anchored.length) % readerState.anchored.length;
  updatePassageCounter();
  const p = readerState.anchored[readerState.activeIndex];
  const el = passageElementFor(p.n);
  if (!el) return;
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  el.classList.remove("passage-pulse");
  void el.offsetWidth; // restart the CSS animation when jumping to the same element again
  el.classList.add("passage-pulse");
}

async function openReader(caseId) {
  setStatus(`loading reader for ${caseId}...`);
  const node = currentGraph.nodes.find((n) => n.case_id === caseId) || {};
  try {
    const data = await getJSON(`/api/case/${caseId}/reader`);
    $("case-card").style.display = "none";
    $("case-empty").style.display = "none";
    $("case-reader").style.display = "flex";
    $("reader-case-name").textContent = node.label || caseId;
    $("reader-pdf-btn").dataset.caseId = caseId;
    $("reader-body").innerHTML = data.html;
    renderUnanchored(data.unanchored);

    const anchored = (data.passages || []).filter((p) => p.status !== "unanchorable");
    readerState = { caseId, anchored, activeIndex: 0 };
    updatePassageCounter();
    buildReaderGutter();
    if (anchored.length) jumpToPassage(0);
    setStatus("");
  } catch (e) {
    setStatus(String(e));
  }
}

$("read-case-btn").addEventListener("click", () => {
  const caseId = $("case-card").dataset.caseId;
  if (caseId) openReader(caseId);
});

$("reader-back").addEventListener("click", () => {
  $("case-reader").style.display = "none";
  $("case-card").style.display = "block";
});

$("reader-prev").addEventListener("click", () => {
  jumpToPassage((readerState ? readerState.activeIndex : 0) - 1);
});

$("reader-next").addEventListener("click", () => {
  jumpToPassage((readerState ? readerState.activeIndex : 0) + 1);
});

$("reader-pdf-btn").addEventListener("click", async () => {
  const caseId = $("reader-pdf-btn").dataset.caseId;
  if (!caseId) return;
  setStatus("fetching official PDF link...");
  try {
    const data = await getJSON(`/api/case/${caseId}/pdf`);
    const match = (data.raw || "").match(/https?:\/\/\S+/);
    if (match) {
      window.open(match[0].replace(/[),.]+$/, ""), "_blank");
    } else {
      setStatus("no PDF URL found in the Descrybe response");
      return;
    }
  } catch (e) {
    setStatus(String(e));
    return;
  }
  setStatus("");
});
