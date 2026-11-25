/**
 * AI Assistant interface controller (Section 15.5)
 */
import { state, KEYS } from "./state.js";
import { DEFAULT_LOCATION } from "./common.js";
import { RouteMap } from "./map.js";

const SESSION_HISTORY_KEY = "bm:assistant_turns";
const ROUTE_EXPLAIN_KEY = "bm:route_explain_ctx";

const TIME_OPTIONS = [null, "now", "this evening", "tomorrow 8am"];
const DUR_OPTIONS = [null, 20, 30, 45, 60];
const MODE_OPTIONS = [null, "walk", "cycle", "car", "auto", "bus", "metro"];
const ACT_OPTIONS = [null, "walk", "jog", "cycle", "yoga", "play"];

let localCtx = {
  departure_time: null,
  duration_min: null,
  mode: null,
  activity: null,
  destination: null,
};
let isSending = false;

document.addEventListener("DOMContentLoaded", () => {
  initAssistant();
});

window.addEventListener("bm:contextchange", () => {
  syncContextChips();
});

function initAssistant() {
  syncContextChips();
  bindContextChipEditors();

  const input = document.getElementById("assistant-input");
  const counter = document.getElementById("assistant-char-counter");
  const form = document.getElementById("assistant-form");

  if (input && counter) {
    input.addEventListener("input", () => {
      counter.textContent = `${input.value.length} / 500`;
    });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        form?.requestSubmit();
      }
    });
  }

  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    if (!input || isSending) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    if (counter) counter.textContent = "0 / 500";
    sendAssistantMessage(text);
  });

  document.querySelectorAll(".starter-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const prompt = btn.getAttribute("data-prompt");
      if (prompt && !isSending) sendAssistantMessage(prompt);
    });
  });

  handleIncomingQueryParams();
}

function handleIncomingQueryParams() {
  const params = new URLSearchParams(window.location.search);
  const q = params.get("q");
  if (q && q.trim()) {
    sendAssistantMessage(q.trim());
    return;
  }
  if (params.get("explain_route") === "1") {
    try {
      const raw = sessionStorage.getItem(ROUTE_EXPLAIN_KEY);
      if (raw) {
        const routeCtx = JSON.parse(raw);
        if (routeCtx.destination) localCtx.destination = routeCtx.destination;
        if (routeCtx.departure_time) localCtx.departure_time = routeCtx.departure_time;
        syncContextChips();
        const destLabel = routeCtx.destination?.label || "my destination";
        sendAssistantMessage(`Going to ${destLabel}, explain the best way`);
      }
    } catch {
      // Ignore unavailable sessionStorage
    }
  }
}

function syncContextChips() {
  const loc = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
  const sens = state.get(KEYS.SENSITIVE, []);

  const locBtn = document.getElementById("chip-ctx-loc");
  const timeBtn = document.getElementById("chip-ctx-time");
  const durBtn = document.getElementById("chip-ctx-dur");
  const modeBtn = document.getElementById("chip-ctx-mode");
  const actBtn = document.getElementById("chip-ctx-act");
  const sensBtn = document.getElementById("chip-ctx-sens");

  if (locBtn) locBtn.textContent = `Location: ${loc.label || "Selected"}`;
  if (timeBtn) {
    timeBtn.textContent = `Time: ${localCtx.departure_time ? String(localCtx.departure_time).slice(0, 16) : "Any"}`;
  }
  if (durBtn) durBtn.textContent = `Duration: ${localCtx.duration_min ? `${localCtx.duration_min} min` : "Any"}`;
  if (modeBtn) modeBtn.textContent = `Mode: ${localCtx.mode || "All"}`;
  if (actBtn) actBtn.textContent = `Activity: ${localCtx.activity || "None"}`;
  if (sensBtn) {
    sensBtn.textContent = sens.length > 0 ? `Cautious: ${sens.join(", ")}` : "Cautious: Off";
  }
}

function cycleValue(options, current) {
  const idx = options.indexOf(current);
  return options[(idx + 1) % options.length];
}

