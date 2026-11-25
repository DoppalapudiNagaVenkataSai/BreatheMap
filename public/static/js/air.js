/**
 * Air view controller
 */
import { fetchApi } from "./api.js";
import { state, KEYS } from "./state.js";
import { renderBarChart } from "./chart.js";
import { DEFAULT_LOCATION } from "./common.js";

document.addEventListener("DOMContentLoaded", () => {
  initAirView();
});

window.addEventListener("bm:contextchange", () => {
  loadAirData();
});

function initAirView() {
  const btnToggleTable = document.getElementById("btn-toggle-table");
  const chartContainer = document.getElementById("chart-container");
  const tableContainer = document.getElementById("table-container");

  if (btnToggleTable && chartContainer && tableContainer) {
    btnToggleTable.addEventListener("click", () => {
      const isTableHidden = tableContainer.classList.contains("hidden");
      if (isTableHidden) {
        tableContainer.classList.remove("hidden");
        chartContainer.classList.add("hidden");
        btnToggleTable.textContent = "Show as chart";
        btnToggleTable.setAttribute("aria-expanded", "true");
      } else {
        tableContainer.classList.add("hidden");
        chartContainer.classList.remove("hidden");
        btnToggleTable.textContent = "Show as table";
        btnToggleTable.setAttribute("aria-expanded", "false");
      }
    });
  }

  loadAirData();
}

async function loadAirData() {
  const loc = state.get(KEYS.LOCATION, DEFAULT_LOCATION);
  const scale = state.get(KEYS.SCALE, "naqi");

  const aqiBadge = document.getElementById("aqi-level-badge");
  const aqiNumber = document.getElementById("aqi-number");
  const aqiBand = document.getElementById("aqi-band");
  const domText = document.getElementById("dominant-pollutant-text");
  const provNote = document.getElementById("provenance-note");

  const wTemp = document.getElementById("w-temp");
  const wHum = document.getElementById("w-hum");
  const wWind = document.getElementById("w-wind");

  const valPm25 = document.getElementById("val-pm25");
  const valPm10 = document.getElementById("val-pm10");
  const valNo2 = document.getElementById("val-no2");
  const valO3 = document.getElementById("val-o3");
  const valCo = document.getElementById("val-co");
  const valSo2 = document.getElementById("val-so2");

  const cleanestTime = document.getElementById("cleanest-time");
  const cleanestAvg = document.getElementById("cleanest-avg");
  const worstTime = document.getElementById("worst-time");
  const worstAvg = document.getElementById("worst-avg");

  const chartContainer = document.getElementById("chart-container");
  const tableBody = document.getElementById("hourly-table-body");

  try {
    const data = await fetchApi(
      `/api/v1/air?lat=${loc.lat}&lon=${loc.lon}&scale=${scale}`
    );

    if (aqiBadge) {
      aqiBadge.className = `aqi-badge level-${data.level.toLowerCase()}`;
    }
    if (aqiNumber) aqiNumber.textContent = data.index !== null ? data.index : "--";
    if (aqiBand) aqiBand.textContent = data.band || "Unknown";
    if (domText) domText.textContent = `Dominant pollutant: ${(data.dominant_pollutant || "PM2.5").toUpperCase()}`;
    if (provNote) provNote.textContent = `${data.provenance.source} · Updated ${data.provenance.observed_at.slice(11, 16)} UTC`;

    if (wTemp) wTemp.textContent = `${data.weather.temperature ?? "--"}°C`;
    if (wHum) wHum.textContent = `${data.weather.humidity ?? "--"}%`;
    if (wWind) wWind.textContent = `${data.weather.wind_speed ?? "--"} km/h`;

    if (valPm25) valPm25.textContent = `${data.pollutants.pm25 ?? "--"} µg/m³`;
    if (valPm10) valPm10.textContent = `${data.pollutants.pm10 ?? "--"} µg/m³`;
    if (valNo2) valNo2.textContent = `${data.pollutants.no2 ?? "--"} µg/m³`;
    if (valO3) valO3.textContent = `${data.pollutants.o3 ?? "--"} µg/m³`;
    if (valCo) valCo.textContent = `${data.pollutants.co ?? "--"} mg/m³`;
    if (valSo2) valSo2.textContent = `${data.pollutants.so2 ?? "--"} µg/m³`;

    if (data.windows.cleanest && cleanestTime && cleanestAvg) {
      cleanestTime.textContent = `${data.windows.cleanest.start_time.slice(11, 16)} - ${data.windows.cleanest.end_time.slice(11, 16)}`;
      cleanestAvg.textContent = `${data.windows.cleanest.avg_pm25} µg/m³ PM2.5`;
    }
    if (data.windows.worst && worstTime && worstAvg) {
      worstTime.textContent = `${data.windows.worst.start_time.slice(11, 16)} - ${data.windows.worst.end_time.slice(11, 16)}`;
      worstAvg.textContent = `${data.windows.worst.avg_pm25} µg/m³ PM2.5`;
    }

    if (chartContainer && data.hourly) {
      renderBarChart(chartContainer, data.hourly.times, data.hourly.pm25);
    }

    if (tableBody && data.hourly) {
      tableBody.textContent = "";
      data.hourly.times.forEach((t, i) => {
        const row = document.createElement("tr");
        const cellT = document.createElement("td");
        cellT.textContent = t.slice(11, 16);
        const cellV = document.createElement("td");
        cellV.textContent = data.hourly.pm25[i] ?? "--";
        row.appendChild(cellT);
        row.appendChild(cellV);
        tableBody.appendChild(row);
      });
    }
  } catch (e) {
    if (provNote) provNote.textContent = "Data temporarily unavailable";
  }
}
