import { useState, useEffect, useCallback } from "react";
import "../overview.css";

interface KPI { label: string; value: string; sub: string; icon: string; delta?: string }

export default function Overview() {
  const [kpis, setKpis] = useState<KPI[]>([]);
  const [greeting, setGreeting] = useState("");
  const [greetingLoading, setGreetingLoading] = useState(true);
  const [widgets, setWidgets] = useState<any[]>([]);
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    const f = async (filter: string, label: string, icon: string, sub: string) => {
      try {
        const r = await fetch(`/v1/widgets/airtable?table=tblvcVTyk2HoZ8SzA&max_records=500&group_by=Status&filter_formula=${encodeURIComponent(filter)}`, { credentials: "same-origin" });
        const d = await r.json();
        return { label, value: String(d.total || 0), sub, icon };
      } catch { return { label, value: "—", sub, icon }; }
    };
    Promise.all([
      f('NOT(OR({Status}="Cancelled",{Status}="Sunset",{Status}="Paused"))', "Total Use Cases", "✦", "Across 6 locations"),
      f('OR({Status}="Development",{Status}="Discovery/Testing",{Status}="OTE Review",{Status}="Commercialization Request")', "Active (In-Flight)", "🚀", "37% of total"),
      f('OR({V2 Migration Status}="Onboarding In-Progress",{V2 Migration Status}="Testing")', "Automations & Agents", "⚡", "Connected"),
      f('{Status}="Commercialized"', "Commercialized", "🏆", "Shipped to production"),
    ]).then(setKpis);
  }, []);

  useEffect(() => {
    const cacheKey = "app_greeting";
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      const { text, ts } = JSON.parse(cached);
      if (Date.now() - ts < 3600000) { setGreeting(text); setGreetingLoading(false); return; }
    }
    fetch("/v1/chat/stream", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: [{ role: "user", content: "Give me a 2-3 sentence briefing about the current state of our use case portfolio. Be encouraging and specific. Do NOT use tools." }] }),
    }).then(async r => {
      if (!r.ok || !r.body) { setGreetingLoading(false); return; }
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "", text = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n"); buf = frames.pop() ?? "";
        for (const f of frames) {
          if (!f.trim().startsWith("data:")) continue;
          try { const e = JSON.parse(f.trim().slice(5).trim()); if (e.type === "done") text = e.content || text; else if (e.type === "delta") text += e.content || ""; } catch {}
        }
      }
      setGreeting(text); setGreetingLoading(false);
      sessionStorage.setItem(cacheKey, JSON.stringify({ text, ts: Date.now() }));
    }).catch(() => setGreetingLoading(false));
  }, []);

  useEffect(() => {
    fetch("/v1/chat/overview-widgets", { credentials: "same-origin" })
      .then(r => r.json()).then(d => setWidgets(d.widgets || [])).catch(() => {});
  }, []);

  const ask = useCallback(async () => {
    if (!query.trim() || asking) return;
    setAsking(true); setAnswer("");
    try {
      const r = await fetch("/v1/chat/stream", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ messages: [{ role: "user", content: query }] }) });
      if (!r.ok || !r.body) { setAnswer("Error"); setAsking(false); return; }
      const reader = r.body.getReader();
      const dec = new TextDecoder();
      let buf = "", text = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n"); buf = frames.pop() ?? "";
        for (const f of frames) {
          if (!f.trim().startsWith("data:")) continue;
          try { const e = JSON.parse(f.trim().slice(5).trim()); if (e.type === "done") text = e.content || text; else if (e.type === "delta") { text += e.content || ""; setAnswer(text); } } catch {}
        }
      }
      setAnswer(text);
    } catch { setAnswer("Connection error"); }
    setAsking(false);
  }, [query, asking]);

  return (
    <div className="overview-page">
      {/* Toolbar */}
      <div className="overview-toolbar">
        <div className="overview-toolbar-left">
          <h1>Live Operations</h1>
          <p>Real-time visibility into your orchestration</p>
        </div>
        <div className="overview-toolbar-actions">
          <span className="overview-status-badge">Operational</span>
          <button className="overview-action-btn">↻ Refresh</button>
          <button className="overview-action-btn">↶ Undo</button>
          <button className="overview-action-btn">↷ Redo</button>
          <button className="overview-action-btn overview-action-btn--primary">✦ Templates</button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="overview-kpi-row">
        {kpis.map(k => (
          <div key={k.label} className="overview-kpi-card">
            <div className="overview-kpi-icon">{k.icon}</div>
            <div className="overview-kpi-label">{k.label}</div>
            <div className="overview-kpi-value">{k.value}</div>
            <div className="overview-kpi-sub">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Greeting */}
      <div className="overview-greeting">
        <span className="overview-greeting-icon">🎵</span>
        <div>
          {greetingLoading
            ? <span className="overview-greeting-loading">Composing your briefing...</span>
            : <p className="overview-greeting-text">{greeting || "Your orchestra is in perfect harmony. All use cases performing well."}</p>
          }
        </div>
      </div>

      {/* Widget Grid */}
      {widgets.length > 0 && (
        <div className="overview-widgets">
          {widgets.map(w => <OverviewWidget key={w.id} widget={w} />)}
        </div>
      )}

      {/* Mini Chat */}
      <div className="overview-chat">
        <div className="overview-chat-title">Ask about your data</div>
        <div className="overview-chat-row">
          <input className="overview-chat-input" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === "Enter" && ask()} placeholder="How many use cases are in development?" />
          <button className="overview-chat-btn" onClick={ask} disabled={asking}>{asking ? "..." : "Ask"}</button>
        </div>
        {answer && <div className="overview-chat-answer">{answer}</div>}
      </div>
    </div>
  );
}

