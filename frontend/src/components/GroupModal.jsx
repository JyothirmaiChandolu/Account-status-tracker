import { useEffect, useState } from "react";
import { api } from "../api";
import { formatDateIST } from "../format";

function StatusCell({ status }) {
  if (!status || status === "unknown") {
    return <span className="company-sub">—</span>;
  }
  return <span className={`badge badge-${status}`}>{status.replace(/_/g, " ")}</span>;
}

export default function GroupModal({ groupName, onClose, onOpenCompany, onRefresh, onDelete, onDeleteGroup, refreshingId }) {
  const [members, setMembers] = useState([]);
  const [error, setError] = useState(null);

  async function load() {
    try {
      setMembers(await api.getGroupMembers(groupName));
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupName]);

  useEffect(() => {
    if (refreshingId === null) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshingId]);

  async function handleDelete(id, name) {
    await onDelete(id, name);
    load();
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{groupName} — {members.length} entities</h2>
          <button className="btn btn-ghost" onClick={onClose}>✕</button>
        </div>

        <div style={{ marginBottom: 16 }}>
          <button
            className="btn btn-danger"
            onClick={() => onDeleteGroup(groupName, members.length)}
          >
            Remove All {members.length}
          </button>
        </div>

        {error && <div className="error-text">{error}</div>}

        <table>
          <thead>
            <tr>
              <th>Entity</th>
              <th>State</th>
              <th>Status</th>
              <th>Last Checked</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} className="clickable" onClick={() => onOpenCompany(m.id)}>
                <td className="company-name">{m.name}</td>
                <td>{m.state}</td>
                <td><StatusCell status={m.latest_status} /></td>
                <td className="company-sub">{formatDateIST(m.latest_checked_at)}</td>
                <td>
                  <div className="row-actions">
                    <button
                      className="btn btn-secondary"
                      onClick={(e) => {
                        e.stopPropagation();
                        onRefresh(m.id);
                      }}
                      disabled={refreshingId === m.id}
                    >
                      {refreshingId === m.id ? <span className="spinner dark" /> : "⟳"} Refresh
                    </button>
                    <button
                      className="btn btn-danger"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(m.id, m.name);
                      }}
                    >
                      Remove
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
