/* digger API(digger/api.py)를 호출해 렌더링함. 유사도/관계/질림 스코어 계산은
   전부 백엔드(similarity.py/graph.py/boredom.py)가 하고, 여기서는 결과만 그림. */

let TRACKS = [];
let BOREDOM = {};
let FEEDBACK = [];

const CATEGORY_LABELS = { collab: "협업", label: "레이블", samples: "샘플", influence: "영향" };
const FEEDBACK_LOG_LIMIT = 200;

const trackById = (id) => TRACKS.find((t) => t.id === id);

async function requestJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    // 422(검증 실패)의 detail은 문자열이 아니라 객체 배열이라 그대로 쓰면 [object Object]가 된다
    const detail = body.detail;
    throw new Error(typeof detail === "string" ? detail : `${url} 요청 실패 (${res.status})`);
  }
  return res.status === 204 ? null : res.json();
}

const fetchJSON = (url) => requestJSON(url);
const postJSON = (url, body) =>
  requestJSON(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? null : JSON.stringify(body),
  });

async function loadInitialData() {
  const [tracks, boredomList, feedback] = await Promise.all([
    fetchJSON("/tracks"),
    fetchJSON("/boredom?top=1000"),
    fetchJSON(`/feedback?top=${FEEDBACK_LOG_LIMIT}`),
  ]);
  TRACKS = tracks;
  BOREDOM = Object.fromEntries(boredomList.map((b) => [b.track_id, b.boredom_score]));
  FEEDBACK = feedback;
}

/* 결과 목록 전체를 다시 그리지 않고 알릴 것만 알린다 — 피드백 한 번에 유사도
   재조회가 딸려오면 순위가 눈앞에서 바뀌어 오히려 방해가 된다. */
