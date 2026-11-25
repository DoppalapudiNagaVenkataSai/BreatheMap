/**
 * Shared Leaflet map helper with distinct colors & dash patterns per mode
 */
export const MODE_STYLES = {
  walk: { color: "#1e8e3e", dashArray: "4, 8", label: "Walk (dotted)" },
  cycle: { color: "#0b57d0", dashArray: "12, 6", label: "Cycle (dashed)" },
  car: { color: "#d93025", dashArray: null, label: "Car (solid)" },
  auto: { color: "#e37400", dashArray: "10, 4, 2, 4", label: "Auto (dash-dot)" },
  bus: { color: "#7b1fa2", dashArray: "16, 4", label: "Bus (long dash)" },
  metro: { color: "#00796b", dashArray: "2, 6", label: "Metro (straight-line est.)" },
};

export class RouteMap {
  constructor(containerId) {
    this.containerId = containerId;
    this.map = null;
    this.layerGroup = null;
    this.modeLayers = new Map();
  }

  init(centerLat = 28.6315, centerLon = 77.2167) {
    if (this.map || typeof L === "undefined") return;
    this.map = L.map(this.containerId).setView([centerLat, centerLon], 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(this.map);
    this.layerGroup = L.layerGroup().addTo(this.map);
  }

  renderComparison(origin, destination, options, reports = []) {
    if (!this.map) this.init(origin.lat, origin.lon);
    if (!this.map || !this.layerGroup) return;

    this.layerGroup.clearLayers();
    this.modeLayers.clear();

    const bounds = L.latLngBounds([[origin.lat, origin.lon], [destination.lat, destination.lon]]);

    // Origin & Destination markers (circleMarkers avoid external PNG 404s)
    L.circleMarker([origin.lat, origin.lon], {
      radius: 8,
      color: "#1e8e3e",
      fillColor: "#1e8e3e",
      fillOpacity: 1,
    })
      .bindPopup(`Origin: ${origin.label}`)
      .addTo(this.layerGroup);

    L.circleMarker([destination.lat, destination.lon], {
      radius: 8,
      color: "#d93025",
      fillColor: "#d93025",
      fillOpacity: 1,
    })
      .bindPopup(`Destination: ${destination.label}`)
      .addTo(this.layerGroup);

    // Draw routed polylines
    options.forEach((opt) => {
      const style = MODE_STYLES[opt.mode] || { color: "#444", dashArray: null };
      let latlngs = null;
      if (opt.geometry && opt.geometry.coordinates && opt.geometry.coordinates.length >= 2) {
        // GeoJSON is [lon, lat], Leaflet expects [lat, lon]
        latlngs = opt.geometry.coordinates.map((pt) => [pt[1], pt[0]]);
      } else if (opt.mode === "metro" && opt.status === "available") {
        latlngs = [[origin.lat, origin.lon], [destination.lat, destination.lon]];
      }

      if (latlngs) {
        const line = L.polyline(latlngs, {
          color: style.color,
          dashArray: style.dashArray,
          weight: opt.is_best ? 6 : 4,
          opacity: opt.is_best ? 0.95 : 0.7,
        }).addTo(this.layerGroup);
        this.modeLayers.set(opt.mode, line);
        bounds.extend(line.getBounds());
      }
    });

    // Draw reports along route
    reports.forEach((rep) => {
      if (rep.lat && rep.lon) {
        L.circleMarker([rep.lat, rep.lon], {
          radius: 6,
          color: "#f9ab00",
          fillColor: "#f9ab00",
          fillOpacity: 0.9,
        })
          .bindPopup(`Unverified report: ${rep.category}`)
          .addTo(this.layerGroup);
      }
    });

    this.map.fitBounds(bounds, { padding: [24, 24] });
  }

  highlightMode(mode) {
    this.modeLayers.forEach((layer, m) => {
      if (m === mode) {
        layer.setStyle({ weight: 7, opacity: 1.0 });
        layer.bringToFront();
      } else {
        layer.setStyle({ weight: 3, opacity: 0.45 });
      }
    });
  }
}
