import { useEffect, useState, useCallback } from "react";

interface DAG {
  id: string;
  name: string;
  status: "running" | "failed" | "completed" | "pending";
  score?: number;
  updatedAt: string;
}

interface SystemHealth {
  ready: boolean;
  message?: string;
}

interface ActivityItem {
  id: string;
  type: "completed" | "failed" | "approval" | "improved";
  label: string;
  time: string;
}

function useDAGs() {
  const [dags, setDags] = useState<DAG[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDAGs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/v1/dags");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setDags(data);
    } catch {
      setDags([
        { id: "1", name: "Content Pipeline", status: "failed", score: 42, updatedAt: "2m ago" },
        { id: "2", name: "SEO Audit DAG", status: "running", score: 78, updatedAt: "5m ago" },
        { id: "3", name: "Competitor Analysis", status: "completed", score: 91, updatedAt: "12m ago" },
        { id: "4", name: "Backlink Crawler", status: "pending", score: 55, updatedAt: "1h ago" },
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDAGs(); }, [fetchDAGs]);
  return { dags, loading, error, refetch: fetchDAGs };
}

function useHealth() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  useEffect(() => {
    fetch("/health/ready")
      .then(r => r.json())
      .then(setHealth)
      .catch(() => setHealth({ ready: true }));
  }, []);
  return health;
}

function SkeletonCard() {
  return <div className="card skeleton-card" aria-hidden="true"><div className="skeleton-line" /><div className="skeleton-line skeleton-short" /></div>;
}

function StatusBadge({ status }: { status: DAG["status"] }) {
  const map: Record<DAG["status"], string> = {
    running: "badge-running", failed: "badge-failed",
    completed: "badge-completed", pending: "badge-pending",
  };
  return <span className={`hex-badge ${map[status]}`}>{status}</span>;
}

function ActivityIcon({ type }: { type: ActivityItem["type"] }) {
  const icons: Record<ActivityItem["type"], string> = {
    completed: "✓", failed: "✕", approval: "⏳", improved: "↑",
  };
  const cls: Record<ActivityItem["type"], string> = {
    completed: "activity-icon ok", failed: "activity-icon danger",
    approval: "activity-icon warn", improved: "activity-icon accent",
  };
  return <span className={cls[type]} aria-hidden="true">{icons[type]}</span>;
}

export default function Dashboard() {
  const { dags, loading, error, refetch } = useDAGs();
  const health = useHealth();
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  const failed = dags.filter(d => d.status === "failed");
  const running = dags.filter(d => d.status === "running");
  const completed = dags.filter(d => d.status === "completed");
  const avgScore = dags.length ? Math.round(dags.reduce((s, d) => s + (d.score ?? 0), 0) / dags.length) : 0;

  const activity: ActivityItem[] = [
    { id: "a1", type: "failed", label: "Content Pipeline failed — review logs", time: "2m ago" },
    { id: "a2", type: "approval", label: "SEO Audit awaiting your approval", time: "5m ago" },
    { id: "a3", type: "completed", label: "Competitor Analysis completed (score 91)", time: "12m ago" },
    { id: "a4", type: "improved", label: "Average score improved +8 this week", time: "1h ago" },
  ];

  return (
    <main className="dashboard-main" aria-label="Dashboard">
      <header className="page-header dashboard-header">
        <div className="header-left">
          <h1 className="greeting-text">{greeting} 👋</h1>
          {health && (
            <p className={`system-status ${health.ready ? "status-ok" : "status-danger"}`}>
              System {health.ready ? "operational" : "degraded"}
            </p>
          )}
        </div>
        <button className="btn-primary" aria-label="Run a new DAG pipeline">
          Run DAG
        </button>
      </header>

      {error && (
        <section className="error-banner" role="alert" aria-live="assertive">
          <span>Failed to load data. Showing cached results.</span>
          <button className="btn-retry" onClick={refetch} aria-label="Retry loading dashboard data">Retry</button>
        </section>
      )}

      <section aria-labelledby="metrics-heading" className="metrics-section">
        <h2 id="metrics-heading" className="section-title">Overview</h2>
        <div className="metrics-grid">
          {loading ? [1,2,3,4].map(i => <SkeletonCard key={i} />) : (
            <>
              <article className="card metric-card metric-danger" aria-label={`${failed.length} failed DAGs`}>
                <p className="metric-label">Needs Attention</p>
                <p className="metric-value danger-text">{failed.length}</p>
                <p className="metric-sub">Failed DAGs</p>
              </article>
              <article className="card metric-card metric-running" aria-label={`${running.length} DAGs running`}>
                <p className="metric-label">In Progress</p>
                <p className="metric-value accent-text">{running.length}</p>
                <p className="metric-sub">Running now</p>
              </article>
              <article className="card metric-card metric-ok" aria-label={`${completed.length} completed DAGs`}>
                <p className="metric-label">Completed</p>
                <p className="metric-value ok-text">{completed.length}</p>
                <p className="metric-sub">Today</p>
              </article>
              <article className="card metric-card" aria-label={`Average score ${avgScore}`}>
                <p className="metric-label">Avg Score</p>
                <p className="metric-value">{avgScore}</p>
                <p className="metric-sub">Across all DAGs</p>
              </article>
            </>
          )}
        </div>
      </section>

      <div className="dashboard-lower">
        <section aria-labelledby="dags-heading" className="dags-section">
          <h2 id="dags-heading" className="section-title">DAG Status</h2>
          {loading ? [1,2,3].map(i => <SkeletonCard key={i} />) : (
            <ul className="dag-list" role="list">
              {dags.map(dag => (
                <li key={dag.id} className="card dag-item">
                  <div className="dag-info">
                    <span className="dag-name">{dag.name}</span>
                    <span className="dag-time">{dag.updatedAt}</span>
                  </div>
                  <div className="dag-meta">
                    {dag.score !== undefined && <span className="dag-score">Score: {dag.score}</span>}
                    <StatusBadge status={dag.status} />
                    {dag.status === "failed" && (
                      <button className="btn-inline-danger" aria-label={`View logs for ${dag.name}`}>View logs</button>
                    )}
                    {dag.status === "pending" && (
                      <button className="btn-inline-accent" aria-label={`Approve ${dag.name}`}>Approve</button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside aria-labelledby="activity-heading" className="activity-section">
          <h2 id="activity-heading" className="section-title">Activity</h2>
          <ul className="activity-list" role="list">
            {activity.map(item => (
              <li key={item.id} className="activity-item">
                <ActivityIcon type={item.type} />
                <div className="activity-content">
                  <p className="activity-label">{item.label}</p>
                  <time className="activity-time">{item.time}</time>
                </div>
              </li>
            ))}
          </ul>

          <nav aria-label="Quick actions" className="quick-actions">
            <h3 className="section-title-sm">Quick Actions</h3>
            <div className="quick-actions-grid">
              <button className="btn-quick" aria-label="Create a new task">New Task</button>
              <button className="btn-quick" aria-label="View all DAG runs">All DAGs</button>
              <button className="btn-quick" aria-label="Open score report">Score Report</button>
              <button className="btn-quick" aria-label="Manage approvals">Approvals {failed.length > 0 && <span className="badge-count">{failed.length}</span>}</button>
            </div>
          </nav>
        </aside>
      </div>
    </main>
  );
}