function showToast(message, kind = "info") {
  const host = document.getElementById("toast-host");
  const el = document.createElement("div");
  el.className = `toast toast-${kind}`;
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function showAppError(err) {
  const banner = document.getElementById("app-error-banner");
  banner.textContent = `API 서버에 연결하지 못함: ${err.message} — uvicorn digger.api:app으로 서버를 먼저 실행할 것`;
  banner.hidden = false;
}

function formatDuration(sec) {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function initials(artist) {
  const words = (artist || "?").trim().split(/\s+/);
  const letters = words.length === 1 ? words[0].slice(0, 2) : words.slice(0, 2).map((w) => w[0]).join("");
  return letters.toUpperCase();
}

/* Spotify에서 가져온 트랙은 로컬 음원이 없어 bpm/key/energy가 비어 있다.
   없는 값은 "-"로 채우지 않고 칩 자체를 빼되, 왜 없는지는 명시한다. */
function statChips(track) {
  const chips = [];
  if (track.bpm != null) chips.push(`${track.bpm.toFixed(1)} BPM`);
  if (track.key) chips.push(`${track.key} ${track.key_scale || ""}`.trim());
  if (track.energy != null) chips.push(`energy ${track.energy.toFixed(2)}`);
  if (track.duration_sec != null) chips.push(formatDuration(track.duration_sec));
  if (track.bpm == null) chips.push("음원 미분석");
  return chips.map((chip) => `<span class="stat-chip">${chip}</span>`).join("");
}

/* ---------- 라이브러리 탭 ---------- */

function renderLibrary() {
  document.getElementById("track-count").textContent = TRACKS.length;
  const grid = document.getElementById("library-grid");
  grid.innerHTML = TRACKS.map((t) => `
    <article class="track-card glass" onclick="openTrackModal(${t.id})">
      <div class="track-art">${initials(t.artist)}</div>
      <div class="track-body">
        <h3 class="track-title">${t.title}</h3>
        <p class="track-artist">${t.artist} · ${t.album}</p>
        <div class="track-stats">${statChips(t)}</div>
        <div class="tag-row">
          ${t.tags.map((tag) => `
            <span class="tag-chip" title="${tag.confirmed ? "두 출처가 함께 지목" : tag.sources.join(", ")}">
              <span class="tag-dot ${tag.confirmed ? "tag-dot-confirmed" : "tag-dot-single"}"></span>${tag.style}
            </span>
          `).join("")}
        </div>
      </div>
    </article>
  `).join("");
}

/* ---------- 좋아요/스킵 피드백 ---------- */

/* 백엔드는 같은 트랙의 피드백을 덮어쓰지 않고 이벤트로 쌓는다(db.insert_feedback).
   버튼은 "지금 이 트랙을 어떻게 평가해뒀나"를 보여주면 되므로 최신 한 건만 본다.
   GET /feedback이 created_at 내림차순이라 처음 만나는 것이 최신이다. */
const latestFeedbackFor = (trackId) => FEEDBACK.find((f) => f.track_id === trackId);

const THUMB_PATH =
  '<svg viewBox="0 0 24 24" fill="none"><path d="M7 21.5V10l4.6-7.5 1.1.5c.8.4 1.2 1.3 1 2.2L12.9 9.5h5.4a2 2 0 0 1 2 2.4l-1.4 7.6a2 2 0 0 1-2 1.6H7z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M7 10.5H3.5v11H7" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';

function feedbackButtons(trackId, context, seedTrackId = null) {
  const latest = latestFeedbackFor(trackId);
  const seedArg = seedTrackId == null ? "null" : seedTrackId;
  const button = (action, title) => `
    <button class="fb-btn fb-${action} ${latest && latest.action === action ? "active" : ""}"
            data-action="${action}" title="${title}"
            onclick="onFeedback(event, ${trackId}, '${action}', '${context}', ${seedArg})">
      ${THUMB_PATH}
    </button>`;
  return `<div class="feedback-actions">${button("like", "좋아요로 기록")}${button("skip", "스킵으로 기록")}</div>`;
}

function markFeedbackState(container, action) {
  container.querySelectorAll(".fb-btn").forEach((b) => b.classList.toggle("active", b.dataset.action === action));
}

async function onFeedback(event, trackId, action, context, seedTrackId) {
  event.stopPropagation(); // 결과 행 클릭(모달 열기)까지 같이 발동하지 않게
  const container = event.currentTarget.closest(".feedback-actions");
  try {
    await postJSON("/feedback", {
      track_id: trackId,
      action,
      context,
      seed_track_id: seedTrackId,
    });
    FEEDBACK = await fetchJSON(`/feedback?top=${FEEDBACK_LOG_LIMIT}`);
  } catch (err) {
    showToast(`피드백 기록 실패: ${err.message}`, "error");
    return;
  }
  markFeedbackState(container, action);
  renderFeedbackHistory(trackId);
  const track = trackById(trackId);
  showToast(`${action === "like" ? "좋아요" : "스킵"} 기록됨 — ${track ? track.title : `id=${trackId}`}`);
}

function formatFeedbackTime(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

function feedbackHistoryHtml(trackId) {
  const history = FEEDBACK.filter((f) => f.track_id === trackId);
  if (history.length === 0) {
    return `<p class="modal-empty-note">아직 기록된 피드백 없음</p>`;
  }
  return history
    .slice(0, 5)
    .map(
      (f) => `
      <div class="feedback-log-row">
        <span class="fb-log-action fb-log-${f.action}">${f.action === "like" ? "좋아요" : "스킵"}</span>
        <span class="fb-log-context">${f.context || "직접"}${f.seed_title ? ` · 시드 ${f.seed_artist} - ${f.seed_title}` : ""}</span>
        <span class="fb-log-time">${formatFeedbackTime(f.created_at)}</span>
      </div>`
    )
    .join("");
}

/* 모달이 열려 있고 그 트랙의 기록이 바뀐 경우에만 갱신한다. */
function renderFeedbackHistory(trackId) {
  const el = document.getElementById("modal-feedback-history");
  if (el && Number(el.dataset.trackId) === trackId) el.innerHTML = feedbackHistoryHtml(trackId);
}

/* ---------- 탐색(Similar) 탭 ---------- */

function populateSeedSelect(selectEl) {
  selectEl.innerHTML = TRACKS.map((t) => `<option value="${t.id}">${t.artist} - ${t.title}</option>`).join("");
}

function renderSeedBanner(el, track, extra = "") {
  el.onclick = () => openTrackModal(track.id);
  el.innerHTML = `
    <div class="track-art small">${initials(track.artist)}</div>
    <div>
      <div class="seed-banner-title">${track.artist} - ${track.title}</div>
      <div class="seed-banner-sub">시드 트랙 (id=${track.id})${extra}</div>
    </div>
  `;
}

async function renderSimilar() {
  const seedId = Number(document.getElementById("seed-select").value);
  const seed = trackById(seedId);
  const digMode = document.getElementById("dig-toggle").checked;
  const zoneLow = Number(document.getElementById("zone-low").value);
  const zoneHigh = Number(document.getElementById("zone-high").value);
  const boredomWeight = Number(document.getElementById("boredom-weight").value);
  const excludeTired = document.getElementById("exclude-tired-toggle").checked ? 3.0 : null;

  renderSeedBanner(document.getElementById("seed-banner"), seed, digMode ? ` · 디깅 존 ${zoneLow.toFixed(2)}~${zoneHigh.toFixed(2)}` : "");

  const params = new URLSearchParams({ top: "50" });
  if (digMode) {
    params.set("dig", "true");
    params.set("zone_low", zoneLow);
    params.set("zone_high", zoneHigh);
  }
  if (boredomWeight > 0) params.set("boredom_weight", boredomWeight);
  if (excludeTired != null) params.set("exclude_tired_above", excludeTired);

  const list = document.getElementById("similar-results");
  let ranked;
  try {
    ranked = await fetchJSON(`/tracks/${seedId}/similar?${params}`);
  } catch (err) {
    list.innerHTML = `<div class="empty-state glass">유사곡을 불러오지 못함: ${err.message}</div>`;
    return;
  }

  if (ranked.length === 0) {
    list.innerHTML = `<div class="empty-state glass">해당 조건에 맞는 후보가 없음. ${digMode ? "디깅 존 범위를 넓혀볼 것" : "필터를 완화해볼 것"}</div>`;
    return;
  }

  list.innerHTML = ranked.map((r, i) => `
    <div class="result-row glass" onclick="openTrackModal(${r.track_id})">
      <div class="result-rank">${i + 1}</div>
      <div class="track-art small">${initials(r.artist)}</div>
      <div class="result-main">
        <div class="result-title">${r.artist} - ${r.title}</div>
        <div class="result-sub">${r.top_features.length ? r.top_features.join(", ") : "공통 특성 없음"}${boredomWeight > 0 || excludeTired ? ` · 질림 ${r.boredom_score.toFixed(2)}` : ""}</div>
      </div>
      <div class="similarity-meter">
        <div class="similarity-bar"><div class="similarity-fill" style="width:${(r.similarity * 100).toFixed(0)}%"></div></div>
        <span class="similarity-val">${r.similarity.toFixed(3)}</span>
      </div>
      ${feedbackButtons(r.track_id, digMode ? "digging_zone" : "similar", seedId)}
    </div>
  `).join("");
}

/* ---------- 관계 탐험 탭 ---------- */

let activeCategory = "collab";

const ENTITY_TYPE_LABELS = { artist: "아티스트", recording: "레코딩", label: "레이블", track: "트랙" };

/* dig_relations가 돌려주는 관계 한 건을 배지로 요약한다.
   entity_mbid가 없으면 graph.py가 한 단계 더 들어가지 못하고 멈춘 결과다
   (Discogs 크레딧/레이블) — 왜 후보가 얕은지 화면에서 바로 알 수 있게 표시한다. */
function relationBadges(r) {
  const badges = [];
  const entityLabel = ENTITY_TYPE_LABELS[r.entity_type] || r.entity_type;
  if (entityLabel) badges.push(`<span class="rel-badge rel-badge-type">${entityLabel}</span>`);
  if (r.relation_type) badges.push(`<span class="rel-badge">${r.relation_type}</span>`);
  if (!r.entity_mbid) badges.push(`<span class="rel-badge rel-badge-muted" title="MusicBrainz id가 없어 이 지점에서 탐색이 멈춤">mbid 없음</span>`);
  if (r.already_known) badges.push(`<span class="known-badge">이미 아는 곡/아티스트</span>`);
  return badges.join("");
}

async function renderRelations() {
  const seedId = Number(document.getElementById("rel-seed-select").value);
  const seed = trackById(seedId);
  const includeKnown = document.getElementById("include-known-toggle").checked;
  const excludeTired = document.getElementById("rel-exclude-tired-toggle").checked ? 3.0 : null;

  const bannerExtra = `${CATEGORY_LABELS[activeCategory]} 축${excludeTired != null ? " · 질림 3.0 초과 제외" : ""}`;
  renderSeedBanner(document.getElementById("rel-seed-banner"), seed, ` · ${bannerExtra}`);

  const list = document.getElementById("relations-results");
  const params = new URLSearchParams({ category: activeCategory, top: "50", include_known: includeKnown });
  if (excludeTired != null) params.set("exclude_tired_above", excludeTired);

  let items;
  try {
    items = await fetchJSON(`/tracks/${seedId}/relations?${params}`);
  } catch (err) {
    list.innerHTML = `<div class="empty-state glass">관계를 불러오지 못함: ${err.message}</div>`;
    return;
  }

  if (items.length === 0) {
    list.innerHTML = `<div class="empty-state glass">연결된 관계를 찾지 못함 — collect-relations를 먼저 실행했는지 확인할 것</div>`;
    return;
  }

  /* 질림 스코어는 exclude_tired_above를 넘겼을 때만 백엔드가 계산한다
     (안 넘기면 전부 0.0) — 계산되지 않은 0을 "안 질림"으로 오해하지 않게 그때만 그린다. */
  list.innerHTML = items.map((r, i) => `
    <div class="result-row glass">
      <div class="result-rank">${i + 1}</div>
      <div class="result-main">
        <div class="result-title">${r.entity_name}${relationBadges(r)}</div>
        <div class="result-sub">${r.path}</div>
      </div>
      ${excludeTired != null ? `
        <div class="boredom-meter">
          <div class="boredom-bar"><div class="boredom-fill" style="width:${Math.min(r.boredom_score / excludeTired * 100, 100).toFixed(0)}%"></div></div>
          <span class="boredom-val">${r.boredom_score.toFixed(2)}</span>
        </div>
      ` : ""}
    </div>
  `).join("");
}

/* ---------- 질림 랭킹 탭 ---------- */

function renderBoredom() {
  const ranked = Object.entries(BOREDOM)
    .map(([id, score]) => ({ track: trackById(Number(id)), score }))
    .filter((r) => r.track)
    .sort((a, b) => b.score - a.score);

  const list = document.getElementById("boredom-list");
  if (ranked.length === 0) {
    list.innerHTML = `<div class="empty-state glass">청취 이력이 없음 — sync-listening을 먼저 실행할 것</div>`;
    return;
  }

  const max = Math.max(...ranked.map((r) => r.score));
  list.innerHTML = ranked.map((r, i) => `
    <div class="boredom-row" onclick="openTrackModal(${r.track.id})">
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

/* ---------- 트랙 상세 모달 ---------- */

async function renderTrackModal(track) {
  const boredom = BOREDOM[track.id];

  const tagsHtml = track.tags.length
    ? track.tags.map((tag) => `
        <div class="tag-detail-row">
          <span class="tag-dot ${tag.confirmed ? "tag-dot-confirmed" : "tag-dot-single"}"></span>
          <span class="tag-detail-source">${tag.confirmed ? "확증" : tag.sources.join(", ")}</span>
          <span class="tag-detail-name">${tag.style}</span>
          <span class="tag-detail-weight">${tag.weight.toFixed(2)}</span>
        </div>
      `).join("")
    : `<p class="modal-empty-note">장르로 인정된 태그 없음 — enrich를 먼저 실행했는지 확인할 것</p>`;

  const categories = Object.keys(CATEGORY_LABELS);
  let relationsHtml;
  try {
    const counts = await Promise.all(
      categories.map((category) =>
        fetchJSON(`/tracks/${track.id}/relations?category=${category}&top=1000&include_known=true`)
      )
    );
    relationsHtml = categories.map((key, i) => `
      <div class="modal-relation-row"><span>${CATEGORY_LABELS[key]}</span><b>${counts[i].length}건</b></div>
    `).join("");
  } catch (err) {
    relationsHtml = `<p class="modal-empty-note">관계 데이터를 불러오지 못함 — collect-relations를 먼저 실행했는지 확인할 것</p>`;
  }

  return `
    <div class="modal-header">
      <div class="track-art">${initials(track.artist)}</div>
      <div>
        <div class="modal-title">${track.artist} - ${track.title}</div>
        <div class="modal-subtitle">${track.album}</div>
      </div>
    </div>

    <div class="track-stats">${statChips(track)}</div>

    <div class="modal-section">
      <div class="modal-section-label">장르 태그 (${track.tags.length}) · 가중치는 출처 간 합의 정도</div>
      ${tagsHtml}
    </div>

    <div class="modal-section">
      <div class="modal-section-label">질림 스코어</div>
      <p class="modal-empty-note">${boredom != null ? `${boredom.toFixed(2)} · sync-listening 기반` : "청취 이력 없음"}</p>
    </div>

    <div class="modal-section">
      <div class="modal-section-label modal-section-label-row">
        <span>피드백</span>
        ${feedbackButtons(track.id, "library")}
      </div>
      <div id="modal-feedback-history" data-track-id="${track.id}">${feedbackHistoryHtml(track.id)}</div>
    </div>

    <div class="modal-section">
      <div class="modal-section-label">관계 그래프</div>
      ${relationsHtml}
    </div>
  `;
}

async function openTrackModal(trackId) {
  const track = trackById(trackId);
  if (!track) return;
  document.getElementById("modal-body").innerHTML = `<p class="modal-empty-note">불러오는 중...</p>`;
  document.getElementById("track-modal-overlay").hidden = false;
  document.getElementById("modal-body").innerHTML = await renderTrackModal(track);
}

function closeTrackModal() {
  document.getElementById("track-modal-overlay").hidden = true;
}

function setupModal() {
  document.getElementById("modal-close").addEventListener("click", closeTrackModal);
  document.getElementById("track-modal-overlay").addEventListener("click", (e) => {
    if (e.target.id === "track-modal-overlay") closeTrackModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeTrackModal();
  });
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
  document.getElementById("rel-exclude-tired-toggle").addEventListener("change", renderRelations);
}

document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupModal();

  try {
    await loadInitialData();
  } catch (err) {
    showAppError(err);
    return;
  }

  renderLibrary();
  setupSimilarControls();
  setupRelationsControls();
  renderSimilar();
  renderRelations();
  renderBoredom();
});
