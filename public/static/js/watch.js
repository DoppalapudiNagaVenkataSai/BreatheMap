/**
 * BreatheWatch community reports controller
 */
import { fetchApi } from "./api.js";
import { state, KEYS } from "./state.js";
import { DEFAULT_LOCATION } from "./common.js";

const CATEGORY_LABELS = {
  smoke: "Smoke",
  open_burning: "Open burning",
  construction_dust: "Construction dust",
  road_dust: "Road dust",
  vehicle_emissions: "Vehicle emissions",
  industrial_emissions: "Industrial emissions",
  odour: "Odour",
  other: "Other",
};

const CATEGORY_TTL_HOURS = {
  smoke: 12,
  open_burning: 12,
  odour: 12,
  vehicle_emissions: 6,
  construction_dust: 24,
  road_dust: 24,
  industrial_emissions: 48,
  other: 24,
};

let watchMap = null;
let watchLayer = null;
let pickMode = false;
let pickedLocation = null;
let duplicateReportId = null;

document.addEventListener("DOMContentLoaded", () => {
  initWatchView();
});

window.addEventListener("bm:contextchange", () => {
  loadNearbyReports();
});

function initWatchMap(lat, lon) {
  if (watchMap || typeof L === "undefined") return;
  const container = document.getElementById("watch-map");
  if (!container) return;

  watchMap = L.map("watch-map").setView([lat, lon], 13);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(watchMap);
  watchLayer = L.layerGroup().addTo(watchMap);

  watchMap.on("click", (evt) => {
    if (!pickMode) return;
    pickedLocation = {
      lat: Number(evt.latlng.lat.toFixed(3)),
      lon: Number(evt.latlng.lng.toFixed(3)),
    };
    pickMode = false;
    updateSelectedCoordsText();
    showStatus("Report location set from map.");
  });
}

function initWatchView() {
  const loc = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
  pickedLocation = { lat: Number(loc.lat.toFixed(3)), lon: Number(loc.lon.toFixed(3)) };
  updateSelectedCoordsText();
  initWatchMap(loc.lat, loc.lon);

  const toggleBtn = document.getElementById("btn-toggle-report-form");
  const panel = document.getElementById("watch-report-panel");
  const cancelBtn = document.getElementById("btn-cancel-report");
  const descInput = document.getElementById("report-description");
  const counterEl = document.getElementById("report-desc-counter");
  const form = document.getElementById("watch-report-form");

  if (toggleBtn && panel) {
    toggleBtn.addEventListener("click", () => {
      const hidden = panel.classList.toggle("hidden");
      toggleBtn.setAttribute("aria-expanded", String(!hidden));
    });
  }
  if (cancelBtn && panel && toggleBtn) {
    cancelBtn.addEventListener("click", () => {
      panel.classList.add("hidden");
      toggleBtn.setAttribute("aria-expanded", "false");
      pickMode = false;
    });
  }
  if (descInput && counterEl) {
    descInput.addEventListener("input", () => {
      counterEl.textContent = `${descInput.value.length} / 280`;
    });
  }

  document.getElementById("filter-category")?.addEventListener("change", loadNearbyReports);
  document.getElementById("filter-hours")?.addEventListener("change", loadNearbyReports);
  document.getElementById("filter-radius")?.addEventListener("change", loadNearbyReports);

  document.getElementById("btn-report-use-loc")?.addEventListener("click", handleUseMyLocation);
  document.getElementById("btn-report-pick-map")?.addEventListener("click", () => {
    pickMode = true;
    showStatus("Click anywhere on the map to choose the report location.");
  });
  document.getElementById("btn-report-loc-search")?.addEventListener("click", handleLocationSearch);

  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    openConfirmDialog();
  });

  document.getElementById("btn-confirm-cancel")?.addEventListener("click", () => {
    document.getElementById("watch-confirm-dialog")?.close();
  });
  document.getElementById("btn-confirm-post")?.addEventListener("click", submitReport);

  document.getElementById("btn-duplicate-confirm")?.addEventListener("click", async () => {
    if (duplicateReportId) {
      await handleConfirmVote(duplicateReportId);
      duplicateReportId = null;
      document.getElementById("btn-duplicate-confirm")?.classList.add("hidden");
    }
  });

  loadNearbyReports();
}

