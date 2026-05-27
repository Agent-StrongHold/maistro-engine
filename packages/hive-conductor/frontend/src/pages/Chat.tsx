import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiPost, apiDelete } from "../lib/api";
import { PageHeader, Hex, SearchInput, ConfirmDialog } from "../components/shared";

type Session = { id: string; title: string; message_count: number; updated_at: string };
type ChatMsg = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  agent?: string;
  model?: string;
  intent?: string;
  tool_calls?: { name: string; args: string; result: string; done: boolean }[];
  verdict?: string;
  clarify_options?: string[];
  gate?: { blocked: boolean; strikes: number; max_strikes: number; pattern: string; escalation: string };
};
type FullSession = { id: string; title: string; messages: ChatMsg[]; created_at: string; updated_at: string };

const SUGGESTIONS = [
  "What's on my plate in Jira?",
  "Who's blocked right now?",
  "Summarize the sprint status",
  "Search Confluence for onboarding docs",
];

const DEFAULT_MODELS = [
  "cerebras-qwen-3-235b-a22b-2507",
  "mistral-large",
  "gpt-4o",
  "claude-sonnet-4-20250514",
  "gemini-2.5-pro",
];

const DOTS_ID = "hc-chat-dots";
function ensureDotsAnim() {
  if (document.getElementById(DOTS_ID)) return;
  const s = document.createElement("style");
  s.id = DOTS_ID;
  s.textContent = "@keyframes hc-dots{0%,20%{opacity:.2}40%{opacity:1}100%{opacity:.2}}";
  document.head.appendChild(s);
}

const STATUS_STEPS = ["Working…"];

