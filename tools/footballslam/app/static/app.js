const $ = (id) => document.getElementById(id);

const els = {
  gate: $("gate"),
  app: $("app"),
  sceneTitle: $("sceneTitle"),
  sceneSelect: $("sceneSelect"),
  partSelect: $("partSelect"),
  simulate: $("simulate"),
  clock: $("clock"),
  stage: $("stage"),
  segLabel: $("segLabel"),
  videoWrap: $("videoWrap"),
  video: $("video"),
  overlay: $("overlay"),
  flowPanel: $("flowPanel"),
  simBadge: $("simBadge"),
  flow: $("flow"),
  bottom: $("bottom"),
  laneALabel: $("laneALabel"),
  laneBLabel: $("laneBLabel"),
  laneA: $("laneA"),
  laneB: $("laneB"),
  axis: $("axis"),
  legend: $("legend"),
  tabEpisodes: $("tabEpisodes"),
  tabTracks: $("tabTracks"),
  list: $("list"),
  why: $("why")
};

const FLOW_COLOUR = {
  F: "#d7e8ff",
  M: "#7eaff2",
  D: "#3c6fbe",
  S: "#1a3d73",
  U: "#6d7888"
};
const FLOW_ALIAS = { FREE: "F", MODERATE: "M", DENSE: "D", STOPPED: "S", UNCLEAR: "U" };
const FLOW_WORD = {
  F: "free flowing traffic",
  M: "moderate traffic",
  D: "dense traffic",
  S: "stopped traffic",
  U: "traffic"
};
const FALLBACK_LANES = {
  A: { name: "Scene episodes (Cosmos)", colour: "#2f6df6" },
  B: { name: "Trajectory alerts (Kalman)", colour: "#f6b02f" }
};

let drawPitch = null;
let drawOverlay = null;
let matches = [];
let scene = null;
let partIndex = 0;
let segments = [];
let segmentRows = [];
let allEpisodes = [];
let episodes = [];
let anomalyItems = [];
let anomalyById = new Map();
let featureNames = [];
let alerts = [];
let partAlerts = [];
let alertTau = null;
let mapDoc = null;
let frames = [];
let frameTimes = [];
let currentSeg = null;
let selectedEpisode = null;
let selectedAnomaly = null;
let selectedAlert = null;
let selectedTrackId = null;
let tab = "episodes";
let loadGen = 0;
let mapGen = 0;
let mediaToken = 0;
let tStart = 0;
let tEnd = 1;
let headA = null;
let headB = null;
let quiet = false;

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function rel(path) {
  return new URL(path, import.meta.url).href;
}

async function loadFn(url, name) {
  try {
    const mod = await import(url);
    if (mod && typeof mod[name] === "function") return mod[name];
    if (mod && mod.default && typeof mod.default[name] === "function") return mod.default[name];
    if (mod && typeof mod.default === "function") return mod.default;
    return null;
  } catch (err) {
    return null;
  }
}

async function fetchOptional(url) {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    return null;
  }
}

function base64url(text) {
  const bytes = new TextEncoder().encode(text);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function matchList(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.matches)) return data.matches;
  if (data && Array.isArray(data.scenes)) return data.scenes;
  if (data && (data.match_id || data.camera_id)) return [data];
  return [];
}

function sceneId(match) {
  if (!match) return "";
  return String(match.match_id || match.camera_id || match.id || "");
}

function sceneTitle(match) {
  if (!match) return "Scene";
  return match.title || match.name || match.label || sceneId(match) || "Scene";
}

function lanesOf(match) {
  const lanes = match && (match.lanes || match.teams);
  if (!lanes || typeof lanes !== "object" || Array.isArray(lanes)) return FALLBACK_LANES;
  return { A: lanes.A || FALLBACK_LANES.A, B: lanes.B || FALLBACK_LANES.B };
}

function mapModeOf(match) {
  const mode = match && (match.map_mode || match.mapMode);
  return mode || "FLOW";
}

function partLabel(part, i) {
  if (!part) return "Part " + (i + 1);
  return part.label || part.name || part.title || part.part_id || part.id || ("Part " + (i + 1));
}

function listOf(doc, keys) {
  if (!doc) return [];
  if (Array.isArray(doc)) return doc;
  for (const key of keys) {
    if (Array.isArray(doc[key])) return doc[key];
  }
  return [];
}

function episodeId(obj) {
  if (!obj) return "";
  if (obj.attack_id != null) return String(obj.attack_id);
  if (obj.episode_id != null) return String(obj.episode_id);
  if (obj.id != null) return String(obj.id);
  return "";
}

