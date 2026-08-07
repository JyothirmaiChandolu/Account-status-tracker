import { useEffect, useState, useCallback } from "react";
import { api } from "./api";
import Sidebar from "./components/Sidebar";
import StatCards from "./components/StatCards";
import CompanyTable from "./components/CompanyTable";
import AddCompanyModal from "./components/AddCompanyModal";
import CompanyDetailModal from "./components/CompanyDetailModal";
import GroupModal from "./components/GroupModal";

function App() {
  const [view, setView] = useState("dashboard");
  const [companies, setCompanies] = useState([]);
  const [reviewCompanies, setReviewCompanies] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedCompanyId, setSelectedCompanyId] = useState(null);
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [refreshingId, setRefreshingId] = useState(null);
  const [refreshingAll, setRefreshingAll] = useState(false);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [companyList, review, statData] = await Promise.all([
        api.getCompanies(),
        api.getManualReview(),
        api.getStats(),
      ]);
      setCompanies(companyList);
      setReviewCompanies(review);
      setStats(statData);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  async function handleRefreshCompany(id) {
    setRefreshingId(id);
    try {
      await api.refreshCompany(id);
      await loadAll();
    } catch (e) {
      setError(e.message);
    } finally {
      setRefreshingId(null);
    }
  }

  async function handleRefreshAll() {
    setRefreshingAll(true);
    try {
      await api.refreshAllCompanies();
      await loadAll();
    } catch (e) {
      setError(e.message);
    } finally {
      setRefreshingAll(false);
    }
  }

  async function handleDeleteCompany(id, name) {
    if (!window.confirm(`Remove "${name}" and all its check history? This can't be undone.`)) {
      return;
    }
    try {
      await api.deleteCompany(id);
      if (selectedCompanyId === id) setSelectedCompanyId(null);
      await loadAll();
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleDeleteGroup(groupName, count) {
    if (!window.confirm(`Remove all ${count} entities under "${groupName}" and their check history? This can't be undone.`)) {
      return;
    }
    try {
      await api.deleteGroup(groupName);
      setSelectedGroup(null);
      await loadAll();
    } catch (e) {
      setError(e.message);
    }
  }

  const listForView = view === "manual-review" ? reviewCompanies : companies;

  return (
    <div className="app-shell">
      <Sidebar
        view={view}
        setView={setView}
        reviewCount={reviewCompanies.length}
        onReload={loadAll}
        loading={loading}
        onRefreshAll={handleRefreshAll}
        refreshingAll={refreshingAll}
        onAddCompany={() => setShowAddModal(true)}
        hasCompanies={companies.length > 0}
      />

      <div className="main-area">
        <div className="top-bar">
          <h1>Franchise Tax Account Status Monitoring Dashboard</h1>
        </div>

        {error && <div className="panel error-text">{error}</div>}

        {stats && <StatCards stats={stats} />}

        <div className="panel panel-flex">
          <div className="panel-header">
            <h2>{view === "manual-review" ? "Manual Review Queue" : "Companies"}</h2>
          </div>
          <div className="panel-scroll">
            <CompanyTable
              companies={listForView}
              loading={loading}
              onRowClick={(id) => setSelectedCompanyId(id)}
              onGroupClick={(groupName) => setSelectedGroup(groupName)}
              onRefresh={handleRefreshCompany}
              onDelete={handleDeleteCompany}
              refreshingId={refreshingId}
              emptyMessage={
                view === "manual-review"
                  ? "Nothing needs manual review right now."
                  : "No companies yet. Click \"Add Company\" to start tracking one."
              }
            />
          </div>
        </div>
      </div>

      {showAddModal && (
        <AddCompanyModal
          onClose={() => setShowAddModal(false)}
          onCreated={() => {
            setShowAddModal(false);
            loadAll();
          }}
        />
      )}

      {selectedCompanyId && (
        <CompanyDetailModal
          companyId={selectedCompanyId}
          onClose={() => setSelectedCompanyId(null)}
          onRefresh={handleRefreshCompany}
          onDelete={handleDeleteCompany}
          refreshingId={refreshingId}
        />
      )}

      {selectedGroup && (
        <GroupModal
          groupName={selectedGroup}
          onClose={() => setSelectedGroup(null)}
          onOpenCompany={(id) => {
            setSelectedGroup(null);
            setSelectedCompanyId(id);
          }}
          onRefresh={handleRefreshCompany}
          onDelete={handleDeleteCompany}
          onDeleteGroup={handleDeleteGroup}
          refreshingId={refreshingId}
        />
      )}
    </div>
  );
}

export default App;
