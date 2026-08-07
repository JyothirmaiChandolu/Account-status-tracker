import { useEffect, useState } from "react";
import { api } from "../api";

export default function AddCompanyModal({ onClose, onCreated }) {
  const [states, setStates] = useState([]);
  const [name, setName] = useState("");
  const [state, setState] = useState("");
  const [entityNumber, setEntityNumber] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .getStates()
      .then((rows) => {
        setStates(rows);
        if (rows.length > 0) setState(rows[0].state);
      })
      .catch((e) => setError(e.message));
  }, []);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!name.trim() || !state) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createCompany({
        name: name.trim(),
        state,
        entity_number: entityNumber.trim() || null,
      });
      onCreated();
    } catch (e) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Add Company</h2>
          <button className="btn btn-ghost" onClick={onClose}>
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="field">
            <label>Company Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. MHK Tech Inc"
              required
            />
          </div>

          <div className="field">
            <label>Tax Authority State</label>
            <select value={state} onChange={(e) => setState(e.target.value)} required>
              {states.map((s) => (
                <option key={s.state} value={s.state}>
                  {s.state} — {s.authority_name}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>Entity / Taxpayer Number (optional)</label>
            <input
              type="text"
              value={entityNumber}
              onChange={(e) => setEntityNumber(e.target.value)}
              placeholder="Optional — helps disambiguate common names"
            />
          </div>

          {error && <div className="error-text">{error}</div>}
          {submitting && (
            <div className="company-sub">
              Checking status now — first-time states can take up to a minute...
            </div>
          )}

          <div className="modal-actions">
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? <span className="spinner dark" /> : null} Add & Check Status
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