function handleUseMyLocation() {
  const fallback = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
  if (!navigator.geolocation) {
    pickedLocation = { lat: Number(fallback.lat.toFixed(3)), lon: Number(fallback.lon.toFixed(3)) };
    updateSelectedCoordsText();
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      pickedLocation = {
        lat: Number(pos.coords.latitude.toFixed(3)),
        lon: Number(pos.coords.longitude.toFixed(3)),
      };
      updateSelectedCoordsText();
      showStatus("Using your device location.");
    },
    () => {
      pickedLocation = { lat: Number(fallback.lat.toFixed(3)), lon: Number(fallback.lon.toFixed(3)) };
      updateSelectedCoordsText();
    },
    { timeout: 6000 }
  );
}

async function handleLocationSearch() {
  const input = document.getElementById("report-loc-search");
  const list = document.getElementById("report-loc-results");
  if (!input || !list) return;
  const q = input.value.trim();
  if (q.length < 2) return;

  try {
    const results = await fetchApi(`/api/v1/geocode?q=${encodeURIComponent(q)}`);
    list.textContent = "";
    if (!results || results.length === 0) {
      const li = document.createElement("li");
      li.textContent = `No places found for '${q}'.`;
      list.appendChild(li);
      list.classList.remove("hidden");
      return;
    }
    results.forEach((place) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "result-option-btn";
      btn.textContent = place.label;
      btn.addEventListener("click", () => {
        pickedLocation = {
          lat: Number(Number(place.lat).toFixed(3)),
          lon: Number(Number(place.lon).toFixed(3)),
        };
        updateSelectedCoordsText();
        list.classList.add("hidden");
      });
      li.appendChild(btn);
      list.appendChild(li);
    });
    list.classList.remove("hidden");
  } catch (err) {
    showError(err.message || "Search failed.");
  }
}

function updateSelectedCoordsText() {
  const el = document.getElementById("report-selected-coords");
  if (el && pickedLocation) {
    el.textContent = `Selected coordinates: ${pickedLocation.lat.toFixed(3)}, ${pickedLocation.lon.toFixed(3)}`;
  }
}

function openConfirmDialog() {
  clearBanners();
  const category = document.getElementById("report-category")?.value || "other";
  const desc = (document.getElementById("report-description")?.value || "").trim();
  if (desc.length < 10) {
    showError("Please enter at least 10 characters describing what you see.");
    return;
  }

  const ttl = CATEGORY_TTL_HOURS[category] || 24;
  const dialog = document.getElementById("watch-confirm-dialog");
  const msg = document.getElementById("confirm-dialog-message");
  const sumCat = document.getElementById("confirm-summary-category");
  const sumDesc = document.getElementById("confirm-summary-desc");
  const sumLoc = document.getElementById("confirm-summary-loc");

  if (msg) msg.textContent = `Post this report publicly? It will be visible to others for up to ${ttl} hours.`;
  if (sumCat) sumCat.textContent = CATEGORY_LABELS[category] || category;
  if (sumDesc) sumDesc.textContent = desc;
  if (sumLoc && pickedLocation) {
    sumLoc.textContent = `${pickedLocation.lat.toFixed(3)}, ${pickedLocation.lon.toFixed(3)}`;
  }
  if (dialog && typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    submitReport();
  }
}

