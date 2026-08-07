import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDateIST } from "../format";
import BarChart from "./BarChart";

const MARKER_COLOR = {
  active: "#0ca30c",
  delinquent: "#ec835a",
  forfeited: "#d03b3b",
  suspended: "#d03b3b",
  unknown: "#898781",
  manual_review_needed: "#fab219",
};

const HISTORY_LIMIT = 5;

export default function CompanyDetailModal({ companyId, onClose, onRefresh, onDelete, refreshingId }) {
  const [company, setCompany] = useState(null);
  const [error, setError] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [expandedShot, setExpandedShot] = useState(null);

  async function load() {
    try {
      const data = await api.getCompany(companyId);
      setCompany(data);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    setShowHistory(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  useEffect(() => {
    if (refreshingId === null && company) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshingId]);

  const recentChecks = company ? company.status_checks.slice(0, HISTORY_LIMIT) : [];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{company ? company.name : "Loading..."}</h2>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        {error && <div className="error-text">{error}</div>}

        {company && (
          <>
            <div className="company-sub" style={{ marginBottom: 16 }}>
              {company.state}
              {company.entity_number && ` · Entity #${company.entity_number}`}
              {company.parent_group && ` · Part of ${company.parent_group}`}
            </div>

            <div style={{ display: "flex", gap: 10, marginBottom: 22 }}>
              <button
                className="btn btn-primary"
                onClick={() => onRefresh(company.id)}
                disabled={refreshingId === company.id}
              >
                {refreshingId === company.id ? <span className="spinner dark" /> : "⟳"} Check Status Now
              </button>
              <button className="btn btn-secondary" onClick={() => setShowHistory((v) => !v)}>
                {showHistory ? "Hide History" : "History"}
              </button>
              <button className="btn btn-danger" onClick={() => onDelete(company.id, company.name)}>
                Remove Company
              </button>
            </div>

            {company.status_checks.length === 0 ? (
              <div className="empty-state">No checks yet.</div>
            ) : (
              <BarChart checks={company.status_checks} />
            )}

            {showHistory && (
              <div className="timeline" style={{ marginTop: 18 }}>
                {recentChecks.map((chk) => (
                  <div className="timeline-item" key={chk.id}>
                    <div
                      className="timeline-marker"
                      style={{ background: MARKER_COLOR[chk.status] || "#898781" }}
                    />
                    <div className="timeline-body">
                      <div className="timeline-meta">
                        {chk.status === "unknown" ? (
                          <span className="company-sub">no clear status found</span>
                        ) : (
                          <span className={`badge badge-${chk.status}`}>
                            {chk.status.replace(/_/g, " ")}
                          </span>
                        )}
                        <span className="timeline-date">{formatDateIST(chk.checked_at)}</span>
                      </div>

                      <div className="evidence-row">
                        {chk.source_url && (
                          <a href={chk.source_url} target="_blank" rel="noreferrer" className="evidence-link">
                            View source →
                          </a>
                        )}
                        {chk.screenshot_url && (
                          <button
                            type="button"
                            className="evidence-link evidence-link-btn"
                            onClick={() => setExpandedShot(expandedShot === chk.id ? null : chk.id)}
                          >
                            {expandedShot === chk.id ? "Hide screenshot ▲" : "View screenshot ▼"}
                          </button>
                        )}
                      </div>

                      {expandedShot === chk.id && chk.screenshot_url && (
                        <img
                          className="screenshot-preview"
                          src={api.screenshotUrl(chk.screenshot_url)}
                          alt="Status check evidence"
                        />
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
