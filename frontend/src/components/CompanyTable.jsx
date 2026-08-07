import { formatDateIST } from "../format";

function StatusCell({ status }) {
  if (!status || status === "unknown") {
    return <span className="company-sub">—</span>;
  }
  const label = status.replace(/_/g, " ");
  return <span className={`badge badge-${status}`}>{label}</span>;
}

function CompanyRow({ c, onRowClick, onRefresh, onDelete, refreshingId }) {
  return (
    <tr className="clickable" onClick={() => onRowClick(c.id)}>
      <td>
        <div className="company-name">{c.name}</div>
        {c.entity_number && <div className="company-sub">#{c.entity_number}</div>}
      </td>
      <td>{c.state}</td>
      <td>
        <StatusCell status={c.latest_status} />
      </td>
      <td className="company-sub">{formatDateIST(c.latest_checked_at)}</td>
      <td>
        <div className="row-actions">
          <button
            className="btn btn-secondary"
            onClick={(e) => {
              e.stopPropagation();
              onRefresh(c.id);
            }}
            disabled={refreshingId === c.id}
          >
            {refreshingId === c.id ? <span className="spinner dark" /> : "⟳"} Refresh
          </button>
          <button
            className="btn btn-danger"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(c.id, c.name);
            }}
          >
            Remove
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function CompanyTable({
  companies,
  loading,
  onRowClick,
  onGroupClick,
  onRefresh,
  onDelete,
  refreshingId,
  emptyMessage,
}) {
  if (!loading && companies.length === 0) {
    return <div className="empty-state">{emptyMessage}</div>;
  }

  const ungrouped = [];
  const groups = new Map();
  for (const c of companies) {
    if (c.parent_group) {
      if (!groups.has(c.parent_group)) groups.set(c.parent_group, []);
      groups.get(c.parent_group).push(c);
    } else {
      ungrouped.push(c);
    }
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Company</th>
          <th>State</th>
          <th>Status</th>
          <th>Last Checked</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {ungrouped.map((c) => (
          <CompanyRow
            key={c.id}
            c={c}
            onRowClick={onRowClick}
            onRefresh={onRefresh}
            onDelete={onDelete}
            refreshingId={refreshingId}
          />
        ))}

        {[...groups.entries()].map(([groupName, members]) => (
          <tr
            className="clickable group-header-row"
            key={`group-${groupName}`}
            onClick={() => onGroupClick(groupName, members)}
          >
            <td colSpan={5}>
              {groupName} <span className="company-sub">— {members.length} entities found — click to view all</span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
