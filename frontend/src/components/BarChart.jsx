import { useState } from "react";
import { formatDateIST } from "../format";

const STATUS_COLOR = {
  active: "var(--status-good)",
  delinquent: "var(--status-serious)",
  forfeited: "var(--status-critical)",
  suspended: "var(--status-critical)",
  manual_review_needed: "var(--status-warning)",
  unknown: "var(--status-muted)",
};

// Ordinal rank — data is categorical, not a magnitude, so bar height encodes
// severity order (higher = better standing), not a counted value.
const STATUS_RANK = {
  active: 4,
  delinquent: 3,
  manual_review_needed: 2,
  forfeited: 1,
  suspended: 1,
  unknown: 0.4,
};

const Y_TICKS = [
  { pct: 100, label: "Active" },
  { pct: 75, label: "Delinquent" },
  { pct: 50, label: "Manual Review" },
  { pct: 25, label: "Forfeited / Suspended" },
];

const LEGEND_ITEMS = [
  { status: "active", label: "Active" },
  { status: "delinquent", label: "Delinquent" },
  { status: "forfeited", label: "Forfeited / Suspended" },
  { status: "manual_review_needed", label: "Manual Review" },
  { status: "unknown", label: "No clear status" },
];

function shortDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short" });
}

export default function BarChart({ checks }) {
  const [hovered, setHovered] = useState(null);

  if (!checks || checks.length === 0) return null;

  // checks arrive newest-first from the API; the chart reads left (oldest) to right (newest)
  const chronological = [...checks].reverse();
  const hoveredCheck = hovered != null ? chronological[hovered] : null;

  const maxLabels = 6;
  const labelEvery = Math.max(1, Math.ceil(chronological.length / maxLabels));

  return (
    <div className="bar-chart-wrap">
      <div className="bar-chart-plot">
        <div className="bar-chart-yaxis">
          {Y_TICKS.map((t) => (
            <span key={t.label} style={{ bottom: `${t.pct}%` }}>{t.label}</span>
          ))}
        </div>

        <div className="bar-chart-bars">
          {chronological.map((chk, i) => {
            const rank = STATUS_RANK[chk.status] ?? 0.4;
            const pct = (rank / 4) * 100;
            return (
              <div
                key={chk.id}
                className="bar-chart-col"
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(i)}
                onBlur={() => setHovered(null)}
                tabIndex={0}
              >
                <div
                  className="bar-chart-bar"
                  style={{ height: `${pct}%`, background: STATUS_COLOR[chk.status] || "var(--status-muted)" }}
                />
              </div>
            );
          })}
        </div>
      </div>

      <div className="bar-chart-xaxis">
        {chronological.map((chk, i) => (
          <span key={chk.id}>{i % labelEvery === 0 ? shortDate(chk.checked_at) : ""}</span>
        ))}
      </div>

      <div className="uptime-tooltip-slot">
        {hoveredCheck ? (
          <span>
            <strong>{hoveredCheck.status.replace(/_/g, " ")}</strong>
            {" · "}
            {formatDateIST(hoveredCheck.checked_at)}
          </span>
        ) : (
          <span className="company-sub">
            {chronological.length} check{chronological.length === 1 ? "" : "s"} — oldest to newest, hover a bar for details
          </span>
        )}
      </div>

      <div className="uptime-legend">
        {LEGEND_ITEMS.map((item) => (
          <span className="uptime-legend-item" key={item.status}>
            <span className="uptime-legend-dot" style={{ background: STATUS_COLOR[item.status] }} />
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}
