/**
 * Shared location bar, settings, and ARIA announcer
 */
import { fetchApi } from "./api.js";
import { state, KEYS } from "./state.js";

export const DEFAULT_LOCATION = {
  label: "Connaught Place, New Delhi",
  lat: 28.6315,
  lon: 77.2167,
};

export function parseLatLonText(q) {
  const m = /^\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*$/.exec(q || "");
  if (!m) return null;
  const lat = parseFloat(m[1]);
  const lon = parseFloat(m[2]);
  if (lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
    return {
      name: `${lat.toFixed(4)}, ${lon.toFixed(4)}`,
      subtitle: "Coordinates",
      label: `${lat.toFixed(4)}, ${lon.toFixed(4)}`,
      lat,
      lon,
    };
  }
  return null;
}

function splitPlaceLabel(item) {
  if (item.name) {
    return { title: item.name, subtitle: item.subtitle || "" };
  }
  const parts = String(item.label || "").split(",");
  const title = parts[0]?.trim() || item.label || "";
  const subtitle = parts.slice(1).join(",").trim();
  return { title, subtitle };
}

/**
 * Attach Google Maps-style debounced place autocomplete to a text input.
 */
export function attachPlaceAutocomplete({
  input,
  resultsList,
  searchBtn = null,
  getBiasCoords = null,
  onSelect,
  onInputChange = null,
  debounceMs = 280,
}) {
  if (!input || !resultsList) return;

  let debounceTimer = null;
  let activeController = null;
  let activeIndex = -1;
  let currentItems = [];

  const hideResults = () => {
    resultsList.classList.add("hidden");
    activeIndex = -1;
  };

  const setStatus = (msg) => {
    resultsList.textContent = "";
    const li = document.createElement("li");
    li.className = "results-status";
    li.textContent = msg;
    resultsList.appendChild(li);
    resultsList.classList.remove("hidden");
  };

  const highlightIndex = (nextIdx) => {
    const buttons = resultsList.querySelectorAll("li button");
    if (!buttons.length) return;
    buttons.forEach((b) => b.classList.remove("is-active"));
    activeIndex = ((nextIdx % buttons.length) + buttons.length) % buttons.length;
    buttons[activeIndex].classList.add("is-active");
    buttons[activeIndex].scrollIntoView({ block: "nearest" });
  };

  const selectItem = (item) => {
    const loc = { label: item.label, lat: item.lat, lon: item.lon };
    input.value = item.label;
    hideResults();
    onSelect(loc);
  };

  const runSearch = async ({ autoSelectCoord = false } = {}) => {
    const q = input.value.trim();
    if (q.length < 2) {
      hideResults();
      return;
    }

    const directCoord = parseLatLonText(q);
    if (directCoord) {
      if (autoSelectCoord) {
        selectItem(directCoord);
      } else {
        currentItems = [directCoord];
        renderItems([directCoord]);
      }
      return;
    }

    if (activeController) activeController.abort();
    activeController = new AbortController();
    const { signal } = activeController;

    setStatus("Searching places…");

    const params = new URLSearchParams({ q: q.slice(0, 250) });
    const bias = typeof getBiasCoords === "function" ? getBiasCoords() : null;
    if (bias && Number.isFinite(bias.lat) && Number.isFinite(bias.lon)) {
      params.set("lat", String(bias.lat));
      params.set("lon", String(bias.lon));
    }

    try {
      const headers = {};
      if (state.get(KEYS.DEMO, false)) headers["X-BreatheMap-Demo"] = "true";
      const res = await fetch(`/api/v1/geocode?${params.toString()}`, { headers, signal });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setStatus(json?.error?.message || `Search unavailable (${res.status}) — try again.`);
        return;
      }
      const items = Array.isArray(json.data) ? json.data : [];
      currentItems = items;
      activeIndex = -1;
      renderItems(items, q);
    } catch (err) {
      if (err?.name === "AbortError") return;
      setStatus("Search is busy — try again in a few seconds.");
    }
  };

  const renderItems = (items, queryText = "") => {
    resultsList.textContent = "";
    if (!items.length) {
      setStatus(
        queryText
          ? `No places found for '${queryText}'. Try a nearby landmark or area.`
          : "No places found."
      );
      return;
    }
    items.forEach((item) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      const optBtn = document.createElement("button");
      optBtn.type = "button";

      const pin = document.createElement("span");
      pin.className = "place-pin";
      pin.setAttribute("aria-hidden", "true");
      pin.textContent = "📍";

      const textWrap = document.createElement("span");
      textWrap.className = "place-text";
      const { title, subtitle } = splitPlaceLabel(item);

      const titleEl = document.createElement("span");
      titleEl.className = "place-title";
      titleEl.textContent = title;
      textWrap.appendChild(titleEl);

      if (subtitle) {
        const subEl = document.createElement("span");
        subEl.className = "place-subtitle";
        subEl.textContent = subtitle;
        textWrap.appendChild(subEl);
      }

      optBtn.appendChild(pin);
      optBtn.appendChild(textWrap);
      optBtn.addEventListener("click", () => selectItem(item));
      li.appendChild(optBtn);
      resultsList.appendChild(li);
    });
    resultsList.classList.remove("hidden");
  };

  input.addEventListener("input", () => {
    if (typeof onInputChange === "function") onInputChange(input.value);
    if (debounceTimer) clearTimeout(debounceTimer);
    const q = input.value.trim();
    if (q.length < 2) {
      if (activeController) activeController.abort();
      hideResults();
      return;
    }
    debounceTimer = setTimeout(() => {
      runSearch({ autoSelectCoord: false });
    }, debounceMs);
  });

  input.addEventListener("keydown", (e) => {
    const isVisible = !resultsList.classList.contains("hidden");
    if (e.key === "ArrowDown" && isVisible) {
      e.preventDefault();
      highlightIndex(activeIndex + 1);
    } else if (e.key === "ArrowUp" && isVisible) {
      e.preventDefault();
      highlightIndex(activeIndex - 1);
    } else if (e.key === "Escape") {
      hideResults();
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (isVisible && activeIndex >= 0 && currentItems[activeIndex]) {
        selectItem(currentItems[activeIndex]);
      } else {
        if (debounceTimer) clearTimeout(debounceTimer);
        runSearch({ autoSelectCoord: true });
      }
    }
  });

  if (searchBtn) {
    searchBtn.addEventListener("click", () => {
      if (debounceTimer) clearTimeout(debounceTimer);
      runSearch({ autoSelectCoord: true });
    });
  }

  document.addEventListener("click", (e) => {
    const target = e.target;
    if (target !== input && target !== searchBtn && !resultsList.contains(target)) {
      hideResults();
    }
  });
}

