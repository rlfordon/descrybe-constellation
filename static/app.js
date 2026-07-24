// descrybe-constellation: vanilla-JS three-pane UI. No framework, no build step.

const COLORS = { search: "#4a90d9", backward: "#d9984a", forward: "#6bbf6b" };
let cy = null;
let currentGraph = { nodes: [], edges: [] };
let clusters = [];
let corpusBuilt = false;

function $(id) { return document.getElementById(id); }

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${url}: ${r.status} ${await r.text()}`);
  return r.json();
}

async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status} ${await r.text()}`);
  return r.json();
}

function setStatus(text) { $("status-line").textContent = text || ""; }

// ------------------------------------------------------------- variants

function addVariantInput(value) {
  const row = document.createElement("input");
  row.type = "text";
  row.className = "variant-input";
  row.placeholder = "search variant";
  row.value = value || "";
  $("variant-list").appendChild(row);
}

function getVariants() {
  return Array.from(document.querySelectorAll(".variant-input"))
    .map((i) => i.value.trim())
    .filter(Boolean);
}

$("add-variant").addEventListener("click", () => addVariantInput());
$("threshold").addEventListener("input", (e) => {
  $("threshold-value").textContent = e.target.value;
});

// --------------------------------------------------------------- search

$("search-btn").addEventListener("click", async () => {
  const seed = $("seed").value.trim();
  if (!seed) return setStatus("enter a seed issue first");
  setStatus("searching...");
  try {
    const body = {
      seed,
      jurisdiction: $("jurisdiction").value.trim() || null,
      variants: getVariants(),
      harvest_labels: $("harvest-labels").checked,
      threshold: parseFloat($("threshold").value),
    };
    const resp = await postJSON("/api/search", body);
    clusters = resp.clusters;
    renderClusters();
    $("build-corpus-btn").disabled = false;
    setStatus(`found ${clusters.length} search cluster(s)`);
  } catch (e) {
    setStatus(String(e));
  }
});

function renderClusters() {
  const box = $("clusters");
  box.innerHTML = "";
  clusters.forEach((c, idx) => {
    const chip = document.createElement("span");
    chip.className = "chip " + (c.included ? "included" : "excluded");
    chip.textContent = `${c.terms.join(" / ")} (${c.case_ids.length}, overlap ${c.seed_overlap})`;
    chip.addEventListener("click", () => {
      clusters[idx].included = !clusters[idx].included;
      renderClusters();
    });
    box.appendChild(chip);
  });
}

// --------------------------------------------------------------- corpus

$("build-corpus-btn").addEventListener("click", async () => {
  const includedTerms = clusters.filter((c) => c.included).flatMap((c) => c.terms);
  if (!includedTerms.length) return setStatus("include at least one search cluster");
  setStatus("building corpus...");
  try {
    const payload = await postJSON("/api/corpus", { included_terms: includedTerms });
    corpusBuilt = true;
    $("hop-backward").disabled = false;
    $("hop-forward").disabled = false;
    renderGraph(payload);
    setStatus(`corpus: ${payload.nodes.length} cases, ${payload.edges.length} edges`);
  } catch (e) {
    setStatus(String(e));
  }
});

// ----------------------------------------------------------------- hops

function updateCallsHint() {
  const n = currentGraph.nodes.length;
  $("calls-hint").textContent = n ? `≈ ${n} call(s) per hop (node-count based)` : "";
}

$("hop-backward").addEventListener("click", async () => {
  setStatus("running backward hop...");
  try {
    const payload = await postJSON("/api/expand", { direction: "backward" });
    renderGraph(payload);
    setStatus(`backward hop done: ${payload.nodes.length} cases, ${payload.edges.length} edges`);
  } catch (e) {
    setStatus(String(e));
  }
});

$("hop-forward").addEventListener("click", async () => {
  const cap = parseInt($("forward-cap").value, 10) || 10;
  setStatus("running forward hop...");
  try {
    const payload = await postJSON("/api/expand", { direction: "forward", forward_cap: cap });
    renderGraph(payload);
    let msg = `forward hop done: ${payload.nodes.length} cases, ${payload.edges.length} edges`;
    if (payload.truncation_notes && payload.truncation_notes.length) {
      msg += "\n" + payload.truncation_notes.join("\n");
    }
    setStatus(msg);
  } catch (e) {
    setStatus(String(e));
  }
});

// ---------------------------------------------------------------- graph

function nodeSizer(nodes) {
  const max = Math.max(1, ...nodes.map((n) => n.cited_by_corpus || 0));
  return (n) => 18 + (60 - 18) * ((n.cited_by_corpus || 0) / max);
}

