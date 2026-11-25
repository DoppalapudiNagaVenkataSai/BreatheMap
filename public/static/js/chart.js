/**
 * Accessible SVG bar chart generator
 */
export function renderBarChart(container, times, values) {
  container.innerHTML = "";
  if (!values || values.length === 0) return;

  const maxVal = Math.max(...values.map(v => v || 0), 100);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${times.length * 28} 140`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "24-hour PM2.5 concentration bar chart");

  values.forEach((v, idx) => {
    const val = v || 0;
    const height = Math.round((val / maxVal) * 90);
    const y = 100 - height;
    const x = idx * 28 + 4;

    const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    rect.setAttribute("x", x);
    rect.setAttribute("y", y);
    rect.setAttribute("width", "20");
    rect.setAttribute("height", height);
    rect.setAttribute("rx", "3");

    // Color code according to CPCB NAQI bands
    let fill = "#1e8e3e";
    if (val > 250) fill = "#7b1fa2";
    else if (val > 120) fill = "#a50e0e";
    else if (val > 90) fill = "#d93025";
    else if (val > 60) fill = "#e37400";
    else if (val > 30) fill = "#137333";

    rect.setAttribute("fill", fill);
    svg.appendChild(rect);

    // Hour label
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", x + 10);
    text.setAttribute("y", "125");
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("font-size", "10");
    text.setAttribute("fill", "#5f6368");
    const hour = times[idx] ? times[idx].split("T")[1]?.slice(0, 2) : "";
    text.textContent = hour;
    svg.appendChild(text);
  });

  container.appendChild(svg);
}