function spanOf(obj) {
  if (!obj) return null;
  const t0 = Number(obj.t0);
  let t1 = Number(obj.t1);
  if (!Number.isFinite(t1) && Number.isFinite(t0) && Number.isFinite(Number(obj.duration_s))) {
    t1 = t0 + Number(obj.duration_s);
  }
  if (!Number.isFinite(t0) || !Number.isFinite(t1)) return null;
  return [t0, Math.max(t1, t0)];
}

function flowCode(ep) {
  let raw = ep && ep.flow != null && ep.flow !== "" ? ep.flow : "";
  if (!raw) {
    const sp = spanOf(ep);
    if (sp) {
      for (const seg of segmentRows) {
        const a = Number(seg.t0);
        const b = Number(seg.t1);
        if (Number.isFinite(a) && Number.isFinite(b) && sp[0] >= a && sp[0] < b && seg.flow) {
          raw = seg.flow;
          break;
        }
      }
    }
  }
  let code = String(raw || "U").trim().toUpperCase();
  if (FLOW_ALIAS[code]) code = FLOW_ALIAS[code];
  return FLOW_COLOUR[code] ? code : "U";
}

function isLaneA(ep) {
  return String(ep && ep.team != null ? ep.team : "A") === "A";
}

function pretty(name) {
  return String(name == null ? "" : name).replace(/_/g, " ");
}

function fmt(t) {
  if (!Number.isFinite(t) || t < 0) t = 0;
  const s = Math.floor(t);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return String(m).padStart(2, "0") + ":" + String(r).padStart(2, "0");
}

function fmtScore(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : "—";
}