const BAR_COLORS = ["", "--gold", "--orange", "--red", "--green"];

function OverviewWidget({ widget }: { widget: any }) {
  const [data, setData] = useState<any>(null);
  const cfg = widget.config || {};

  useEffect(() => {
    if (cfg.source !== "airtable") return;
    const p = new URLSearchParams({ table: cfg.table || "", max_records: cfg.max_records || "500" });
    if (cfg.group_by) p.set("group_by", cfg.group_by);
    if (cfg.filter_formula) p.set("filter_formula", cfg.filter_formula);
    if (cfg.display_field) p.set("display_field", cfg.display_field);
    fetch(`/v1/widgets/airtable?${p}`, { credentials: "same-origin" }).then(r => r.json()).then(setData).catch(() => {});
  }, []);

  const display = cfg.display || "bar";

  return (
    <div className="overview-widget-card">
      <div className="overview-widget-header">
        <div className="overview-widget-title">
          <span className="overview-widget-title-icon">{cfg.icon || "📊"}</span>
          {widget.title}
        </div>
        <span className="overview-widget-menu">···</span>
      </div>

      {!data ? <div className="overview-widget-loading">Loading...</div> :
        display === "count" ? (
          <div className="overview-widget-count">{data.total ?? data.count ?? 0}</div>
        ) : display === "table" && data.records ? (
          <table className="overview-widget-table">
            <thead><tr>
              {(cfg.columns || ["name", "category", "status"]).map((c: string) => <th key={c}>{c}</th>)}
            </tr></thead>
            <tbody>
              {data.records.slice(0, 6).map((r: any, i: number) => (
                <tr key={i}>
                  {(cfg.columns || ["name", "category", "status"]).map((c: string) => (
                    <td key={c}>{c === "status" ? <span className={`overview-widget-table-status overview-widget-table-status--${(r[c] || "").toLowerCase().includes("active") ? "active" : "paused"}`}>● {r[c]}</span> : r[c] || "—"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : data.breakdown ? (
          <div>
            {Object.entries(data.breakdown).slice(0, 7).map(([k, v]: [string, any], i) => (
              <div key={k} className="overview-widget-bar">
                <span className="overview-widget-bar-label">{k}</span>
                <div className="overview-widget-bar-track">
                  <div className={`overview-widget-bar-fill${BAR_COLORS[i % BAR_COLORS.length] ? ` overview-widget-bar-fill${BAR_COLORS[i % BAR_COLORS.length]}` : ""}`} style={{ width: `${Math.min((v / (data.total || 1)) * 100, 100)}%` }} />
                </div>
                <span className="overview-widget-bar-value">{v}</span>
              </div>
            ))}
          </div>
        ) : display === "list" && data.records ? (
          <div>
            {data.records.slice(0, 5).map((r: any, i: number) => (
              <div key={i} className="overview-widget-bar">
                <span className="overview-widget-bar-label">{r.name}</span>
                <span className="overview-widget-bar-value">{r.status || ""}</span>
              </div>
            ))}
          </div>
        ) : <div className="overview-widget-loading">No data</div>
      }
    </div>
  );
}