async function submitReport() {
  const dialog = document.getElementById("watch-confirm-dialog");
  if (dialog && dialog.open) dialog.close();

  const userLoc = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
  const category = document.getElementById("report-category")?.value || "other";
  const description = (document.getElementById("report-description")?.value || "").trim();
  const targetLoc = pickedLocation || userLoc;

  try {
    const res = await fetchApi("/api/v1/reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category,
        description,
        lat: targetLoc.lat,
        lon: targetLoc.lon,
        user_lat: userLoc.lat,
        user_lon: userLoc.lon,
      }),
    });

    if (res.duplicate_of) {
      duplicateReportId = res.duplicate_of;
      showStatus(res.message || "Someone already reported this — tap 'I see this too'.", true);
    } else {
      showStatus(res.message || "Thanks — your report is visible.");
      const form = document.getElementById("watch-report-form");
      form?.reset();
      const counterEl = document.getElementById("report-desc-counter");
      if (counterEl) counterEl.textContent = "0 / 280";
      document.getElementById("watch-report-panel")?.classList.add("hidden");
      document.getElementById("btn-toggle-report-form")?.setAttribute("aria-expanded", "false");
    }
    await loadNearbyReports();
  } catch (err) {
    showError(err.message || "Could not post report.");
  }
}

async function loadNearbyReports() {
  const loc = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
  const cat = document.getElementById("filter-category")?.value || "";
  const hours = document.getElementById("filter-hours")?.value || "24";
  const radius = document.getElementById("filter-radius")?.value || "3";

  const params = new URLSearchParams({
    lat: String(loc.lat),
    lon: String(loc.lon),
    radius_km: radius,
    hours,
  });
  if (cat) params.set("category", cat);

  const listEl = document.getElementById("watch-reports-list");
  const countEl = document.getElementById("watch-count");
  const warnEl = document.getElementById("watch-warning-note");

  try {
    const res = await fetch("/api/v1/reports/nearby?" + params.toString(), {
      headers: state.get(KEYS.DEMO, false) ? { "X-BreatheMap-Demo": "1" } : {},
    });
    const payload = await res.json();
    if (!res.ok) {
      throw new Error(payload?.error?.message || "Unable to load reports.");
    }

    const reports = payload.data || [];
    const warnings = payload.meta?.warnings || [];

    if (warnEl) {
      if (warnings.length > 0) {
        warnEl.textContent = warnings.join(" ");
        warnEl.classList.remove("hidden");
      } else {
        warnEl.classList.add("hidden");
      }
    }

    if (countEl) countEl.textContent = String(reports.length);
    renderReportsList(listEl, reports);
    renderReportsMap(loc, reports);
  } catch (err) {
    if (listEl) {
      listEl.textContent = "";
      const li = document.createElement("li");
      li.className = "empty-state";
      li.textContent = err.message || "Community reports temporarily unavailable.";
      listEl.appendChild(li);
    }
  }
}

function formatTimeAgo(isoStr) {
  const created = new Date(isoStr);
  const diffMin = Math.max(1, Math.round((Date.now() - created.getTime()) / 60000));
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.round(diffMin / 60);
  return `${diffHr} h ago`;
}