function StreamingStatus({ status }: { status: string }) {
  return (
    <div style={{ alignSelf: "flex-start", padding: "8px 12px", background: "var(--paper)", border: "1.4px solid var(--accent)", borderRadius: 8, fontFamily: "var(--mono)", fontSize: 10, color: "var(--accent)", display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)", animation: "hc-dots 1s ease-in-out infinite" }} />
      {status}
    </div>
  );
}

function fmtTime(ts: string) {
  const d = new Date(ts);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function Chat() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamStatus, setStreamStatus] = useState("Working…");
  const [models, setModels] = useState<string[]>(DEFAULT_MODELS);
  const [selectedModel, setSelectedModel] = useState("gemini-3.5-flash");
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedTools, setExpandedTools] = useState<Set<string>>(new Set());
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null);
  const [clarifyChoice, setClarifyChoice] = useState<string | null>(null);
  const [modelOpen, setModelOpen] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const loadSessions = useCallback(async () => {
    try { setSessions(await apiGet<Session[]>("/v1/chat/sessions")); } catch { /* */ }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const data = await apiGet<{ models?: string[] } | string[]>("/v1/settings/models");
      const list = Array.isArray(data) ? data : (data as { models?: string[] }).models;
      if (list && list.length > 0) {
        setModels(list);
        if (!list.includes(selectedModel)) setSelectedModel(list[0]);
      }
    } catch { /* */ }
  }, [selectedModel]);

  useEffect(() => { void loadSessions(); void loadModels(); ensureDotsAnim(); }, [loadSessions, loadModels]);

  // Auto-send from ?q= query param (agent button clicks)
  const pendingQuery = useRef<string | null>(null);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    if (q) {
      window.history.replaceState({}, "", window.location.pathname);
      (async () => {
        try {
          const s = await apiPost<Session>("/v1/chat/sessions", { title: q.slice(0, 40) });
          setSessions((p) => [s, ...p]);
          setActiveSessionId(s.id);
          setMessages([]);
          pendingQuery.current = q;
        } catch {
          pendingQuery.current = q;
        }
      })();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fire pending query after session is selected
  useEffect(() => {
    if (pendingQuery.current && activeSessionId) {
      const q = pendingQuery.current;
      pendingQuery.current = null;
      void send(q);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSessionId]);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, streaming]);

  async function createSession() {
    try {
      const s = await apiPost<Session>("/v1/chat/sessions", { title: "New chat" });
      setSessions((p) => [s, ...p]);
      setActiveSessionId(s.id);
      setMessages([]);
      setClarifyChoice(null);
    } catch { /* */ }
  }

  async function loadSession(id: string) {
    try {
      const fs = await apiGet<FullSession>(`/v1/chat/sessions/${id}`);
      setActiveSessionId(id);
      setMessages(fs.messages ?? []);
      setClarifyChoice(null);
    } catch { /* */ }
  }

  async function deleteSession(id: string) {
    try {
      await apiDelete(`/v1/chat/sessions/${id}`);
      setSessions((p) => p.filter((s) => s.id !== id));
      if (activeSessionId === id) { setActiveSessionId(null); setMessages([]); setStreaming(false); }
    } catch { /* */ }
    setDeleteTarget(null);
  }

  async function send(msg?: string) {
    const text = (msg ?? input).trim();
    if (!text || streaming) return;
    setInput("");
    if (taRef.current) taRef.current.style.height = "auto";
    // Auto-create session if none active
    let sid = activeSessionId;
    if (!sid) {
      try {
        const s = await apiPost<Session>("/v1/chat/sessions", { title: text.slice(0, 40) });
        setSessions((p) => [s, ...p]);
        setActiveSessionId(s.id);
        sid = s.id;
      } catch { /* continue without session */ }
    }
    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: "user", content: text, timestamp: new Date().toISOString() };
    const next = [...messages, userMsg];
    setMessages(next);
    setStreaming(true);
    setStreamStatus("Working…");
    setClarifyChoice(null);
    try {
      const history = next.map((m) => ({ role: m.role, content: m.content }));
      const resp = await fetch("/v1/chat/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ messages: history, model: selectedModel }),
      });
      if (!resp.ok) throw new Error(`/v1/chat/complete: ${resp.status}`);
      const data = await resp.json();
      const content = data?.choices?.[0]?.message?.content ?? "";
      const asst: ChatMsg = {
        id: crypto.randomUUID(), role: "assistant", content: content || "(no response)",
        timestamp: new Date().toISOString(),
        model: selectedModel,
      };
      setMessages((p) => [...p, asst]);
      // Persist messages to session
      if (sid) {
        apiPost(`/v1/chat/sessions/${sid}/messages`, { role: "user", content: text }).catch(() => {});
        apiPost(`/v1/chat/sessions/${sid}/messages`, { role: "assistant", content }).catch(() => {});
      }
      if (sessions.length === 0) void loadSessions();
    } catch (e) {
      setMessages((p) => [...p, {
        id: crypto.randomUUID(), role: "assistant" as const,
        content: `Error: ${e instanceof Error ? e.message : "request failed"}`,
        timestamp: new Date().toISOString(), agent: "System",
      }]);
    }
    setStreaming(false);
  }

  function toggleTool(key: string) {
    setExpandedTools((p) => { const n = new Set(p); if (n.has(key)) n.delete(key); else n.add(key); return n; });
  }

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const filtered = sessions.filter((s) => s.title.toLowerCase().includes(searchQuery.toLowerCase()));
  const showSidebar = sessions.length > 0;
  const isNarrow = typeof window !== "undefined" && window.innerWidth < 700;

  const sidebar = showSidebar && (
    <div style={{
      width: 240, borderRight: "1.3px solid var(--rule)", display: "flex", flexDirection: "column",
      flexShrink: 0, background: "var(--paper-2)",
      ...(isNarrow ? { position: "fixed", top: 0, left: 0, bottom: 0, zIndex: 200, boxShadow: "4px 0 16px rgba(0,0,0,0.15)" } : {}),
    }}>
      <div style={{ padding: "8px 10px", display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--rule)" }}>
        <span style={{ fontFamily: "var(--mono)", fontSize: 8, fontWeight: 700, letterSpacing: "0.06em", color: "var(--pencil)" }}>SESSIONS</span>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <button onClick={() => void createSession()} style={{ background: "none", border: "1px solid var(--accent)", color: "var(--accent)", fontFamily: "var(--mono)", fontSize: 9, padding: "1px 6px", borderRadius: 3, cursor: "pointer" }}>+ new</button>
          {isNarrow && (
            <button onClick={() => setSidebarOpen(false)} style={{ background: "none", border: "none", fontSize: 16, cursor: "pointer", color: "var(--pencil)", padding: "0 2px" }}>✕</button>
          )}
        </div>
      </div>
      <div style={{ padding: "6px 8px" }}>
        <SearchInput value={searchQuery} onChange={setSearchQuery} placeholder="filter..." />
      </div>
      <div style={{ flex: 1, overflow: "auto" }}>
        {filtered.map((s) => (
          <div key={s.id} onClick={() => { void loadSession(s.id); if (isNarrow) setSidebarOpen(false); }} style={{
            padding: "6px 10px", cursor: "pointer",
            borderLeft: activeSessionId === s.id ? "3px solid var(--accent)" : "3px solid transparent",
            background: activeSessionId === s.id ? "var(--honey-light)" : "transparent",
            display: "flex", alignItems: "center", gap: 4,
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: "var(--hand)", fontSize: 12, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 8, color: "var(--pencil)" }}>{s.message_count} msgs · {fmtTime(s.updated_at)}</div>
            </div>
            <button onClick={(e) => { e.stopPropagation(); setDeleteTarget(s); }} style={{ background: "none", border: "none", color: "var(--pencil)", cursor: "pointer", fontSize: 10, padding: "0 2px", lineHeight: 1 }}>✕</button>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div style={{ display: "flex", height: "calc(100vh - 60px)" }}>
      <ConfirmDialog
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => { if (deleteTarget) void deleteSession(deleteTarget.id); }}
        title="Delete Session"
        message={`Delete "${deleteTarget?.title ?? ""}" and all its messages?`}
      />

      {isNarrow && sidebarOpen && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.3)", zIndex: 199 }} onClick={() => setSidebarOpen(false)} />
      )}
      {(isNarrow ? sidebarOpen : showSidebar) && sidebar}

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <div style={{ flexShrink: 0, padding: "0 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
          {isNarrow && showSidebar && (
            <button onClick={() => setSidebarOpen(true)} style={{ background: "none", border: "1px solid var(--rule)", borderRadius: 4, padding: "4px 8px", cursor: "pointer", fontSize: 14, color: "var(--ink)", lineHeight: 1 }}>☰</button>
          )}
          <PageHeader
            title="Chat"
            subtitle="PM Fleet — manage your program, check Jira, track blockers"
            helpHref="/docs#chat"
            actions={!showSidebar ? <button className="btn btn-accent" onClick={() => void createSession()} style={{ fontSize: 9 }}>+ new session</button> : undefined}
          />
        </div>

        {!messages.length && !streaming ? (
          <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16, padding: 20 }}>
            <div style={{ fontFamily: "var(--hand)", fontSize: 32, textAlign: "center" }}>How can I help?</div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--pencil)", textAlign: "center" }}>Poll Jira, check blockers, search Confluence, or create agent buttons</div>
            <div className="grid-2" style={{ width: "100%", maxWidth: 380 }}>
              {SUGGESTIONS.map((s) => (
                <div key={s} className="card" style={{ cursor: "pointer", fontFamily: "var(--hand)", fontSize: 13 }} onClick={() => void send(s)}>{s}</div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ flex: 1, overflow: "auto", display: "flex", flexDirection: "column", gap: 10, padding: "4px 12px" }}>
            {messages.map((m, i) => {
              if (m.role === "user") {
                const struck = !!messages[i + 1]?.gate?.blocked;
                return (
                  <div key={m.id} style={{ alignSelf: "flex-end", maxWidth: "75%" }}>
                    <div style={{
                      padding: "8px 12px", background: "var(--ink)",
                      border: "1.4px solid var(--rule)", borderRadius: 8,
                      fontSize: 12, color: "var(--paper)", whiteSpace: "pre-wrap",
                      textDecoration: struck ? "line-through" : "none",
                      opacity: struck ? 0.55 : 1,
                    }}>{m.content}</div>
                  </div>
                );
              }
              return (
                <div key={m.id} style={{ alignSelf: "flex-start", maxWidth: "75%" }}>
                  {m.gate?.blocked && (
                    <div style={{ marginBottom: 4, padding: 8, border: "1.3px solid var(--danger)", borderRadius: 6, background: "rgba(196,69,42,0.08)" }}>
                      <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--danger)", fontWeight: 600 }}>GATE BLOCKED</div>
                      <div style={{ fontFamily: "var(--mono)", fontSize: 10, marginTop: 3, display: "flex", gap: 12 }}>
                        <span>Strikes: <strong>{m.gate.strikes}/{m.gate.max_strikes}</strong></span>
                        <span>Pattern: <strong>{m.gate.pattern}</strong></span>
                      </div>
                      <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginTop: 2 }}>Escalation: {m.gate.escalation}</div>
                    </div>
                  )}
                  <div style={{ display: "flex", gap: 4, marginBottom: 3, flexWrap: "wrap" }}>
                    {m.agent && <Hex variant="accent">{m.agent}</Hex>}
                    {m.model && <Hex variant="muted">{m.model}</Hex>}
                    {m.intent && <Hex variant="purple">{m.intent}</Hex>}
                  </div>
                  <div style={{
                    padding: "8px 12px", background: "var(--paper)",
                    border: "1.4px solid var(--ink)", borderRadius: 8,
                    fontSize: 12, color: "var(--ink)", whiteSpace: "pre-wrap",
                  }}>{m.content}</div>
                  {m.tool_calls?.map((tc, ti) => {
                    const key = `${m.id}-${ti}`;
                    const open = expandedTools.has(key);
                    return (
                      <div key={key} style={{ border: "1px solid var(--rule)", borderRadius: 4, marginTop: 4, fontFamily: "var(--mono)", fontSize: 10 }}>
                        <div onClick={() => toggleTool(key)} style={{
                          display: "flex", alignItems: "center", gap: 6,
                          padding: "4px 8px", cursor: "pointer", background: "var(--paper-2)",
                          borderRadius: open ? undefined : 4,
                        }}>
                          <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%", background: tc.done ? "var(--ok)" : "var(--warn)" }} />
                          <span style={{ fontWeight: 600 }}>{tc.name}</span>
                          <span style={{ color: "var(--pencil)", fontSize: 9 }}>{tc.done ? "done" : "running"}</span>
                          <span style={{ marginLeft: "auto", fontSize: 9 }}>{open ? "▾" : "▸"}</span>
                        </div>
                        {open && (
                          <div style={{ padding: "4px 8px", borderTop: "1px solid var(--rule)" }}>
                            <div style={{ marginBottom: 4 }}>
                              <span style={{ color: "var(--pencil)", fontSize: 8 }}>ARGS</span>
                              <pre style={{ margin: 0, fontSize: 9, whiteSpace: "pre-wrap", maxHeight: 80, overflow: "auto" }}>{tc.args}</pre>
                            </div>
                            {tc.result && (
                              <div>
                                <span style={{ color: "var(--pencil)", fontSize: 8 }}>RESULT</span>
                                <pre style={{ margin: 0, fontSize: 9, whiteSpace: "pre-wrap", maxHeight: 80, overflow: "auto" }}>{tc.result}</pre>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {m.verdict === "CLARIFY" && m.clarify_options && m.clarify_options.length > 0 && (
                    <div style={{ marginTop: 6, padding: 8, border: "1.3px solid var(--warn)", borderRadius: 6, background: "rgba(232,160,58,0.08)" }}>
                      <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--warn)", marginBottom: 6, fontWeight: 600 }}>CLARIFICATION NEEDED</div>
                      {m.clarify_options.map((opt) => (
                        <label key={opt} style={{ display: "flex", alignItems: "center", gap: 6, padding: "3px 0", cursor: "pointer", fontFamily: "var(--mono)", fontSize: 10 }}>
                          <input type="radio" name={`cl-${m.id}`} checked={clarifyChoice === opt} onChange={() => setClarifyChoice(opt)} />
                          {opt}
                        </label>
                      ))}
                      <button className="btn btn-accent" style={{ marginTop: 6, fontSize: 9, padding: "3px 12px" }} disabled={!clarifyChoice} onClick={() => { if (clarifyChoice) void send(clarifyChoice); }}>Continue</button>
                    </div>
                  )}
                </div>
              );
            })}
            {streaming && <StreamingStatus status={streamStatus} />}
            {messages.length > 0 && !streaming && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "8px 0" }}>
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => void send(s)} style={{ background: "var(--paper-2)", border: "1px solid var(--rule)", borderRadius: 12, padding: "4px 10px", fontFamily: "var(--mono)", fontSize: 9, cursor: "pointer", color: "var(--accent)" }}>{s}</button>
                ))}
              </div>
            )}
            <div ref={endRef} />
          </div>
        )}

        <div style={{ borderTop: "1px solid var(--rule)", padding: "8px 12px", display: "flex", gap: 8, flexShrink: 0, alignItems: "flex-end" }}>
          <textarea
            ref={taRef}
            className="input-field"
            style={{ flex: 1, resize: "none", minHeight: 32, maxHeight: 120, padding: "6px 10px" }}
            placeholder="Ask about your sprint, blockers, or team status..."
            value={input}
            rows={1}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + "px";
            }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }}
          />
          {showAdvanced && (
          <div style={{ position: "relative" }}>
            <button onClick={() => setModelOpen((p) => !p)} style={{
              background: "var(--paper-2)", border: "1px solid var(--rule)", borderRadius: 4,
              padding: "4px 8px", fontFamily: "var(--mono)", fontSize: 8, color: "var(--pencil)",
              cursor: "pointer", whiteSpace: "nowrap",
            }}>{selectedModel.split("-").slice(0, 3).join("-")} ▾</button>
            {modelOpen && (
              <>
                <div style={{ position: "fixed", inset: 0, zIndex: 998 }} onClick={() => setModelOpen(false)} />
                <div style={{
                  position: "absolute", bottom: "100%", right: 0, marginBottom: 4,
                  background: "var(--paper)", border: "1.3px solid var(--ink)", borderRadius: 5,
                  zIndex: 999, maxHeight: 200, overflow: "auto", minWidth: 200,
                }}>
                  {models.map((m) => (
                    <div key={m} onClick={() => { setSelectedModel(m); setModelOpen(false); }} style={{
                      padding: "5px 10px", fontFamily: "var(--mono)", fontSize: 9, cursor: "pointer",
                      background: m === selectedModel ? "var(--honey-light)" : "transparent",
                      color: m === selectedModel ? "var(--accent)" : "var(--ink)",
                      fontWeight: m === selectedModel ? 600 : 400,
                    }}>{m}</div>
                  ))}
                </div>
              </>
            )}
          </div>
          )}
          <button onClick={() => setShowAdvanced((p) => !p)} style={{
            background: "none", border: "none", fontFamily: "var(--mono)", fontSize: 8,
            color: showAdvanced ? "var(--accent)" : "var(--pencil)", cursor: "pointer", padding: "4px 4px",
            textDecoration: "underline",
          }}>{showAdvanced ? "Advanced" : "Advanced"}</button>
          <button className="btn btn-accent" onClick={() => void send()} disabled={streaming} style={{ padding: "6px 12px", fontSize: 14, lineHeight: 1 }}>↑</button>
        </div>
      </div>
    </div>
  );
}
