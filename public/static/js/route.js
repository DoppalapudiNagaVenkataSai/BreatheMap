/**
 * BreatheRoute page controller
 */
import { fetchApi } from "./api.js";
import { state, KEYS } from "./state.js";
import { DEFAULT_LOCATION, announce } from "./common.js";
import { RouteMap, MODE_STYLES } from "./map.js";

let selectedOrigin = null;
let selectedDest = null;
const routeMap = new RouteMap("route-map");

document.addEventListener("DOMContentLoaded", () => {
  initRouteForm();
  applyQueryPrefill();
});

function initRouteForm() {
  const originInput = document.getElementById("route-origin-input");
  const destInput = document.getElementById("route-dest-input");
  const originResults = document.getElementById("origin-results");
  const destResults = document.getElementById("dest-results");
  const btnOriginSearch = document.getElementById("btn-origin-search");
  const btnDestSearch = document.getElementById("btn-dest-search");
  const whenInput = document.getElementById("route-when-input");
  const btnWhenNow = document.getElementById("btn-when-now");
  const form = document.getElementById("route-compare-form");
  const btnDemo = document.getElementById("btn-route-demo");
  const btnErrorSample = document.getElementById("btn-error-sample");

  const savedLoc = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
  selectedOrigin = { ...savedLoc };
  if (originInput) originInput.value = savedLoc.label;

  setNowTime(whenInput);
  updateNightOptionVisibility(whenInput?.value);

  if (btnWhenNow && whenInput) {
    btnWhenNow.addEventListener("click", () => {
      setNowTime(whenInput);
      updateNightOptionVisibility(whenInput.value);
    });
  }
  if (whenInput) {
    whenInput.addEventListener("change", () => {
      updateNightOptionVisibility(whenInput.value);
    });
  }

  setupSearchBox(originInput, btnOriginSearch, originResults, (loc) => {
    selectedOrigin = loc;
  });
  setupSearchBox(destInput, btnDestSearch, destResults, (loc) => {
    selectedDest = loc;
  });

  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      runComparison();
    });
  }

  const triggerSample = () => {
    state.set(KEYS.DEMO, true);
    const demoBanner = document.getElementById("demo-banner");
    if (demoBanner) demoBanner.classList.remove("hidden");
    selectedOrigin = { label: "Connaught Place, New Delhi", lat: 28.6315, lon: 77.2167 };
    selectedDest = { label: "New Delhi Railway Station", lat: 28.643, lon: 77.2194 };
    if (originInput) originInput.value = selectedOrigin.label;
    if (destInput) destInput.value = selectedDest.label;
    runComparison();
  };

  if (btnDemo) btnDemo.addEventListener("click", triggerSample);
  if (btnErrorSample) btnErrorSample.addEventListener("click", triggerSample);
}

function setNowTime(input) {
  if (!input) return;
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  input.value = now.toISOString().slice(0, 16);
}

function updateNightOptionVisibility(whenVal) {
  const nightBox = document.getElementById("night-lighting-option");
  if (!nightBox || !whenVal) return;
  const hour = new Date(whenVal).getHours();
  const isNightHour = hour >= 18 || hour < 6;
  if (isNightHour) nightBox.classList.remove("hidden");
  else nightBox.classList.add("hidden");
}

function setupSearchBox(input, btn, resultsList, onSelect) {
  if (!input || !btn || !resultsList) return;
  const performSearch = async () => {
    const q = input.value.trim();
    if (q.length < 2) return;
    resultsList.classList.remove("hidden");
    resultsList.textContent = "Searching…";
    try {
      const items = await fetchApi(`/api/v1/geocode?q=${encodeURIComponent(q)}`);
      resultsList.textContent = "";
      if (!items.length) {
        const li = document.createElement("li");
        li.textContent = `No places found for '${q}'.`;
        resultsList.appendChild(li);
        return;
      }
      items.forEach((item) => {
        const li = document.createElement("li");
        const optBtn = document.createElement("button");
        optBtn.type = "button";
        optBtn.textContent = item.label;
        optBtn.addEventListener("click", () => {
          onSelect({ label: item.label, lat: item.lat, lon: item.lon });
          input.value = item.label;
          resultsList.classList.add("hidden");
        });
        li.appendChild(optBtn);
        resultsList.appendChild(li);
      });
    } catch (e) {
      resultsList.textContent = "Search is busy — try again in a few seconds.";
    }
  };
  btn.addEventListener("click", performSearch);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      performSearch();
    }
  });
}

function applyQueryPrefill() {
  const params = new URLSearchParams(window.location.search);
  const to = params.get("to");
  const when = params.get("when");
  const destInput = document.getElementById("route-dest-input");
  const whenInput = document.getElementById("route-when-input");
  if (to && destInput) destInput.value = to;
  if (when && whenInput) whenInput.value = when;
}