function momentT(item) {
  if (!item) return null;
  if (typeof item.moment === "number" && Number.isFinite(item.moment)) return item.moment;
  if (item.moment && item.moment.t != null) {
    const n = Number(item.moment.t);
    return Number.isFinite(n) ? n : null;
  }
  if (item.moment_t != null) {
    const n = Number(item.moment_t);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function alertKey(a) {
  return String(a.track_id) + ":" + a.t0 + ":" + (a.type || "");
}

function namesOf(doc) {
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) return [];
  if (Array.isArray(doc.feature_names)) return doc.feature_names;
  const per = doc.per_team || doc.per_lane || {};
  const lane = per.A || per.a;
  if (lane && !Array.isArray(lane) && Array.isArray(lane.feature_names)) return lane.feature_names;
  return [];
}

function laneAAnomalies(doc) {
  if (!doc) return [];
  const per = doc.per_team || doc.per_lane || {};
  let rows = per.A || per.a;
  if (!rows && Array.isArray(doc.anomalies)) rows = doc.anomalies;
  if (rows && !Array.isArray(rows)) rows = rows.items || rows.attacks || rows.episodes || [];
  if (!Array.isArray(rows)) return [];
  return rows.slice().sort((a, b) => {
    const ra = Number(a.rank);
    const rb = Number(b.rank);
    if (!Number.isFinite(ra) && !Number.isFinite(rb)) return 0;
    if (!Number.isFinite(ra)) return 1;
    if (!Number.isFinite(rb)) return -1;
    return ra - rb;
  });
}

function parseAlerts(doc) {
  alertTau = null;
  if (!doc) return [];
  if (Array.isArray(doc)) return doc.slice();
  if (doc.tau != null && Number.isFinite(Number(doc.tau))) alertTau = Number(doc.tau);
  const rows = doc.alerts || doc.track_alerts || [];
  return Array.isArray(rows) ? rows.slice() : [];
}

function alertTauOf(a) {
  if (a && a.tau != null && Number.isFinite(Number(a.tau))) return Number(a.tau);
  if (mapDoc && mapDoc.tau != null && Number.isFinite(Number(mapDoc.tau))) return Number(mapDoc.tau);
  return alertTau != null && Number.isFinite(alertTau) ? alertTau : null;
}

function histValues(a) {
  const hist = a && a.d2_hist;
  if (!Array.isArray(hist) || !hist.length) return null;
  const values = [];
  for (const v of hist) {
    const n = typeof v === "number" ? v : Number(v && (v.d2 != null ? v.d2 : v.v));
    if (!Number.isFinite(n)) return null;
    values.push(n);
  }
  return values;
}

function framesOf(doc) {
  if (!doc) return [];
  if (Array.isArray(doc.frames)) return doc.frames;
  if (Array.isArray(doc)) return doc;
  return [];
}

function frameTime(frame) {
  if (!frame) return null;
  const n = Number(frame.t != null ? frame.t : frame.time);
  return Number.isFinite(n) ? n : null;
}

function applyMap(doc) {
  mapDoc = doc;
  const decorated = [];
  for (const frame of framesOf(doc)) {
    const t = frameTime(frame);
    if (t != null) decorated.push({ frame, t });
  }
  decorated.sort((a, b) => a.t - b.t);
  frames = decorated.map((row) => row.frame);
  frameTimes = decorated.map((row) => row.t);
}

function frameAt(t) {
  let lo = 0;
  let hi = frameTimes.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (frameTimes[mid] <= t) {
      ans = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return ans >= 0 ? frames[ans] : null;
}

function indexAnomalies() {
  anomalyById = new Map();
  featureNames = featureNames || [];
  for (const item of anomalyItems) {
    const id = episodeId(item);
    if (id) anomalyById.set(id, item);
  }
}

function isFlagged(ep) {
  const item = anomalyById.get(episodeId(ep));
  if (!item) return false;
  if (item.flagged === true) return true;
  if (Number(item.s_feat) >= 2.5) return true;
  if (Number(item.s_emb) >= 2.5) return true;
  return false;
}

function samePart(obj, part) {
  if (!obj) return null;
  const keys = [obj.original_video, obj.part, obj.part_id, obj.chunk].filter((v) => v != null && v !== "");
  if (!keys.length) return null;
  if (!part) return false;
  const partKeys = [part.original_video, part.part_id, part.id, part.label, part.name].filter((v) => v != null && v !== "");
  return keys.some((key) => partKeys.includes(key));
}

function inPart(obj, part) {
  const tagged = samePart(obj, part);
  if (tagged === false) return false;
  if (tagged === true) return true;
  if (!segments.length) return true;
  const sp = spanOf(obj);
  if (!sp) return false;
  return sp[1] >= tStart && sp[0] <= tEnd;
}

function readSegments(part) {
  const raw = (part && (part.segments || part.playlist)) || [];
  const list = [];
  for (const seg of raw) {
    if (!seg || !(seg.source || seg.uri)) continue;
    const t0 = Number(seg.t0);
    let t1 = Number(seg.t1);
    const start = Number.isFinite(t0) ? t0 : 0;
    if (!Number.isFinite(t1) || t1 < start) t1 = start;
    list.push({ t0: start, t1, source: seg.source || seg.uri, idx: seg.idx });
  }
  list.sort((a, b) => a.t0 - b.t0);
  return list;
}

function showNotReady() {
  els.gate.hidden = false;
  els.app.hidden = true;
  els.stage.hidden = true;
  els.bottom.hidden = true;
}

function updateSimBadge() {
  els.simBadge.hidden = !(els.simulate.checked && mapModeOf(scene) !== "NONE");
}

function applyChrome() {
  const title = sceneTitle(scene);
  els.sceneTitle.textContent = title;
  document.title = title;
  const lanes = lanesOf(scene);
  els.laneALabel.textContent = (lanes.A && lanes.A.name) || "Episodes";
  els.laneBLabel.textContent = (lanes.B && lanes.B.name) || "Trajectories";
  els.laneALabel.style.color = (lanes.A && lanes.A.colour) || FALLBACK_LANES.A.colour;
  els.laneBLabel.style.color = (lanes.B && lanes.B.colour) || FALLBACK_LANES.B.colour;
  const none = mapModeOf(scene) === "NONE";
  els.flowPanel.hidden = none;
  els.stage.classList.toggle("no-flow", none);
  updateSimBadge();
  renderLegend();
}

function renderLegend() {
  els.legend.replaceChildren();
  const items = [
    ["F", "free"],
    ["M", "moderate"],
    ["D", "dense"],
    ["S", "stopped"]
  ];
  for (const [code, name] of items) {
    const span = el("span", null, name);
    const sw = el("i", "swatch");
    sw.style.background = FLOW_COLOUR[code];
    span.prepend(sw);
    els.legend.appendChild(span);
  }
  const flagged = el("span", null, "flagged");
  const mark = el("i", "swatch flag");
  flagged.prepend(mark);
  els.legend.appendChild(flagged);
}

function fillScenes() {
  els.sceneSelect.replaceChildren();
  matches.forEach((match, i) => {
    const opt = el("option", null, sceneTitle(match));
    opt.value = String(i);
    els.sceneSelect.appendChild(opt);
  });
}

function fillParts() {
  quiet = true;
  const parts = (scene && scene.parts) || [];
  els.partSelect.replaceChildren();
  if (!parts.length) {
    const opt = el("option", null, "Part 1");
    opt.value = "0";
    els.partSelect.appendChild(opt);
  }
  parts.forEach((part, i) => {
    const opt = el("option", null, partLabel(part, i));
    opt.value = String(i);
    els.partSelect.appendChild(opt);
  });
  els.partSelect.value = String(partIndex);
  quiet = false;
}

function globalTime() {
  const seg = segments[currentSeg];
  if (!seg) return tStart;
  const now = Number(els.video.currentTime);
  return seg.t0 + (Number.isFinite(now) ? now : 0);
}

function playSegment(index, offset, resume) {
  const seg = segments[index];
  if (!seg) return;
  const keepPlaying = resume === true || (!els.video.paused && !els.video.ended);
  const src = rel("video?src=" + encodeURIComponent(base64url(seg.source)));
  currentSeg = index;
  els.segLabel.textContent = "Segment " + (index + 1) + " of " + segments.length;
  const off = Number(offset) || 0;
  if (els.video.dataset.src !== src) {
    const token = ++mediaToken;
    els.video.dataset.src = src;
    els.video.dataset.token = String(token);
    els.video.dataset.seek = String(off);
    els.video.dataset.resume = keepPlaying ? "1" : "0";
    els.video.src = src;
    return;
  }
  els.video.dataset.seek = String(off);
  if (els.video.readyState < 1) return;
  let next = off;
  if (Number.isFinite(els.video.duration)) next = Math.min(next, Math.max(0, els.video.duration - 0.05));
  if (Math.abs((els.video.currentTime || 0) - next) > 0.05) els.video.currentTime = next;
  if (keepPlaying) els.video.play().catch(() => {});
}

function seekTo(t) {
  if (!Number.isFinite(t)) return;
  if (!segments.length) return;
  let idx = 0;
  let best = Infinity;
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    const last = i === segments.length - 1;
    if (t >= seg.t0 && (t < seg.t1 || (last && t <= seg.t1))) {
      idx = i;
      best = 0;
      break;
    }
    const dist = t < seg.t0 ? seg.t0 - t : t - seg.t1;
    if (dist < best) {
      best = dist;
      idx = i;
    }
  }
  playSegment(idx, Math.max(0, t - segments[idx].t0));
}

function pct(t) {
  if (tEnd <= tStart) return 0;
  return ((t - tStart) / (tEnd - tStart)) * 100;
}

function freshHead(lane) {
  lane.replaceChildren();
  const head = el("div", "playhead");
  lane.appendChild(head);
  return head;
}

function renderTimeline() {
  headA = freshHead(els.laneA);
  headB = freshHead(els.laneB);
  for (const ep of episodes) {
    const sp = spanOf(ep);
    if (!sp) continue;
    const code = flowCode(ep);
    const btn = el("button", "episode" + (isFlagged(ep) ? " flagged" : ""));
    btn.type = "button";
    btn.dataset.id = episodeId(ep) + ":" + ep.t0;
    btn.dataset.t0 = String(sp[0]);
    btn.dataset.t1 = String(sp[1]);
    btn.style.left = pct(sp[0]) + "%";
    btn.style.width = Math.max(pct(sp[1]) - pct(sp[0]), 0.6) + "%";
    btn.style.background = FLOW_COLOUR[code];
    btn.title = code + " " + (FLOW_WORD[code] || "");
    btn.setAttribute("aria-label", "Episode " + (episodeId(ep) || "") + " " + code);
    btn.addEventListener("click", () => selectEpisode(ep, false));
    els.laneA.appendChild(btn);
  }
  for (const alert of partAlerts) {
    const sp = spanOf(alert);
    if (!sp) continue;
    const btn = el("button", "tick");
    btn.type = "button";
    btn.dataset.key = alertKey(alert);
    btn.dataset.type = pretty(alert.type || "alert");
    btn.title = pretty(alert.type || "alert");
    btn.style.left = pct(sp[0]) + "%";
    btn.style.width = Math.max(pct(sp[1]) - pct(sp[0]), 0.8) + "%";
    btn.setAttribute("aria-label", pretty(alert.type || "alert") + " track " + alert.track_id);
    btn.addEventListener("click", () => selectAlert(alert));
    els.laneB.appendChild(btn);
  }
  renderAxis();
  paintSelection();
}

function renderAxis() {
  els.axis.replaceChildren();
  for (let i = 0; i <= 4; i++) {
    const tick = el("span", null, fmt(tStart + ((tEnd - tStart) * i) / 4));
    tick.style.left = (i / 4) * 100 + "%";
    els.axis.appendChild(tick);
  }
}

function syncTabs() {
  const episodesOn = tab === "episodes";
  els.tabEpisodes.setAttribute("aria-selected", episodesOn ? "true" : "false");
  els.tabTracks.setAttribute("aria-selected", episodesOn ? "false" : "true");
}

function renderList() {
  els.list.replaceChildren();
  syncTabs();
  if (tab === "episodes") {
    if (!anomalyItems.length) {
      els.list.appendChild(el("p", "empty", "No episodes yet."));
      return;
    }
    for (const item of anomalyItems) {
      const btn = el("button", "row");
      btn.type = "button";
      const id = episodeId(item);
      const selected = selectedAnomaly && episodeId(selectedAnomaly) === id && id !== "";
      if (selected) btn.classList.add("selected");
      const rank = item.rank != null ? item.rank : "—";
      btn.appendChild(el("span", "row-main", "#" + rank + "   s_feat " + fmtScore(item.s_feat) + "   s_emb " + fmtScore(item.s_emb)));
      if (item.agree === true) btn.appendChild(el("span", "agree", "visual embedding agrees"));
      btn.addEventListener("click", () => selectAnomaly(item));
      els.list.appendChild(btn);
    }
  } else {
    const rows = alerts.slice().sort((a, b) => Number(b.peak_score || 0) - Number(a.peak_score || 0));
    if (!rows.length) {
      els.list.appendChild(el("p", "empty", "No trajectory alerts."));
      return;
    }
    for (const alert of rows) {
      const btn = el("button", "row");
      btn.type = "button";
      if (selectedAlert && alertKey(selectedAlert) === alertKey(alert)) btn.classList.add("selected");
      btn.textContent = fmtScore(alert.peak_score) + "   " + pretty(alert.type || "alert") + "   track " + alert.track_id;
      btn.addEventListener("click", () => selectAlert(alert));
      els.list.appendChild(btn);
    }
  }
  const selected = els.list.querySelector(".selected");
  if (selected) selected.scrollIntoView({ block: "nearest" });
}

function topFeatures(item) {
  const names = featureNames.length ? featureNames : (item.feature_names || []);
  let pairs = [];
  const z = item.z || item.z_scores;
  if (Array.isArray(z)) {
    pairs = z.map((v, i) => ({ name: names[i] || ("feature " + (i + 1)), z: Number(v) }));
  } else if (z && typeof z === "object") {
    pairs = Object.keys(z).map((key) => ({ name: key, z: Number(z[key]) }));
  }
  if (!pairs.length && Array.isArray(item.reasons)) {
    for (const reason of item.reasons) {
      if (!reason || typeof reason !== "object") continue;
      const zv = Number(reason.z != null ? reason.z : reason.z_score);
      const name = reason.feature || reason.name || reason.feature_name;
      if (name && Number.isFinite(zv)) pairs.push({ name, z: zv });
    }
  }
  return pairs.filter((pair) => Number.isFinite(pair.z)).sort((a, b) => Math.abs(b.z) - Math.abs(a.z)).slice(0, 3);
}

function reasonLines(item) {
  if (!item || !Array.isArray(item.reasons)) return [];
  const lines = [];
  for (const reason of item.reasons) {
    const text = typeof reason === "string" ? reason : (reason && (reason.text || reason.reason)) || "";
    if (text) lines.push(text);
  }
  return lines.slice(0, 3);
}

function addBars(parent, item) {
  for (const pair of topFeatures(item)) {
    const row = el("div", "bar-row");
    row.appendChild(el("span", null, pretty(pair.name)));
    const track = el("div", "bar-track");
    const fill = el("div", "bar-fill");
    fill.style.width = Math.min(100, (Math.min(5, Math.abs(pair.z)) / 5) * 100) + "%";
    track.appendChild(fill);
    row.appendChild(track);
    const sign = pair.z > 0 ? "+" : "";
    row.appendChild(el("span", null, sign + pair.z.toFixed(2) + "σ"));
    parent.appendChild(row);
  }
}

function episodePhrase(ep, item) {
  const events = (ep && ep.events) || (item && item.events) || [];
  const useful = events.filter((name) => name && name !== "none");
  if (useful.length) return useful.map(pretty).join(" ");
  return FLOW_WORD[flowCode(ep || item)] || "traffic";
}

function addSimilar(parent, phrase) {
  if (!phrase) return;
  const btn = el("button", "similar", "Find similar");
  btn.type = "button";
  const hits = el("ul", "hits");
  btn.addEventListener("click", () => findSimilar(btn, hits, phrase));
  parent.appendChild(btn);
  parent.appendChild(hits);
}

async function findSimilar(btn, hits, phrase) {
  btn.disabled = true;
  hits.replaceChildren();
  try {
    const res = await fetch(rel("similar?q=" + encodeURIComponent(phrase)), { cache: "no-store" });
    if (!res.ok) {
      hits.appendChild(el("li", null, "Search is unavailable."));
      return;
    }
    const payload = await res.json();
    const rows = Array.isArray(payload) ? payload : (payload.results || payload.hits || payload.matches || payload.data || []);
    const list = Array.isArray(rows) ? rows.slice(0, 6) : [];
    if (!list.length) {
      hits.appendChild(el("li", null, "No similar moments."));
      return;
    }
    for (const hit of list) {
      const text = hit && typeof hit === "object"
        ? (hit.text || hit.caption || hit.description || hit.snippet || hit.reasoning_content || hit.title || hit.source || "result")
        : String(hit);
      const score = hit && Number(hit.score != null ? hit.score : hit.similarity);
      const line = String(text).replace(/\s+/g, " ").slice(0, 180);
      hits.appendChild(el("li", null, Number.isFinite(score) ? line + " (" + score.toFixed(2) + ")" : line));
    }
  } catch (err) {
    hits.appendChild(el("li", null, "Search is unavailable."));
  } finally {
    btn.disabled = false;
  }
}

function drawSpark(canvas, values, tau) {
  const w = canvas.width = 480;
  const h = canvas.height = 120;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  let max = tau == null ? 1 : tau;
  for (const v of values) if (v > max) max = v;
  if (max <= 0) max = 1;
  const pad = 16;
  const xAt = (i) => pad + (i / Math.max(values.length - 1, 1)) * (w - pad * 2);
  const yAt = (v) => h - pad - (v / max) * (h - pad * 2);
  ctx.strokeStyle = "#f6b02f";
  ctx.lineWidth = 3;
  ctx.beginPath();
  values.forEach((v, i) => {
    const x = xAt(i);
    const y = yAt(v);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  if (tau != null) {
    const y = yAt(tau);
    ctx.strokeStyle = "#ff5a5a";
    ctx.setLineDash([8, 6]);
    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(w - pad, y);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

function renderWhy() {
  els.why.replaceChildren();
  els.why.appendChild(el("h3", "why-title", "Why"));
  if (tab === "episodes") {
    const item = selectedAnomaly;
    if (!item && !selectedEpisode) {
      els.why.appendChild(el("p", "empty", "Select an episode."));
      return;
    }
    if (item) {
      const rank = item.rank != null ? item.rank : "—";
      els.why.appendChild(el("p", "meta", "#" + rank + "   s_feat " + fmtScore(item.s_feat) + "   s_emb " + fmtScore(item.s_emb)));
      if (item.agree === true) els.why.appendChild(el("p", "agree", "visual embedding agrees"));
      addBars(els.why, item);
      for (const line of reasonLines(item)) els.why.appendChild(el("p", "reason", line));
    } else {
      const code = flowCode(selectedEpisode);
      els.why.appendChild(el("p", "meta", "Episode " + (episodeId(selectedEpisode) || "") + "   " + code));
    }
    addSimilar(els.why, episodePhrase(selectedEpisode, item));
    return;
  }
  const alert = selectedAlert;
  if (!alert) {
    els.why.appendChild(el("p", "empty", "Select a trajectory alert."));
    return;
  }
  els.why.appendChild(el("p", "meta", "peak_d2 " + fmtScore(alert.peak_d2)));
  els.why.appendChild(el("p", "meta", "type " + pretty(alert.type || "")));
  if (alert.reason) els.why.appendChild(el("p", "reason", alert.reason));
  const hist = histValues(alert);
  const tau = alertTauOf(alert);
  if (hist) {
    const canvas = el("canvas", "spark");
    canvas.setAttribute("aria-label", "d2 history");
    els.why.appendChild(canvas);
    drawSpark(canvas, hist, tau);
    if (tau != null) els.why.appendChild(el("p", "meta", "tau " + fmtScore(tau)));
  }
  addSimilar(els.why, pretty(alert.type || "vehicle motion"));
}

function paintSelection() {
  const epKey = selectedEpisode ? episodeId(selectedEpisode) + ":" + selectedEpisode.t0 : "";
  els.laneA.querySelectorAll(".episode").forEach((node) => {
    node.classList.toggle("selected", epKey !== "" && node.dataset.id === epKey);
  });
  const key = selectedAlert ? alertKey(selectedAlert) : "";
  els.laneB.querySelectorAll(".tick").forEach((node) => {
    node.classList.toggle("selected", key !== "" && node.dataset.key === key);
  });
}

function selectEpisode(ep, useMoment) {
  selectedEpisode = ep;
  selectedAnomaly = anomalyById.get(episodeId(ep)) || null;
  selectedAlert = null;
  selectedTrackId = null;
  tab = "episodes";
  const mt = useMoment ? momentT(selectedAnomaly) : null;
  seekTo(mt == null ? Number(ep.t0) : mt - 2);
  renderList();
  renderWhy();
  paintSelection();
}

function selectAnomaly(item) {
  const id = episodeId(item);
  selectedAnomaly = item;
  selectedEpisode = episodes.find((ep) => episodeId(ep) === id) || null;
  selectedAlert = null;
  selectedTrackId = null;
  tab = "episodes";
  const mt = momentT(item);
  if (mt != null) seekTo(mt - 2);
  else if (selectedEpisode) seekTo(Number(selectedEpisode.t0) || tStart);
  renderList();
  renderWhy();
  paintSelection();
}

function selectAlert(alert) {
  selectedAlert = alert;
  selectedAnomaly = null;
  selectedEpisode = null;
  selectedTrackId = alert.track_id != null ? alert.track_id : null;
  tab = "trajectories";
  const sp = spanOf(alert);
  if (sp) seekTo(sp[0]);
  renderList();
  renderWhy();
  paintSelection();
}

function applyPart() {
  const parts = (scene && scene.parts) || [];
  const part = parts[partIndex] || null;
  segments = readSegments(part);
  if (segments.length) {
    tStart = Math.min(...segments.map((seg) => seg.t0));
    tEnd = Math.max(...segments.map((seg) => seg.t1));
    if (tEnd <= tStart) tEnd = tStart + 1;
  } else {
    tStart = 0;
    tEnd = 1;
  }
  episodes = allEpisodes.filter((ep) => isLaneA(ep) && inPart(ep, part));
  partAlerts = alerts.filter((alert) => inPart(alert, part));
  if (!segments.length) {
    const spans = episodes.concat(partAlerts).map(spanOf).filter(Boolean);
    if (spans.length) {
      tStart = Math.min(...spans.map((sp) => sp[0]));
      tEnd = Math.max(...spans.map((sp) => sp[1]));
      if (tEnd <= tStart) tEnd = tStart + 1;
    }
  }
  currentSeg = null;
  selectedEpisode = null;
  selectedAnomaly = null;
  selectedAlert = null;
  selectedTrackId = null;
  renderTimeline();
  renderList();
  renderWhy();
  if (segments.length) playSegment(0, 0);
  else {
    els.video.dataset.src = "";
    els.video.removeAttribute("src");
    els.video.load();
    els.segLabel.textContent = "No segments in this part.";
  }
}

async function loadMapOnly() {
  if (!scene) return;
  const gen = ++mapGen;
  const sceneGen = loadGen;
  const name = els.simulate.checked ? "map_sim.json" : "map.json";
  const doc = await fetchOptional(rel("data/" + encodeURIComponent(sceneId(scene)) + "/" + name));
  if (gen !== mapGen || sceneGen !== loadGen) return;
  applyMap(doc);
  updateSimBadge();
}

async function loadScene(index) {
  const gen = ++loadGen;
  scene = matches[index];
  partIndex = 0;
  applyChrome();
  fillParts();
  const base = "data/" + encodeURIComponent(sceneId(scene)) + "/";
  const mapName = els.simulate.checked ? "map_sim.json" : "map.json";
  const [segmentDoc, attackDoc, anomalyDoc, alertDoc, map] = await Promise.all([
    fetchOptional(rel(base + "segments.json")),
    fetchOptional(rel(base + "attacks.json")),
    fetchOptional(rel(base + "anomalies.json")),
    fetchOptional(rel(base + "track_alerts.json")),
    fetchOptional(rel(base + mapName))
  ]);
  if (gen !== loadGen) return;
  segmentRows = listOf(segmentDoc, ["segments", "items"]);
  allEpisodes = listOf(attackDoc, ["attacks", "episodes", "items"]);
  anomalyItems = laneAAnomalies(anomalyDoc);
  featureNames = namesOf(anomalyDoc);
  alerts = parseAlerts(alertDoc);
  applyMap(map);
  indexAnomalies();
  applyPart();
}

function fitOverlay() {
  const wrap = els.videoWrap.getBoundingClientRect();
  const vr = els.video.getBoundingClientRect();
  const vw = els.video.videoWidth;
  const vh = els.video.videoHeight;
  if (!vr.width || !vr.height) return;
  let left = vr.left - wrap.left;
  let top = vr.top - wrap.top;
  let width = vr.width;
  let height = vr.height;
  if (vw && vh) {
    const scale = Math.min(vr.width / vw, vr.height / vh);
    width = vw * scale;
    height = vh * scale;
    left += (vr.width - width) / 2;
    top += (vr.height - height) / 2;
    if (els.overlay.width !== vw) els.overlay.width = vw;
    if (els.overlay.height !== vh) els.overlay.height = vh;
  }
  els.overlay.style.left = left + "px";
  els.overlay.style.top = top + "px";
  els.overlay.style.width = width + "px";
  els.overlay.style.height = height + "px";
}

function fitCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.max(1, Math.round(rect.width * dpr));
  const h = Math.max(1, Math.round(rect.height * dpr));
  if (canvas.width !== w) canvas.width = w;
  if (canvas.height !== h) canvas.height = h;
}

function setPlayhead(t) {
  const left = Math.min(100, Math.max(0, pct(t))) + "%";
  if (headA) headA.style.left = left;
  if (headB) headB.style.left = left;
  els.laneA.querySelectorAll(".episode").forEach((node) => {
    const a = Number(node.dataset.t0);
    const b = Number(node.dataset.t1);
    node.classList.toggle("live", t >= a && t < b);
  });
}

function paintFrame() {
  const t = globalTime();
  els.clock.textContent = fmt(t);
  setPlayhead(t);
  if (!scene) return;
  const found = frameAt(t);
  const frame = found || { t, p: [] };
  const opts = {
    mode: mapModeOf(scene),
    flow: mapDoc && mapDoc.flow ? mapDoc.flow : null,
    lanes: lanesOf(scene),
    selectedTrackId: selectedTrackId,
    selected_track_id: selectedTrackId
  };
  fitOverlay();
  if (drawOverlay) {
    try { drawOverlay(els.overlay, frame, opts); } catch (err) { /* missing draw must not stop the page */ }
  }
  if (!els.flowPanel.hidden && drawPitch) {
    fitCanvas(els.flow);
    try { drawPitch(els.flow, frame, opts); } catch (err) { /* missing draw must not stop the page */ }
  }
}

function paint() {
  requestAnimationFrame(paint);
  try { paintFrame(); } catch (err) { /* keep the single loop running */ }
}

function bind() {
  els.sceneSelect.addEventListener("change", () => {
    const i = Number(els.sceneSelect.value) || 0;
    const id = sceneId(matches[i]);
    const url = new URL(location.href);
    if (id) url.searchParams.set("match", id);
    history.replaceState(null, "", url);
    loadScene(i);
  });
  els.partSelect.addEventListener("change", () => {
    if (quiet) return;
    partIndex = Number(els.partSelect.value) || 0;
    applyPart();
  });
  els.simulate.addEventListener("change", () => {
    updateSimBadge();
    loadMapOnly();
  });
  els.tabEpisodes.addEventListener("click", () => {
    tab = "episodes";
    renderList();
    renderWhy();
  });
  els.tabTracks.addEventListener("click", () => {
    tab = "trajectories";
    renderList();
    renderWhy();
  });
  els.video.addEventListener("loadedmetadata", () => {
    if (els.video.dataset.token !== String(mediaToken)) return;
    const off = Number(els.video.dataset.seek || 0);
    if (Number.isFinite(off)) {
      const dur = els.video.duration;
      els.video.currentTime = Number.isFinite(dur) ? Math.min(Math.max(0, off), Math.max(0, dur - 0.05)) : off;
    }
    if (els.video.dataset.resume === "1") els.video.play().catch(() => {});
    fitOverlay();
  });
  els.video.addEventListener("ended", () => {
    if (currentSeg == null || currentSeg + 1 >= segments.length) return;
    playSegment(currentSeg + 1, 0, true);
  });
  els.video.addEventListener("error", () => {
    if (!els.video.dataset.src) return;
    if (els.video.dataset.token !== String(mediaToken)) return;
    els.segLabel.textContent = "Video is unavailable for this segment.";
  });
  const seekLane = (lane, ev) => {
    if (ev.target !== lane) return;
    const rect = lane.getBoundingClientRect();
    if (!rect.width) return;
    const p = (ev.clientX - rect.left) / rect.width;
    seekTo(tStart + p * (tEnd - tStart));
  };
  els.laneA.addEventListener("click", (ev) => seekLane(els.laneA, ev));
  els.laneB.addEventListener("click", (ev) => seekLane(els.laneB, ev));
  const observer = new ResizeObserver(() => {
    fitOverlay();
    if (!els.flowPanel.hidden) fitCanvas(els.flow);
  });
  observer.observe(els.videoWrap);
  observer.observe(els.flowPanel);
}

async function init() {
  drawPitch = await loadFn("./pitch.js", "drawPitch");
  drawOverlay = await loadFn("./overlay.js", "drawOverlay");
  bind();
  requestAnimationFrame(paint);
  let data;
  try {
    const res = await fetch(rel("matches"), { cache: "no-store" });
    if (res.status === 404) {
      showNotReady();
      return;
    }
    if (!res.ok) throw new Error(String(res.status));
    data = await res.json();
  } catch (err) {
    els.sceneTitle.textContent = "Index failed";
    return;
  }
  matches = matchList(data);
  if (!matches.length) {
    els.sceneTitle.textContent = "No scenes";
    return;
  }
  fillScenes();
  const params = new URLSearchParams(location.search);
  const wanted = params.get("match");
  let index = 0;
  if (wanted) {
    const found = matches.findIndex((match) => sceneId(match) === wanted);
    if (found >= 0) index = found;
  }
  els.sceneSelect.value = String(index);
  await loadScene(index);
}

init();
