/* 목업 데이터 기반 인터랙션. 백엔드 없이 브라우저에서 유사도 계산까지 직접 수행함
   (digger/similarity.py의 태그 코사인 유사도 로직을 그대로 옮김). */

const trackById = (id) => MOCK_TRACKS.find((t) => t.id === id);

function formatDuration(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function initials(artist) {
  const words = artist.trim().split(/\s+/);
  const letters = words.length === 1 ? words[0].slice(0, 2) : words.slice(0, 2).map((w) => w[0]).join("");
  return letters.toUpperCase();
}

/* ---------- 태그 벡터 / 코사인 유사도 (similarity.py 이식) ---------- */

function tagVector(track) {
  const vec = {};
  for (const tag of track.tags) {
    const key = tag.canonical_style || `raw:${tag.raw_tag}`;
    vec[key] = (vec[key] || 0) + (tag.weight ?? 1);
  }
  return vec;
}

function dot(a, b) {
  let sum = 0;
  for (const k in a) if (k in b) sum += a[k] * b[k];
  return sum;
}

function norm(a) {
  return Math.sqrt(dot(a, a));
}

function cosine(a, b) {
  const na = norm(a);
  const nb = norm(b);
  if (na === 0 || nb === 0) return 0;
  return dot(a, b) / (na * nb);
}

function topContributingTags(seedVec, otherVec, topN = 3) {
  const contributions = [];
  for (const k in seedVec) {
    if (k in otherVec) contributions.push([seedVec[k] * otherVec[k], k]);
  }
  contributions.sort((a, b) => b[0] - a[0]);
  return contributions.slice(0, topN).map(([, name]) => name);
}

function boredomPenaltyFactor(score, weight) {
  const normalized = score / (1 + score);
  return 1 - weight * normalized;
}

function rankSimilar(seedId, { boredomWeight = 0, excludeTiredAbove = null } = {}) {
  const seed = trackById(seedId);
  const seedVec = tagVector(seed);
  const results = MOCK_TRACKS.filter((t) => t.id !== seedId).map((t) => {
    const boredom = MOCK_BOREDOM_SCORES[t.id] ?? 0;
    const similarity = cosine(seedVec, tagVector(t));
    return {
      track: t,
      similarity,
      boredom,
      topFeatures: topContributingTags(seedVec, tagVector(t)),
    };
  });

  const filtered = excludeTiredAbove == null
    ? results
    : results.filter((r) => r.boredom <= excludeTiredAbove);

  const rankKey = boredomWeight > 0
    ? (r) => r.similarity * boredomPenaltyFactor(r.boredom, boredomWeight)
    : (r) => r.similarity;

  return filtered.sort((a, b) => rankKey(b) - rankKey(a));
}

/* ---------- 라이브러리 탭 ---------- */

function renderLibrary() {
  document.getElementById("track-count").textContent = MOCK_TRACKS.length;
  const grid = document.getElementById("library-grid");
  grid.innerHTML = MOCK_TRACKS.map((t) => `
    <article class="track-card glass">
      <div class="track-art">${initials(t.artist)}</div>
      <div class="track-body">
        <h3 class="track-title">${t.title}</h3>
        <p class="track-artist">${t.artist} · ${t.album}</p>
        <div class="track-stats">
          <span class="stat-chip">${t.bpm.toFixed(1)} BPM</span>
          <span class="stat-chip">${t.key} ${t.key_scale}</span>
          <span class="stat-chip">energy ${t.energy.toFixed(2)}</span>
          <span class="stat-chip">${formatDuration(t.duration_sec)}</span>
        </div>
        <div class="tag-row">
          ${t.tags.map((tag) => `
            <span class="tag-chip" title="${tag.source}">
              <span class="tag-dot tag-dot-${tag.source}"></span>${tag.canonical_style}
            </span>
          `).join("")}
        </div>
      </div>
    </article>
  `).join("");
}

/* ---------- 탐색(Similar) 탭 ---------- */

function populateSeedSelect(selectEl) {
  selectEl.innerHTML = MOCK_TRACKS.map((t) => `<option value="${t.id}">${t.artist} - ${t.title}</option>`).join("");
}

function renderSeedBanner(el, track, extra = "") {
  el.innerHTML = `
    <div class="track-art small">${initials(track.artist)}</div>
    <div>
      <div class="seed-banner-title">${track.artist} - ${track.title}</div>
      <div class="seed-banner-sub">시드 트랙 (id=${track.id})${extra}</div>
    </div>
  `;
}

function renderSimilar() {
  const seedId = Number(document.getElementById("seed-select").value);
  const seed = trackById(seedId);
  const digMode = document.getElementById("dig-toggle").checked;
  const zoneLow = Number(document.getElementById("zone-low").value);
  const zoneHigh = Number(document.getElementById("zone-high").value);
  const boredomWeight = Number(document.getElementById("boredom-weight").value);
  const excludeTired = document.getElementById("exclude-tired-toggle").checked ? 3.0 : null;

  renderSeedBanner(document.getElementById("seed-banner"), seed, digMode ? ` · 디깅 존 ${zoneLow.toFixed(2)}~${zoneHigh.toFixed(2)}` : "");

  let ranked = rankSimilar(seedId, { boredomWeight, excludeTiredAbove: excludeTired });
  if (digMode) {
    ranked = ranked.filter((r) => r.similarity >= zoneLow && r.similarity <= zoneHigh);
  }

  const list = document.getElementById("similar-results");
  if (ranked.length === 0) {
    list.innerHTML = `<div class="empty-state glass">해당 조건에 맞는 후보가 없음. ${digMode ? "디깅 존 범위를 넓혀볼 것" : "필터를 완화해볼 것"}</div>`;
    return;
  }

  list.innerHTML = ranked.map((r, i) => `
    <div class="result-row glass">
      <div class="result-rank">${i + 1}</div>
      <div class="track-art small">${initials(r.track.artist)}</div>
      <div class="result-main">
        <div class="result-title">${r.track.artist} - ${r.track.title}</div>
        <div class="result-sub">${r.topFeatures.length ? r.topFeatures.join(", ") : "공통 특성 없음"}${boredomWeight > 0 || excludeTired ? ` · 질림 ${r.boredom.toFixed(2)}` : ""}</div>
      </div>
      <div class="similarity-meter">
        <div class="similarity-bar"><div class="similarity-fill" style="width:${(r.similarity * 100).toFixed(0)}%"></div></div>
        <span class="similarity-val">${r.similarity.toFixed(3)}</span>
      </div>
    </div>
  `).join("");
}

/* ---------- 관계 탐험 탭 ---------- */

let activeCategory = "collab";

function renderRelations() {
  const seedId = Number(document.getElementById("rel-seed-select").value);
  const seed = trackById(seedId);
  const includeKnown = document.getElementById("include-known-toggle").checked;

  renderSeedBanner(document.getElementById("rel-seed-banner"), seed, ` · 카테고리=${activeCategory}`);

  const data = MOCK_RELATIONS[seedId];
  const list = document.getElementById("relations-results");

  if (!data) {
    list.innerHTML = `<div class="empty-state glass">관계 데이터 없음 — collect-relations를 먼저 실행했는지 확인할 것</div>`;
    return;
  }

  let items = data[activeCategory] || [];
  if (!includeKnown) items = items.filter((r) => !r.already_known);

  if (items.length === 0) {
    list.innerHTML = `<div class="empty-state glass">연결된 관계를 찾지 못함</div>`;
    return;
  }

  list.innerHTML = items.map((r, i) => `
    <div class="result-row glass">
      <div class="result-rank">${i + 1}</div>
      <div class="result-main">
        <div class="result-title">${r.entity_name}${r.already_known ? '<span class="known-badge">이미 아는 곡/아티스트</span>' : ""}</div>
        <div class="result-sub">${r.path}</div>
      </div>
    </div>
  `).join("");
}

/* ---------- 질림 랭킹 탭 ---------- */

function renderBoredom() {
  const ranked = Object.entries(MOCK_BOREDOM_SCORES)
    .map(([id, score]) => ({ track: trackById(Number(id)), score }))
    .sort((a, b) => b.score - a.score);
  const max = Math.max(...ranked.map((r) => r.score));

  const list = document.getElementById("boredom-list");
  list.innerHTML = ranked.map((r, i) => `
    <div class="boredom-row">
      <div class="result-rank">${i + 1}</div>
      <div class="track-art small">${initials(r.track.artist)}</div>
      <div class="result-main">
        <div class="result-title">${r.track.artist} - ${r.track.title}</div>
      </div>
      <div class="boredom-meter">
        <div class="boredom-bar"><div class="boredom-fill" style="width:${(r.score / max * 100).toFixed(0)}%"></div></div>
        <span class="boredom-val">${r.score.toFixed(2)}</span>
      </div>
    </div>
  `).join("");
}

/* ---------- 탭 전환 ---------- */

function setupTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

/* ---------- 초기화 ---------- */

function setupSimilarControls() {
  const seedSelect = document.getElementById("seed-select");
  populateSeedSelect(seedSelect);

  const digToggle = document.getElementById("dig-toggle");
  const zoneControls = document.getElementById("zone-controls");
  const zoneLow = document.getElementById("zone-low");
  const zoneHigh = document.getElementById("zone-high");
  const boredomWeight = document.getElementById("boredom-weight");
  const excludeTired = document.getElementById("exclude-tired-toggle");

  function updateZoneBar() {
    const low = Number(zoneLow.value) * 100;
    const high = Number(zoneHigh.value) * 100;
    const fill = document.getElementById("zone-bar-fill");
    fill.style.left = `${Math.min(low, high)}%`;
    fill.style.width = `${Math.abs(high - low)}%`;
  }

  digToggle.addEventListener("change", () => {
    zoneControls.classList.toggle("disabled", !digToggle.checked);
    renderSimilar();
  });
  [zoneLow, zoneHigh].forEach((el) => el.addEventListener("input", () => {
    document.getElementById("zone-low-val").textContent = Number(zoneLow.value).toFixed(2);
    document.getElementById("zone-high-val").textContent = Number(zoneHigh.value).toFixed(2);
    updateZoneBar();
    renderSimilar();
  }));
  boredomWeight.addEventListener("input", () => {
    document.getElementById("boredom-weight-val").textContent = Number(boredomWeight.value).toFixed(1);
    renderSimilar();
  });
  excludeTired.addEventListener("change", renderSimilar);
  seedSelect.addEventListener("change", renderSimilar);

  updateZoneBar();
}

function setupRelationsControls() {
  const seedSelect = document.getElementById("rel-seed-select");
  populateSeedSelect(seedSelect);
  seedSelect.addEventListener("change", renderRelations);

  document.querySelectorAll(".pill-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".pill-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeCategory = btn.dataset.category;
      renderRelations();
    });
  });

  document.getElementById("include-known-toggle").addEventListener("change", renderRelations);
}

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  renderLibrary();
  setupSimilarControls();
  setupRelationsControls();
  renderSimilar();
  renderRelations();
  renderBoredom();
});