function renderGraph(payload) {
  currentGraph = { nodes: payload.nodes, edges: payload.edges };
  updateCallsHint();
  renderLeadingTab(payload.ranked_top || [], payload.foundational || []);

  const size = nodeSizer(payload.nodes);
  const elements = payload.nodes.map((n) => ({ data: { id: String(n.id), node: n, label: n.label } }))
    .concat(payload.edges.map(([src, dst]) => ({ data: { source: String(src), target: String(dst) } })));

  if (cy) cy.destroy();
  cy = cytoscape({
    container: $("cy"),
    elements,
    layout: { name: "cose" },
    style: [
      { selector: "node", style: {
          "background-color": (ele) => COLORS[ele.data("node").origin] || "#999",
          "width": (ele) => size(ele.data("node")),
          "height": (ele) => size(ele.data("node")),
          "border-width": (ele) => (ele.data("node").foundational ? 4 : 0),
          "border-color": "#7b3fa0",
          "label": "data(label)", "font-size": 8, "color": "#333",
          "text-valign": "bottom", "text-wrap": "ellipsis", "text-max-width": "90px",
      } },
      { selector: "edge", style: {
          "width": 1, "line-color": "#bbb", "target-arrow-color": "#bbb",
          "target-arrow-shape": "triangle", "curve-style": "bezier",
      } },
    ],
  });
  cy.on("tap", "node", (evt) => loadCase(evt.target.data("node").case_id));
}

function renderLeadingTab(rankedTop, foundational) {
  const tbody = document.querySelector("#ranked-table tbody");
  tbody.innerHTML = "";
  rankedTop.slice(0, 15).forEach((n) => {
    const tr = document.createElement("tr");
    tr.className = "row-clickable";
    tr.innerHTML = `<td>${n.cited_by_corpus}</td><td>${n.search_membership}</td>` +
      `<td>${n.court_weight}</td><td>${n.name}</td><td>${n.date || ""}</td>`;
    tr.addEventListener("click", () => loadCase(n.case_id));
    tbody.appendChild(tr);
  });

  const list = $("foundational-list");
  list.innerHTML = "";
  foundational.forEach((n) => {
    const li = document.createElement("li");
    li.textContent = `${n.name} (${n.date || "?"}) — cited by ${n.cited_by_corpus}`;
    li.addEventListener("click", () => loadCase(n.case_id));
    list.appendChild(li);
  });
}

// ----------------------------------------------------------------- case

async function loadCase(caseId, focus) {
  setStatus(`loading ${caseId}...`);
  switchTab("case");
  try {
    const url = focus ? `/api/case/${caseId}?focus=${encodeURIComponent(focus)}` : `/api/case/${caseId}`;
    const data = await getJSON(url);
    const node = currentGraph.nodes.find((n) => n.case_id === caseId) || {};
    $("case-empty").style.display = "none";
    $("case-card").style.display = "block";
    $("case-name").textContent = node.label || caseId;
    $("case-meta").innerHTML = `<span class="tag">[CourtListener]</span> ` +
      `${node.court || "?"} &mdash; ${node.date || "?"} &mdash; origin: ${node.origin || "?"}`;
    $("case-numbers").innerHTML = `<span class="tag">[CourtListener]</span> ` +
      `cited-by-corpus: ${node.cited_by_corpus ?? "?"}; searches: ${node.search_membership ?? "?"}`;
    $("case-treatment").innerHTML = (node.treatment || node.research_value)
      ? `<span class="tag">[Descrybe]</span> ${node.research_value || ""} ${node.treatment || ""}`
      : "";
    $("case-summary").textContent = data.summary || "";
    $("case-status").innerHTML = `<span class="tag">[Descrybe]</span> ${data.status || ""}`;
    $("case-passage").innerHTML = data.passage
      ? `<span class="tag">[Descrybe]</span> ${data.passage}`
      : "";
    $("case-card").dataset.caseId = caseId;
    setStatus("");
  } catch (e) {
    setStatus(String(e));
  }
}

$("focus-btn").addEventListener("click", () => {
  const caseId = $("case-card").dataset.caseId;
  const focus = $("focus-input").value.trim();
  if (caseId && focus) loadCase(caseId, focus);
});

// ------------------------------------------------------------------ tabs

function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === `tab-${name}`));
}

document.querySelectorAll(".tab-btn").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

// ---------------------------------------------------------------- export

$("export-trail").addEventListener("click", () => window.open("/api/export/trail", "_blank"));
$("export-snapshot").addEventListener("click", () => window.open("/api/export/snapshot", "_blank"));

// ----------------------------------------------------------------- init

addVariantInput();
