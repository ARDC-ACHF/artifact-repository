"use strict";

// Minimal vanilla-JS frontend for cross-domain search.
// It talks to the same-origin API: /api/v1/search, /api/v1/artifacts.

const els = {
  form: document.getElementById("search-form"),
  q: document.getElementById("q"),
  type: document.getElementById("type"),
  partner: document.getElementById("partner"),
  meta: document.getElementById("meta"),
  results: document.getElementById("results"),
  empty: document.getElementById("empty"),
  overlay: document.getElementById("overlay"),
  close: document.getElementById("close"),
  dLabel: document.getElementById("d-label"),
  dType: document.getElementById("d-type"),
  dPartner: document.getElementById("d-partner"),
  dOrigin: document.getElementById("d-origin"),
  dVersions: document.getElementById("d-versions"),
  dBody: document.getElementById("d-body"),
};

// Convert an ISO timestamp into a short human-readable relative label.
function relativeTime(isoString) {
  const then = Date.parse(isoString);
  if (Number.isNaN(then)) return "";
  const diffMs = Date.now() - then;
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 5) return "just now";
  const units = [
    ["y", 365 * 24 * 3600],
    ["mo", 30 * 24 * 3600],
    ["d", 24 * 3600],
    ["h", 3600],
    ["m", 60],
    ["s", 1],
  ];
  for (const [label, secs] of units) {
    const value = Math.floor(Math.abs(diffSec) / secs);
    if (value >= 1) {
      return diffSec >= 0 ? `${value}${label} ago` : `in ${value}${label}`;
    }
  }
  return "just now";
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// Registry of every IRI known to this repository (id -> artifact summary row),
// used to turn inline PIDs found in a snapshot's JSON body into clickable links.
const knownArtifacts = new Map();

// Populate the type/partner filter dropdowns from everything indexed.
async function initFilters() {
  try {
    const data = await fetchJSON("/api/v1/artifacts?limit=500");
    const types = new Set();
    const partners = new Set();
    for (const row of data.results) {
      if (row.type) types.add(row.type);
      if (row.partner) partners.add(row.partner);
      if (row.id) knownArtifacts.set(row.id, row);
    }
    fillSelect(els.type, [...types].sort(), "All types");
    fillSelect(els.partner, [...partners].sort(), "All partners");
  } catch (e) {
    /* filters are optional; ignore */
  }
}

function fillSelect(select, values, allLabel) {
  select.innerHTML = "";
  const all = document.createElement("option");
  all.value = "";
  all.textContent = allLabel;
  select.appendChild(all);
  for (const v of values) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    select.appendChild(opt);
  }
}

function buildQuery() {
  const params = new URLSearchParams();
  const q = els.q.value.trim();
  const type = els.type.value;
  const partner = els.partner.value;
  if (q) {
    params.set("q", q);
    if (type) params.append("type", type);
    if (partner) params.append("partner", partner);
    return { path: "/api/v1/search?" + params.toString(), mode: "search" };
  }
  // No free text -> list everything (optionally filtered).
  if (type) params.append("type", type);
  if (partner) params.append("partner", partner);
  params.set("limit", "500");
  return { path: "/api/v1/artifacts?" + params.toString(), mode: "list" };
}

async function doSearch(event) {
  if (event) event.preventDefault();
  const { path } = buildQuery();
  els.results.innerHTML = "";
  els.empty.hidden = true;
  try {
    const data = await fetchJSON(path);
    render(data.results || [], data.total ?? (data.results || []).length);
  } catch (e) {
    els.meta.textContent = "Error: " + e.message;
  }
}

function render(results, total) {
  els.meta.textContent = `${total} result${total === 1 ? "" : "s"}`;
  els.results.innerHTML = "";
  if (!results.length) {
    els.empty.hidden = false;
    return;
  }
  for (const row of results) {
    const li = document.createElement("li");
    li.className = "card";
    li.addEventListener("click", () => openDetail(row));

    const h3 = document.createElement("h3");
    h3.textContent = row.label || row.id;
    li.appendChild(h3);

    const chips = document.createElement("div");
    chips.className = "chips";
    chips.appendChild(chip("type", row.type));
    chips.appendChild(chip("partner", row.partner));
    li.appendChild(chips);

    els.results.appendChild(li);
  }
}

function chip(cls, text) {
  const span = document.createElement("span");
  span.className = "chip " + cls;
  span.textContent = text;
  return span;
}

