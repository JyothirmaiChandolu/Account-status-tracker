export default function StatCards({ stats }) {
  const cards = [
    { label: "Total Companies", value: stats.total_companies, icon: "🏢", dark: true },
    { label: "Active", value: stats.active_count, icon: "✅" },
    { label: "Needs Review", value: stats.needs_review_count, icon: "⚠️" },
    { label: "States Tracked", value: stats.states_tracked, icon: "📍" },
  ];

  return (
    <div className="stat-grid">
      {cards.map((c) => (
        <div className={`stat-card ${c.dark ? "dark" : ""}`} key={c.label}>
          <div className="stat-card-top">
            <span>{c.label}</span>
            <span className="stat-icon">{c.icon}</span>
          </div>
          <div className="stat-value">{c.value}</div>
        </div>
      ))}
    </div>
  );
}