function bindContextChipEditors() {
  document.getElementById("chip-ctx-time")?.addEventListener("click", () => {
    localCtx.departure_time = cycleValue(TIME_OPTIONS, localCtx.departure_time);
    syncContextChips();
  });
  document.getElementById("chip-ctx-dur")?.addEventListener("click", () => {
    localCtx.duration_min = cycleValue(DUR_OPTIONS, localCtx.duration_min);
    syncContextChips();
  });
  document.getElementById("chip-ctx-mode")?.addEventListener("click", () => {
    localCtx.mode = cycleValue(MODE_OPTIONS, localCtx.mode);
    syncContextChips();
  });
  document.getElementById("chip-ctx-act")?.addEventListener("click", () => {
    localCtx.activity = cycleValue(ACT_OPTIONS, localCtx.activity);
    syncContextChips();
  });
  document.getElementById("chip-ctx-sens")?.addEventListener("click", () => {
    const sens = state.get(KEYS.SENSITIVE, []);
    state.set(KEYS.SENSITIVE, sens.length > 0 ? [] : ["child"]);
    window.dispatchEvent(new CustomEvent("bm:contextchange"));
    syncContextChips();
  });
}

function getRecentTurns() {
  try {
    const raw = sessionStorage.getItem(SESSION_HISTORY_KEY);
    return raw ? JSON.parse(raw).slice(-2) : [];
  } catch {
    return [];
  }
}

function saveTurn(text) {
  try {
    const turns = getRecentTurns();
    turns.push(String(text).slice(0, 300));
    sessionStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(turns.slice(-2)));
  } catch {
    // Ignore storage errors
  }
}

async function sendAssistantMessage(message) {
  isSending = true;
  const sendBtn = document.getElementById("btn-assistant-send");
  const statusEl = document.getElementById("assistant-status");
  if (sendBtn) sendBtn.disabled = true;
  if (statusEl) statusEl.textContent = "Thinking…";

  appendUserBubble(message);

  const loc = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
  const scale = state.get(KEYS.SCALE, "naqi");
  const sensitive = state.get(KEYS.SENSITIVE, []);
  const isDemo = state.get(KEYS.DEMO, false);

  const payload = {
    message,
    recent_turns: getRecentTurns(),
    context: {
      lat: loc.lat,
      lon: loc.lon,
      label: loc.label,
      scale,
      sensitive,
      departure_time: localCtx.departure_time,
      duration_min: localCtx.duration_min,
      mode: localCtx.mode,
      activity: localCtx.activity,
      destination: localCtx.destination,
    },
  };

  try {
    const res = await fetch("/api/v1/assistant/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(isDemo ? { "X-BreatheMap-Demo": "1" } : {}),
      },
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    if (!res.ok) {
      throw new Error(body?.error?.message || "Assistant request failed.");
    }

    const data = body.data;
    saveTurn(message);
    if (data.reply?.summary) saveTurn(data.reply.summary);
    updateQuotaBanner(data);
    appendAssistantBubble(data);
    if (statusEl) statusEl.textContent = "Reply received.";
  } catch (err) {
    appendErrorBubble(err.message || "Assistant temporarily unavailable.");
    if (statusEl) statusEl.textContent = "Error receiving reply.";
  } finally {
    isSending = false;
    if (sendBtn) sendBtn.disabled = false;
  }
}

function updateQuotaBanner(data) {
  const banner = document.getElementById("assistant-quota-banner");
  if (!banner) return;
  const rc = data.provenance?.reason_code || "";
  const isQuota = rc.startsWith("quota_") || rc === "gemini_disabled";
  banner.classList.toggle("hidden", !(data.answer_mode === "quick" && isQuota));
}

