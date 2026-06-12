import { useState, useEffect, useCallback } from "react";

interface KPI { label: string; value: string; sub: string; icon: string; delta?: string; deltaUp?: boolean }
interface Widget { id: string; title: string; type: string; config: Record<string, unknown> }

export default function Overview() {
  const [kpis, setKpis] = useState<KPI[]>([]);
  const [greeting, setGreeting] = useState("");
  const [greetingLoading, setGreetingLoading] = useState(true);
  const [widgets, setWidgets] = useState<Widget[]>([]);
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [asking, setAsking] = useState(false);

  // Load KPIs from dashboard metrics
  useEffect(() => {
    fetch("/v1/dashboard/metrics", { credentials: "same-origin" })
      .then(r => r.json())
      .then(d => {
        setKpis([
          { label: "Active Agents", value: String(d.active_agents || 0), sub: "Connected", icon: "🤖" },
          { label: "Runs Today", value: String(d.runs_today || 0), sub: "This session", icon: "⚡" },
          { label: "Avg Latency", value: `${d.avg_latency_ms || 0}ms`, sub: "p50 response", icon: "⏱" },
          { label: "Total Cost", value: `$${(d.total_cost || 0).toFixed(2)}`, sub: "This period", icon: "💰" },
        ]);
      })
      .catch(() => {});
  }, []);

  // Load Airtable KPIs
  useEffect(() => {
    const fetchCount = async (filter: string, label: string, icon: string, sub: string) => {
      try {
        const r = await fetch(`/v1/widgets/airtable?table=tblvcVTyk2HoZ8SzA&max_records=500&filter_formula=${encodeURIComponent(filter)}`, { credentials: "same-origin" });
        const d = await r.json();
        return { label, value: String(d.total || d.count || 0), sub, icon };
      } catch { return { label, value: "—", sub, icon }; }
    };
    Promise.all([
      fetchCount('NOT(OR({Status}="Cancelled",{Status}="Sunset",{Status}="Paused"))', "Total Use Cases", "✦", "Active portfolio"),
      fetchCount('OR({Status}="Development",{Status}="Discovery/Testing",{Status}="OTE Review",{Status}="Commercialization Request")', "In-Flight", "🚀", "Actively progressing"),
      fetchCount('OR({V2 Migration Status}="Onboarding In-Progress",{V2 Migration Status}="Testing")', "Active Migration", "🔄", "Onboarding + testing"),
      fetchCount('{Status}="Commercialized"', "Commercialized", "🏆", "Shipped to production"),
    ]).then(results => setKpis(results));
  }, []);

  // LLM greeting (cached, max once/hour)
  useEffect(() => {
    const cacheKey = "fantasia_greeting";
    const cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      const { text, ts } = JSON.parse(cached);
      if (Date.now() - ts < 3600000) { setGreeting(text); setGreetingLoading(false); return; }
    }
    fetch("/v1/chat/stream", {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: [{ role: "user", content: "Give me a 2-3 sentence morning briefing about the current state of our use case portfolio. Be concise and encouraging. Mention key numbers if you have them. Do NOT use tools." }] }),
    }).then(async r => {
      if (!r.ok || !r.body) { setGreetingLoading(false); return; }
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = "", text = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
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

  // Mini chat for data interrogation
  const ask = useCallback(async () => {
    if (!query.trim() || asking) return;
    setAsking(true); setAnswer("");
    try {
      const r = await fetch("/v1/chat/stream", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: query }] }),
      });
      if (!r.ok || !r.body) { setAnswer("Error"); setAsking(false); return; }
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = "", text = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const frames = buf.split("\n\n"); buf = frames.pop() ?? "";
        for (const f of frames) {
          if (!f.trim().startsWith("data:")) continue;
          try {
            const e = JSON.parse(f.trim().slice(5).trim());
            if (e.type === "done") text = e.content || text;
            else if (e.type === "delta") { text += e.content || ""; setAnswer(text); }
          } catch {}
        }
      }
      setAnswer(text);
    } catch { setAnswer("Connection error"); }
    setAsking(false);
  }, [query, asking]);

  return (
    <div style={{ padding: "2rem 2.5rem", maxWidth: 1200, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--ink)", margin: 0 }}>Live Operations</h1>
        <p style={{ fontSize: "0.8rem", color: "var(--pencil)", margin: "4px 0 0" }}>Real-time visibility into your orchestration</p>
      </div>

      {/* KPI Row */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", marginBottom: "1.5rem" }}>
        {kpis.map(k => (
          <div key={k.label} style={{ background: "var(--panel-bg, #fff)", border: "1px solid var(--rule)", borderRadius: 14, padding: "1.2rem", boxShadow: "var(--shadow-sm, 0 2px 8px rgba(42,31,92,0.05))" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={{ fontSize: "1.2rem" }}>{k.icon}</span>
              <span style={{ fontSize: "0.7rem", color: "var(--pencil)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{k.label}</span>
            </div>
            <div style={{ fontSize: "1.8rem", fontWeight: 800, color: "var(--ink)", fontVariantNumeric: "tabular-nums" }}>{k.value}</div>
            <div style={{ fontSize: "0.7rem", color: "var(--muted)", marginTop: 4 }}>{k.sub}</div>
          </div>
        ))}
      </div>

      {/* LLM Greeting */}
      <div style={{ background: "var(--panel-alt, #F1EEFF)", border: "1px solid var(--rule)", borderRadius: 14, padding: "1rem 1.5rem", marginBottom: "1.5rem", display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: "1.5rem" }}>🎵</span>
        <div>
          {greetingLoading ? (
            <span style={{ fontSize: "0.85rem", color: "var(--muted)", fontStyle: "italic" }}>Composing your briefing...</span>
          ) : (
            <p style={{ fontSize: "0.85rem", color: "var(--ink)", margin: 0, lineHeight: 1.6 }}>{greeting || "Your orchestra is in harmony. All systems operational."}</p>
          )}
        </div>
      </div>

      {/* Mini Chat */}
      <div style={{ background: "var(--panel-bg, #fff)", border: "1px solid var(--rule)", borderRadius: 14, padding: "1rem 1.5rem", marginBottom: "1.5rem", boxShadow: "var(--shadow-sm)" }}>
        <div style={{ fontSize: "0.7rem", color: "var(--pencil)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 8 }}>Ask about your data</div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={query} onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && ask()}
            placeholder="How many use cases are in development? What's our migration progress?"
            style={{ flex: 1, padding: "8px 12px", borderRadius: 10, border: "1px solid var(--rule)", fontSize: "0.8rem", color: "var(--ink)", background: "var(--paper)", outline: "none" }}
          />
          <button onClick={ask} disabled={asking} style={{ padding: "8px 16px", borderRadius: 10, border: "none", background: "var(--accent)", color: "#fff", fontSize: "0.75rem", fontWeight: 600, cursor: "pointer", opacity: asking ? 0.5 : 1 }}>
            {asking ? "..." : "Ask"}
          </button>
        </div>
        {answer && (
          <div style={{ marginTop: 10, fontSize: "0.8rem", color: "var(--ink)", lineHeight: 1.6, padding: "8px 12px", background: "var(--panel-alt, #F1EEFF)", borderRadius: 8 }}>
            {answer}
          </div>
        )}
      </div>
    </div>
  );
}
