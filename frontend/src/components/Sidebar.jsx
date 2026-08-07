export default function Sidebar({
  view,
  setView,
  reviewCount,
  onReload,
  loading,
  onRefreshAll,
  refreshingAll,
  onAddCompany,
  hasCompanies,
}) {
  return (
    <div className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">FT</div>
        <div className="sidebar-brand-text">
          Franchise Tax
          <br />
          Status Tracker
        </div>
      </div>

      <div className="sidebar-nav">
        <button
          className={view === "dashboard" ? "active" : ""}
          onClick={() => setView("dashboard")}
        >
          🏠 Dashboard
        </button>
        <button
          className={view === "manual-review" ? "active" : ""}
          onClick={() => setView("manual-review")}
        >
          🔍 Manual Review
          {reviewCount > 0 && <span className="badge-count">{reviewCount}</span>}
        </button>
      </div>

      <div className="sidebar-actions">
        <button className="pill-btn" onClick={onReload} disabled={loading}>
          {loading ? <span className="spinner dark" /> : "⟳"} Reload
        </button>
        <button
          className="pill-btn"
          onClick={onRefreshAll}
          disabled={refreshingAll || !hasCompanies}
          title="Re-check status for every tracked company"
        >
          {refreshingAll ? <span className="spinner dark" /> : "⟳⟳"} Refresh All
        </button>
        <button className="pill-btn pill-btn-accent" onClick={onAddCompany}>
          + Add Company
        </button>
      </div>
    </div>
  );
}
