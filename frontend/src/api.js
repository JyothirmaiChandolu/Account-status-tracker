const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  getCompanies: () => request("/api/companies"),
  getCompany: (id) => request(`/api/companies/${id}`),
  createCompany: (payload) =>
    request("/api/companies", { method: "POST", body: JSON.stringify(payload) }),
  refreshCompany: (id) => request(`/api/companies/${id}/refresh`, { method: "POST" }),
  refreshAllCompanies: () => request("/api/companies/refresh-all", { method: "POST" }),
  deleteCompany: (id) => request(`/api/companies/${id}`, { method: "DELETE" }),
  deleteGroup: (groupName) => request(`/api/groups/${encodeURIComponent(groupName)}`, { method: "DELETE" }),
  getManualReview: () => request("/api/manual-review"),
  getGroupMembers: (groupName) => request(`/api/groups/${encodeURIComponent(groupName)}`),
  getStats: () => request("/api/stats"),
  getStates: () => request("/api/states"),
  screenshotUrl: (path) => (path ? `${BASE_URL}${path}` : null),
};