function appendUserBubble(text) {
  const log = document.getElementById("assistant-chat-log");
  if (!log) return;
  const div = document.createElement("div");
  div.className = "chat-msg chat-msg-user";
  const p = document.createElement("p");
  p.textContent = text;
  div.appendChild(p);
  log.appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function appendErrorBubble(errMsg) {
  const log = document.getElementById("assistant-chat-log");
  if (!log) return;
  const div = document.createElement("div");
  div.className = "chat-msg chat-msg-error";
  const p = document.createElement("p");
  p.textContent = errMsg;
  div.appendChild(p);
  log.appendChild(div);
}

function appendAssistantBubble(data) {
  const log = document.getElementById("assistant-chat-log");
  if (!log) return;

  const div = document.createElement("div");
  div.className = "chat-msg chat-msg-assistant";

  // Badge
  const badge = document.createElement("span");
  badge.className = `answer-badge badge-${data.answer_mode}`;
  if (data.answer_mode === "ai") {
    badge.textContent = "AI explanation";
  } else if (data.answer_mode === "quick") {
    badge.textContent = "Quick answer";
  } else if (data.answer_mode === "clarify") {
    badge.textContent = "Clarification";
  } else {
    badge.textContent = "Guidance";
  }
  div.appendChild(badge);

  // Summary + Bold Recommendation
  const reply = data.reply || {};
  if (reply.summary) {
    const sumP = document.createElement("p");
    sumP.className = "msg-summary";
    sumP.textContent = reply.summary;
    div.appendChild(sumP);
  }
  if (reply.recommendation) {
    const recP = document.createElement("p");
    recP.className = "msg-recommendation";
    const strong = document.createElement("strong");
    strong.textContent = reply.recommendation;
    recP.appendChild(strong);
    div.appendChild(recP);
  }

  if (Array.isArray(reply.reasons) && reply.reasons.length > 0) {
    const ul = document.createElement("ul");
    ul.className = "msg-reasons";
    reply.reasons.forEach((r) => {
      const li = document.createElement("li");
      li.textContent = r;
      ul.appendChild(li);
    });
    div.appendChild(ul);
  }

  if (Array.isArray(reply.caveats) && reply.caveats.length > 0) {
    const cav = document.createElement("p");
    cav.className = "msg-caveats";
    cav.textContent = reply.caveats.join(" ");
    div.appendChild(cav);
  }

  // Cards
  if (Array.isArray(data.cards)) {
    data.cards.forEach((card, idx) => {
      const cardEl = renderCard(card, idx);
      if (cardEl) div.appendChild(cardEl);
    });
  }

  // Chips (clarification, sensitive toggle, report_help)
  if (Array.isArray(data.chips) && data.chips.length > 0) {
    const chipsRow = document.createElement("div");
    chipsRow.className = "follow-up-chips";
    data.chips.forEach((chip) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "starter-chip";
      btn.textContent = chip.label;
      btn.addEventListener("click", () => handleChipClick(chip));
      chipsRow.appendChild(btn);
    });
    div.appendChild(chipsRow);
  }

  // Provenance
  const prov = document.createElement("p");
  prov.className = "provenance-note";
  const provSource = data.provenance?.source || "BreatheMap";
  const cachedNote = data.provenance?.cached ? " · Cached" : "";
  prov.textContent = `Based on ${provSource}${cachedNote}`;
  div.appendChild(prov);

  log.appendChild(div);
  div.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function handleChipClick(chip) {
  if (chip.action === "enable_sensitive" && chip.value) {
    const current = state.get(KEYS.SENSITIVE, []);
    if (!current.includes(chip.value)) {
      state.set(KEYS.SENSITIVE, [...current, chip.value]);
      window.dispatchEvent(new CustomEvent("bm:contextchange"));
      syncContextChips();
    }
    sendAssistantMessage("Update guidance with cautious mode on");
    return;
  }
  if (chip.action === "open_watch") {
    const loc = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
    window.location.href = `/watch?category=open_burning&lat=${loc.lat}&lon=${loc.lon}`;
    return;
  }
  if (chip.action === "set_time") {
    localCtx.departure_time = chip.value;
    syncContextChips();
    sendAssistantMessage(`At ${chip.value}`);
    return;
  }
  if (chip.action === "set_duration") {
    localCtx.duration_min = Number(chip.value);
    syncContextChips();
    sendAssistantMessage(`For ${chip.value} minutes`);
    return;
  }
  if (chip.action === "set_destination") {
    sendAssistantMessage(`Going to ${chip.value}`);
    return;
  }
  if (chip.action === "use_demo") {
    state.set(KEYS.DEMO, true);
    window.dispatchEvent(new CustomEvent("bm:contextchange"));
    return;
  }
  if (chip.label) {
    sendAssistantMessage(chip.label);
  }
}

function renderCard(card, idx) {
  const box = document.createElement("div");
  box.className = "assistant-card";

  if (card.type === "air_summary") {
    const d = card.data || {};
    const h = document.createElement("h3");
    h.textContent = `Air Quality: ${d.band || "Unknown"} (${d.index ?? "--"})`;
    const p = document.createElement("p");
    p.textContent = `PM2.5: ${d.pm25 ?? "--"} µg/m³ · Source: ${d.source || "Open-Meteo"}`;
    box.appendChild(h);
    box.appendChild(p);
    return box;
  }

  if (card.type === "time_window") {
    const w = card.data || {};
    const h = document.createElement("h3");
    h.textContent = "Cleanest & Peak Smog Windows";
    box.appendChild(h);
    if (w.cleanest) {
      const p1 = document.createElement("p");
      p1.textContent = `Cleanest: ${w.cleanest.start_time.slice(11, 16)}–${w.cleanest.end_time.slice(11, 16)} (${w.cleanest.avg_pm25} µg/m³)`;
      box.appendChild(p1);
    }
    if (w.worst) {
      const p2 = document.createElement("p");
      p2.textContent = `Peak smog: ${w.worst.start_time.slice(11, 16)}–${w.worst.end_time.slice(11, 16)} (${w.worst.avg_pm25} µg/m³)`;
      box.appendChild(p2);
    }
    return box;
  }

  if (card.type === "activity_advice") {
    const d = card.data || {};
    const h = document.createElement("h3");
    h.textContent = d.summary || "Activity Advice";
    const p = document.createElement("p");
    p.textContent = `${d.advice || ""} (${d.duration_min || "--"} min)`;
    box.appendChild(h);
    box.appendChild(p);
    return box;
  }

  if (card.type === "route_comparison") {
    const r = card.data || {};
    const h = document.createElement("h3");
    h.textContent = `Route Comparison to ${r.destination?.label || "Destination"}`;
    box.appendChild(h);

    const ul = document.createElement("ul");
    (r.options || []).forEach((opt) => {
      if (opt.status !== "available") return;
      const li = document.createElement("li");
      const est = opt.is_estimated ? " (est.)" : "";
      li.textContent = `${opt.mode.toUpperCase()}${est}: ${opt.dose_ug} µg PM2.5 · ${opt.duration_min} min`;
      ul.appendChild(li);
    });
    box.appendChild(ul);

    if (r.origin && r.destination && typeof L !== "undefined") {
      const mapDiv = document.createElement("div");
      const mapId = `assistant-route-map-${Date.now()}-${idx}`;
      mapDiv.id = mapId;
      mapDiv.className = "assistant-mini-map";
      mapDiv.setAttribute("role", "region");
      mapDiv.setAttribute("aria-label", "Route comparison mini map");
      box.appendChild(mapDiv);
      requestAnimationFrame(() => {
        const mini = new RouteMap(mapId);
        mini.renderComparison(r.origin, r.destination, r.options || [], r.reports_along_route || []);
      });
    }
    return box;
  }

  if (card.type === "home_tips") {
    const h = document.createElement("h3");
    h.textContent = "Indoor Air Exposure Tips";
    box.appendChild(h);
    const ul = document.createElement("ul");
    (card.data || []).forEach((tip) => {
      const li = document.createElement("li");
      li.textContent = `${tip.title}: ${tip.text}`;
      ul.appendChild(li);
    });
    box.appendChild(ul);
    return box;
  }

  if (card.type === "reports") {
    const reps = card.data || [];
    const h = document.createElement("h3");
    h.textContent = `Community Reports (${reps.length})`;
    box.appendChild(h);
    if (reps.length === 0) {
      const p = document.createElement("p");
      p.textContent = "No unverified community reports nearby.";
      box.appendChild(p);
    } else {
      const ul = document.createElement("ul");
      reps.slice(0, 5).forEach((rep) => {
        const li = document.createElement("li");
        li.textContent = `[${rep.category}] ${rep.description} (Unverified community report)`;
        ul.appendChild(li);
      });
      box.appendChild(ul);
    }
    return box;
  }

  if (card.type === "glossary") {
    const g = card.data || {};
    const h = document.createElement("h3");
    h.textContent = String(g.term || "Glossary").toUpperCase();
    const p = document.createElement("p");
    p.textContent = g.definition || "";
    box.appendChild(h);
    box.appendChild(p);
    return box;
  }

  return null;
}