function renderReportsList(listEl, reports) {
  if (!listEl) return;
  listEl.textContent = "";

  if (!reports.length) {
    const li = document.createElement("li");
    li.className = "empty-state";
    li.textContent = "No community reports in this area and time window.";
    listEl.appendChild(li);
    return;
  }

  reports.forEach((rep) => {
    const li = document.createElement("li");
    li.className = "watch-report-card";

    const header = document.createElement("div");
    header.className = "watch-card-header";

    const catBadge = document.createElement("span");
    catBadge.className = "watch-category-badge";
    catBadge.textContent = CATEGORY_LABELS[rep.category] || rep.category;

    const meta = document.createElement("span");
    meta.className = "watch-card-meta";
    const dist = rep.distance_km !== undefined ? `${rep.distance_km.toFixed(1)} km away · ` : "";
    meta.textContent = `${dist}${formatTimeAgo(rep.created_at)}`;

    header.appendChild(catBadge);
    header.appendChild(meta);

    const desc = document.createElement("p");
    desc.className = "watch-card-desc";
    desc.textContent = rep.description;

    const label = document.createElement("p");
    label.className = "watch-unverified-label";
    label.textContent = rep.status_label || "Unverified community report";

    const footer = document.createElement("div");
    footer.className = "watch-card-footer";

    const confText = document.createElement("span");
    confText.className = "watch-confirm-count";
    const count = rep.confirmations || 0;
    confText.textContent = `${count} ${count === 1 ? "person" : "people"} saw this too`;

    const actions = document.createElement("div");
    actions.className = "watch-card-actions";

    const btnConfirm = document.createElement("button");
    btnConfirm.type = "button";
    btnConfirm.className = "btn-secondary btn-sm";
    btnConfirm.textContent = "I see this too";
    btnConfirm.addEventListener("click", () => handleConfirmVote(rep.id));

    const btnFlag = document.createElement("button");
    btnFlag.type = "button";
    btnFlag.className = "btn-text btn-sm";
    btnFlag.textContent = "Flag";
    btnFlag.addEventListener("click", () => handleFlagVote(rep.id));

    actions.appendChild(btnConfirm);
    actions.appendChild(btnFlag);
    footer.appendChild(confText);
    footer.appendChild(actions);

    li.appendChild(header);
    li.appendChild(desc);
    li.appendChild(label);
    li.appendChild(footer);
    listEl.appendChild(li);
  });
}

function renderReportsMap(centerLoc, reports) {
  if (!watchMap) initWatchMap(centerLoc.lat, centerLoc.lon);
  if (!watchMap || !watchLayer) return;

  watchLayer.clearLayers();
  watchMap.setView([centerLoc.lat, centerLoc.lon], 13);

  L.circleMarker([centerLoc.lat, centerLoc.lon], {
    radius: 7,
    color: "#0b57d0",
    fillColor: "#0b57d0",
    fillOpacity: 0.9,
  })
    .bindPopup("Search centre")
    .addTo(watchLayer);

  reports.forEach((rep) => {
    const marker = L.circleMarker([rep.lat, rep.lon], {
      radius: 7,
      color: "#d93025",
      fillColor: "#f9ab00",
      fillOpacity: 0.9,
    });
    const popupEl = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = CATEGORY_LABELS[rep.category] || rep.category;
    const body = document.createElement("p");
    body.textContent = rep.description;
    popupEl.appendChild(title);
    popupEl.appendChild(body);
    marker.bindPopup(popupEl).addTo(watchLayer);
  });
}

async function handleConfirmVote(reportId) {
  clearBanners();
  try {
    await fetchApi(`/api/v1/reports/${encodeURIComponent(reportId)}/confirm`, {
      method: "POST",
    });
    showStatus("Thanks — your confirmation was recorded.");
    await loadNearbyReports();
  } catch (err) {
    showError(err.message || "Unable to confirm report.");
  }
}

async function handleFlagVote(reportId) {
  clearBanners();
  try {
    await fetchApi(`/api/v1/reports/${encodeURIComponent(reportId)}/flag`, {
      method: "POST",
    });
    showStatus("Report flagged for review.");
    await loadNearbyReports();
  } catch (err) {
    showError(err.message || "Unable to flag report.");
  }
}

function showStatus(msg, showDupBtn = false) {
  const banner = document.getElementById("watch-status-banner");
  const text = document.getElementById("watch-status-text");
  const dupBtn = document.getElementById("btn-duplicate-confirm");
  if (banner && text) {
    text.textContent = msg;
    banner.classList.remove("hidden");
  }
  if (dupBtn) {
    dupBtn.classList.toggle("hidden", !showDupBtn);
  }
}

function showError(msg) {
  const banner = document.getElementById("watch-error-banner");
  const text = document.getElementById("watch-error-text");
  if (banner && text) {
    text.textContent = msg;
    banner.classList.remove("hidden");
  }
}

function clearBanners() {
  document.getElementById("watch-status-banner")?.classList.add("hidden");
  document.getElementById("watch-error-banner")?.classList.add("hidden");
}