export function announce(message) {
  const el = document.getElementById("aria-announcer");
  if (el) {
    el.textContent = "";
    setTimeout(() => {
      el.textContent = message;
    }, 30);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initLocationBar();
  initSettings();
});

function emitChange() {
  window.dispatchEvent(new CustomEvent("bm:contextchange"));
}

function initLocationBar() {
  const locText = document.getElementById("current-location-text");
  const dialog = document.getElementById("location-dialog");
  const btnChange = document.getElementById("btn-change-location");
  const btnClose = document.getElementById("btn-close-dialog");
  const btnGPS = document.getElementById("btn-use-gps");
  const btnDelhi = document.getElementById("btn-use-delhi");
  const searchInput = document.getElementById("location-search-input");
  const btnSearch = document.getElementById("btn-search-loc");
  const resultsList = document.getElementById("search-results-list");
  const demoBanner = document.getElementById("demo-banner");
  const btnToggleDemo = document.getElementById("btn-toggle-demo");

  function updateLocationLabel(label) {
    if (locText) locText.textContent = label;
  }

  function updateDemoBanner() {
    const isDemo = state.get(KEYS.DEMO, false);
    if (demoBanner) {
      if (isDemo) demoBanner.classList.remove("hidden");
      else demoBanner.classList.add("hidden");
    }
  }

  const savedLoc = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
  updateLocationLabel(savedLoc.label);
  updateDemoBanner();

  if (btnChange && dialog) {
    btnChange.addEventListener("click", () => dialog.showModal());
  }
  if (btnClose && dialog) {
    btnClose.addEventListener("click", () => dialog.close());
  }
  if (btnToggleDemo) {
    btnToggleDemo.addEventListener("click", () => {
      state.set(KEYS.DEMO, false);
      updateDemoBanner();
      emitChange();
    });
  }

  if (btnDelhi && dialog) {
    btnDelhi.addEventListener("click", () => {
      state.set(KEYS.DEMO, true);
      state.set(KEYS.LOCATION, DEFAULT_LOCATION);
      updateLocationLabel(DEFAULT_LOCATION.label);
      updateDemoBanner();
      dialog.close();
      emitChange();
    });
  }

  if (btnGPS && dialog) {
    btnGPS.addEventListener("click", () => {
      if (!navigator.geolocation) {
        announce("Geolocation is not supported by your browser.");
        return;
      }
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const lat = pos.coords.latitude;
          const lon = pos.coords.longitude;
          try {
            const rev = await fetchApi(`/api/v1/reverse?lat=${lat}&lon=${lon}`);
            const loc = { label: rev.label, lat, lon };
            state.set(KEYS.LOCATION, loc);
            state.set(KEYS.DEMO, false);
            updateLocationLabel(loc.label);
            updateDemoBanner();
            dialog.close();
            emitChange();
          } catch (e) {
            const loc = { label: `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon };
            state.set(KEYS.LOCATION, loc);
            updateLocationLabel(loc.label);
            dialog.close();
            emitChange();
          }
        },
        () => {
          announce("Unable to retrieve your location. Try searching for an area.");
        }
      );
    });
  }

  if (btnSearch && searchInput && resultsList) {
    attachPlaceAutocomplete({
      input: searchInput,
      resultsList,
      searchBtn,
      getBiasCoords: () => state.get(KEYS.LOCATION, DEFAULT_LOCATION),
      onSelect: (newLoc) => {
        state.set(KEYS.LOCATION, newLoc);
        state.set(KEYS.DEMO, false);
        updateLocationLabel(newLoc.label);
        updateDemoBanner();
        dialog.close();
        emitChange();
      },
    });
  }
}

function initSettings() {
  const scaleSelect = document.getElementById("scale-select");
  const sensitiveToggle = document.getElementById("sensitive-toggle");

  const savedScale = state.get(KEYS.SCALE, "naqi");
  if (scaleSelect) {
    scaleSelect.value = savedScale;
    scaleSelect.addEventListener("change", (e) => {
      state.set(KEYS.SCALE, e.target.value);
      emitChange();
    });
  }

  const savedSensitive = state.get(KEYS.SENSITIVE, false);
  if (sensitiveToggle) {
    sensitiveToggle.checked = savedSensitive;
    sensitiveToggle.addEventListener("change", (e) => {
      state.set(KEYS.SENSITIVE, e.target.checked);
      emitChange();
    });
  }
}