async function runComparison() {
  const loadingEl = document.getElementById("route-loading");
  const errorEl = document.getElementById("route-error");
  const errorText = document.getElementById("route-error-text");
  const resultsEl = document.getElementById("route-results");
  const originInput = document.getElementById("route-origin-input");
  const destInput = document.getElementById("route-dest-input");
  const whenInput = document.getElementById("route-when-input");
  const flexSelect = document.getElementById("route-flex-select");
  const sortSelect = document.getElementById("route-sort-select");
  const preferLitCb = document.getElementById("prefer-lit-checkbox");

  const destVal = destInput?.value.trim() || "";
  if (!destVal && !selectedDest) {
    if (errorEl && errorText) {
      errorText.textContent = "Please enter a destination before comparing routes.";
      errorEl.classList.remove("hidden");
    }
    return;
  }

  if (errorEl) errorEl.classList.add("hidden");
  if (resultsEl) resultsEl.classList.add("hidden");
  if (loadingEl) loadingEl.classList.remove("hidden");
  announce("Comparing routes and air quality forecasts…");

  const checkedModes = Array.from(
    document.querySelectorAll('input[name="modes"]:checked')
  ).map((el) => el.value);

  const payload = {
    flexibility_minutes: parseInt(flexSelect?.value || "120", 10),
    modes: checkedModes.length ? checkedModes : ["walk", "cycle", "car", "auto", "bus", "metro"],
    sort: sortSelect?.value || "least_pollution",
    prefer_lit: Boolean(preferLitCb?.checked),
    scale: state.get(KEYS.SCALE, "naqi"),
  };

  if (selectedOrigin && originInput?.value === selectedOrigin.label) {
    payload.origin = { lat: selectedOrigin.lat, lon: selectedOrigin.lon };
  } else if (originInput?.value.trim()) {
    payload.origin_text = originInput.value.trim();
  }

  if (selectedDest && destVal === selectedDest.label) {
    payload.destination = { lat: selectedDest.lat, lon: selectedDest.lon };
  } else {
    payload.destination_text = destVal;
  }

  if (whenInput?.value) {
    payload.departure_time = new Date(whenInput.value).toISOString();
  }

  try {
    const data = await fetchApi("/api/v1/routes/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (loadingEl) loadingEl.classList.add("hidden");
    renderResults(data);
  } catch (err) {
    if (loadingEl) loadingEl.classList.add("hidden");
    if (errorEl && errorText) {
      errorText.textContent = err.message || "Could not compare routes.";
      errorEl.classList.remove("hidden");
    }
    announce("Route comparison failed.");
  }
}

function renderResults(data) {
  const resultsEl = document.getElementById("route-results");
  const resultsHeading = document.getElementById("results-heading");
  const headlineEl = document.getElementById("route-headline");
  const sugBox = document.getElementById("departure-suggestion-box");
  const sugText = document.getElementById("departure-suggestion-text");
  const btnUseTime = document.getElementById("btn-use-suggested-time");
  const cardsList = document.getElementById("mode-cards-list");
  const legendEl = document.getElementById("map-legend");
  const warningsBox = document.getElementById("route-warnings-box");
  const warningsList = document.getElementById("route-warnings-list");
  const reportsText = document.getElementById("route-reports-text");
  const reportsList = document.getElementById("route-reports-list");
  const explainLink = document.getElementById("link-explain-ai");

  if (!resultsEl || !cardsList) return;
  resultsEl.classList.remove("hidden");

  // Headline
  const bestOpt = data.options.find((o) => o.is_best && o.status === "available");
  const walkOpt = data.options.find((o) => o.mode === "walk" && o.status === "available");
  if (headlineEl && bestOpt) {
    const estLabel = bestOpt.is_estimated ? " (estimate)" : "";
    let msg = `${bestOpt.mode.toUpperCase()}${estLabel} has the lowest estimated exposure (~${bestOpt.dose_ug} µg PM2.5 breathed in).`;
    if (walkOpt && walkOpt.mode !== bestOpt.mode && walkOpt.dose_ug > 0) {
      const pctLess = Math.round(((walkOpt.dose_ug - bestOpt.dose_ug) / walkOpt.dose_ug) * 100);
      if (pctLess > 0) {
        msg = `${bestOpt.mode.toUpperCase()}${estLabel} has the lowest estimated exposure — about ${pctLess}% less PM2.5 breathed in than walking.`;
      }
    }
    headlineEl.textContent = msg;
  }

  // Departure suggestion
  if (sugBox && sugText && btnUseTime) {
    if (data.departure_suggestion) {
      const dt = new Date(data.departure_suggestion.time);
      const timeLabel = dt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      sugText.textContent = `Leave at ${timeLabel} to lower your estimated PM2.5 intake by about ${data.departure_suggestion.reduction_pct}%.`;
      sugBox.classList.remove("hidden");
      btnUseTime.onclick = () => {
        const whenInput = document.getElementById("route-when-input");
        if (whenInput) {
          const localDt = new Date(dt.getTime() - dt.getTimezoneOffset() * 60000);
          whenInput.value = localDt.toISOString().slice(0, 16);
          updateNightOptionVisibility(whenInput.value);
          runComparison();
        }
      };
    } else {
      sugBox.classList.add("hidden");
    }
  }

  // Mode cards
  cardsList.textContent = "";
  const maxDose = Math.max(...data.options.map((o) => o.dose_ug || 0), 1);

  data.options.forEach((opt) => {
    const card = document.createElement("article");
    card.className = `mode-card ${opt.is_best ? "is-best" : ""}`;

    const topRow = document.createElement("div");
    topRow.className = "mode-card-top";
    const title = document.createElement("h3");
    title.textContent = opt.mode.toUpperCase();
    topRow.appendChild(title);

    if (opt.is_estimated) {
      const est = document.createElement("span");
      est.className = "badge badge-estimate";
      est.textContent = "Estimate";
      topRow.appendChild(est);
    }
    if (opt.about_same) {
      const tie = document.createElement("span");
      tie.className = "badge badge-tie";
      tie.textContent = "About the same";
      topRow.appendChild(tie);
    }
    opt.flags.forEach((flag) => {
      const fl = document.createElement("span");
      fl.className = "badge badge-flag";
      fl.textContent = flag;
      topRow.appendChild(fl);
    });
    card.appendChild(topRow);

    if (opt.status !== "available") {
      const unavail = document.createElement("p");
      unavail.textContent = "Route unavailable for this mode.";
      card.appendChild(unavail);
      cardsList.appendChild(card);
      return;
    }

    const metrics = document.createElement("p");
    metrics.className = "mode-metrics";
    metrics.textContent = `${opt.duration_min} min · ${opt.distance_km} km · Avg ${opt.avg_pm25} µg/m³`;
    card.appendChild(metrics);

    const doseLine = document.createElement("p");
    doseLine.className = "mode-dose";
    doseLine.textContent = `PM2.5 breathed in: ~${opt.dose_ug} µg`;
    card.appendChild(doseLine);

    const barTrack = document.createElement("div");
    barTrack.className = "dose-bar-track";
    const barFill = document.createElement("div");
    barFill.className = "dose-bar-fill";
    barFill.style.width = `${Math.max(8, Math.round((opt.dose_ug / maxDose) * 100))}%`;
    barTrack.appendChild(barFill);
    card.appendChild(barTrack);

    if (opt.lighting) {
      const lightRow = document.createElement("p");
      lightRow.className = "mode-lighting";
      lightRow.textContent = `${opt.lighting.description} (OSM volunteer tags; may be incomplete)`;
      card.appendChild(lightRow);
    }

    const emRow = document.createElement("p");
    emRow.className = "mode-emissions";
    emRow.textContent = `Illustrative emissions: ${opt.emissions_kg} kg CO₂e`;
    card.appendChild(emRow);

    if (opt.geometry || opt.mode === "metro") {
      const btnMap = document.createElement("button");
      btnMap.type = "button";
      btnMap.className = "btn-text";
      btnMap.textContent = "Show on map";
      btnMap.addEventListener("click", () => {
        routeMap.highlightMode(opt.mode);
      });
      card.appendChild(btnMap);
    }

    cardsList.appendChild(card);
  });

  // Map & Legend
  routeMap.renderComparison(data.origin, data.destination, data.options, data.reports_along_route);
  if (legendEl) {
    legendEl.textContent = "";
    data.options.forEach((opt) => {
      if (opt.status !== "available") return;
      const st = MODE_STYLES[opt.mode];
      if (!st) return;
      const item = document.createElement("span");
      item.className = "legend-item";
      item.textContent = st.label;
      item.style.borderBottom = `3px ${st.dashArray ? "dashed" : "solid"} ${st.color}`;
      legendEl.appendChild(item);
    });
  }

  // Reports
  if (reportsList && reportsText) {
    reportsList.textContent = "";
    if (data.reports_along_route && data.reports_along_route.length > 0) {
      reportsText.textContent = `${data.reports_along_route.length} unverified community report(s) near this route:`;
      data.reports_along_route.forEach((rep) => {
        const li = document.createElement("li");
        li.textContent = `[${rep.category}] ${rep.description} (Unverified community report)`;
        reportsList.appendChild(li);
      });
    } else {
      reportsText.textContent = "No unverified community reports along this route.";
    }
  }

  // Warnings
  if (warningsBox && warningsList) {
    warningsList.textContent = "";
    const allWarnings = data.provenance?.warnings || [];
    if (allWarnings.length > 0) {
      allWarnings.forEach((w) => {
        const li = document.createElement("li");
        li.textContent = w;
        warningsList.appendChild(li);
      });
      warningsBox.classList.remove("hidden");
    } else {
      warningsBox.classList.add("hidden");
    }
  }

  // Explain with AI link
  if (explainLink) {
    const q = `Best way from ${data.origin.label} to ${data.destination.label}?`;
    explainLink.href = `/assistant?q=${encodeURIComponent(q)}`;
  }

  if (resultsHeading) {
    resultsHeading.focus();
  }
  announce(`Route comparison ready. ${data.options.length} modes evaluated.`);
}