async function openDetail(row) {
  els.dLabel.textContent = row.label || row.id;
  els.dType.textContent = row.type;
  els.dPartner.textContent = row.partner;
  els.dOrigin.href = row.id;
  els.dOrigin.textContent = "Open original IRI: " + row.id + " ↗";
  els.dVersions.innerHTML = "";
  els.dBody.textContent = "Loading…";
  els.overlay.classList.add("open");
  // Load the current version body first, then the version history.
  await loadVersionBody(row.locator);
  await loadVersions(row.locator);
}

// Fetch and render an artifact's version history; wire up snapshot loading.
async function loadVersions(locator) {
  try {
    const data = await fetchJSON(locator + "/versions");
    const versions = data.versions || [];
    if (versions.length <= 1) {
      // Single version: nothing meaningful to show as history.
      els.dVersions.innerHTML = "";
      return;
    }
    const wrap = document.createElement("div");
    const h = document.createElement("h3");
    h.textContent = `Version history (${data.total})`;
    wrap.appendChild(h);

    const ul = document.createElement("ul");
    ul.className = "version-list";
    for (const v of versions) {
      const li = document.createElement("li");
      li.className = "version";
      li.dataset.locator = v.locator;

      const date = document.createElement("span");
      date.className = "date";
      date.textContent = v.published_at;
      li.appendChild(date);

      const rel = document.createElement("span");
      rel.className = "relative";
      rel.textContent = relativeTime(v.published_at);
      li.appendChild(rel);

      if (v.is_current) {
        const badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = "current";
        li.appendChild(badge);
      }

      const permalink = document.createElement("a");
      permalink.className = "permalink";
      permalink.href = v.locator;
      permalink.target = "_blank";
      permalink.rel = "noopener noreferrer";
      permalink.textContent = "↗ link";
      permalink.addEventListener("click", (e) => {
        e.stopPropagation();
      });
      li.appendChild(permalink);

      li.addEventListener("click", () => {
        setActiveVersion(li);
        loadVersionBody(v.locator);
      });
      ul.appendChild(li);
      if (v.is_current) setActiveVersion(li);
    }
    wrap.appendChild(ul);
    els.dVersions.innerHTML = "";
    els.dVersions.appendChild(wrap);
  } catch (e) {
    els.dVersions.innerHTML = "";
  }
}

function setActiveVersion(activeLi) {
  const items = els.dVersions.querySelectorAll("li.version");
  items.forEach((li) => {
    li.classList.toggle("active", li === activeLi);
    const badge = li.querySelector(".badge.viewing");
    if (badge && li !== activeLi) badge.remove();
  });
  if (activeLi && !activeLi.querySelector(".badge.viewing")) {
    const badge = document.createElement("span");
    badge.className = "badge viewing";
    badge.textContent = "viewing";
    activeLi.appendChild(badge);
  }
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// Pretty-print JSON and turn any quoted string value that matches a known
// repository IRI (e.g. a "carried_out_by" id) into a clickable in-page link.
function renderBodyWithPidLinks(parsed) {
  const escaped = escapeHtml(JSON.stringify(parsed, null, 2));
  return escaped.replace(/"((?:https?:)\/\/[^"]*)"/g, (match, iri) => {
    if (!knownArtifacts.has(iri)) return match;
    return `"<a href="#" class="pid-link" data-iri="${iri}" title="Open ${iri} in this repository">${iri}</a>"`;
  });
}

async function loadVersionBody(locator) {
  els.dBody.textContent = "Loading…";
  try {
    const res = await fetch(locator);
    const text = await res.text();
    try {
      els.dBody.innerHTML = renderBodyWithPidLinks(JSON.parse(text));
    } catch {
      els.dBody.textContent = text;
    }
  } catch (e) {
    els.dBody.textContent = "Failed to load artifact: " + e.message;
  }
}

function closeDetail() {
  els.overlay.classList.remove("open");
}

els.form.addEventListener("submit", doSearch);
els.type.addEventListener("change", doSearch);
els.partner.addEventListener("change", doSearch);
els.close.addEventListener("click", closeDetail);
els.overlay.addEventListener("click", (e) => {
  if (e.target === els.overlay) closeDetail();
});

// Clicking an inline PID link opens that entity's own detail view.
els.dBody.addEventListener("click", (e) => {
  const link = e.target.closest("a.pid-link");
  if (!link) return;
  e.preventDefault();
  const row = knownArtifacts.get(link.dataset.iri);
  if (row) openDetail(row);
});

// Initial load: populate filters and show everything.
initFilters().then(doSearch);
