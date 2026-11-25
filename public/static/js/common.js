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
    const doSearch = async () => {
      const q = searchInput.value.trim();
      if (!q) return;
      resultsList.textContent = "Loading results…";
      try {
        const results = await fetchApi(`/api/v1/geocode?q=${encodeURIComponent(q)}`);
        resultsList.textContent = "";
        if (results.length === 0) {
          const li = document.createElement("li");
          li.textContent = "No locations found";
          resultsList.appendChild(li);
          return;
        }
        results.forEach((item) => {
          const li = document.createElement("li");
          const btn = document.createElement("button");
          btn.type = "button";
          btn.textContent = item.label;
          btn.addEventListener("click", () => {
            const newLoc = { label: item.label, lat: item.lat, lon: item.lon };
            state.set(KEYS.LOCATION, newLoc);
            updateLocationLabel(newLoc.label);
            dialog.close();
            emitChange();
          });
          li.appendChild(btn);
          resultsList.appendChild(li);
        });
      } catch (e) {
        resultsList.textContent = "Search service busy. Try again.";
      }
    };
    btnSearch.addEventListener("click", doSearch);
    searchInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        doSearch();
      }
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
