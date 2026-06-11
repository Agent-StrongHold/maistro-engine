import { useState, useRef, useEffect, useCallback } from "react";

type Role = "user" | "assistant";

interface Message {
  id: string;
  role: Role;
  content: string;
  timestamp: Date;
}

interface Session {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
}

const SUGGESTED_PROMPTS_HEADING = "AI Project Manager — ask about your sprint, run research, generate documents";
const SUGGESTED_PROMPTS = [
  "What are my top blockers this sprint?",
  "Research competitors to Cursor AI",
  "Draft a PRD for real-time collaboration",
];

function generateId() {
  return Math.random().toString(36).slice(2, 10);
}

function formatTime(date: Date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function createSession(title = "New Chat"): Session {
  return { id: generateId(), title, messages: [], createdAt: new Date() };
}

function getFollowUps(lastResponse: string): string[] {
  const lower = lastResponse.toLowerCase();
  if (lower.includes("jira") || lower.includes("ticket") || lower.includes("issue"))
    return ["Show me the details", "What's blocking these?", "Create a summary report"];
  if (lower.includes("agent") || lower.includes("created") || lower.includes("widget"))
    return ["Run it now", "Show me the config", "What else can you do?"];
  if (lower.includes("metric") || lower.includes("latency") || lower.includes("cost"))
    return ["Compare to last week", "Break down by agent", "Set up an alert"];
  if (lower.includes("error") || lower.includes("failed"))
    return ["Show the logs", "Try a different approach", "What caused this?"];
  return ["Tell me more", "What should I do next?", "Summarize this"];
}

export default function ChatPage() {
  const [models, setModels] = useState<string[]>([]);
  const MODELS = models;
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState("");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(200);
  const sidebarDrag = useRef<{ startX: number; startW: number } | null>(null);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [model, setModel] = useState("");

  // Load sessions from server
  useEffect(() => {
    fetch("/v1/chat/sessions", { credentials: "same-origin" })
      .then((r) => r.json())
      .then((data) => {
        const list: Session[] = (Array.isArray(data) ? data : []).map((s: any) => ({
          id: s.id, title: s.title || "Chat", messages: [], createdAt: new Date(s.updated_at || s.created_at || Date.now()),
        }));
        setSessions(list);
        if (list.length > 0 && !activeId) setActiveId(list[0].id);
      })
      .catch(() => {});
  }, []);

  // Load messages when switching session
  useEffect(() => {
    if (!activeId) return;
    fetch(`/v1/chat/sessions/${activeId}`, { credentials: "same-origin" })
      .then((r) => r.json())
      .then((data) => {
        const msgs: Message[] = (data.messages || []).map((m: any) => ({
          id: m.id || generateId(), role: m.role as Role, content: m.content, timestamp: new Date(m.timestamp || m.created_at || Date.now()),
        }));
        setSessions((prev) => prev.map((s) => s.id === activeId ? { ...s, messages: msgs, title: data.title || s.title } : s));
      })
      .catch(() => {});
  }, [activeId]);

  useEffect(() => {
    fetch("/v1/settings/models", { credentials: "same-origin" })
      .then((res) => res.json())
      .then((data) => {
        const arr = Array.isArray(data) ? data : (data.models || data.data || []);
        const list = arr.map((m: any) => typeof m === "string" ? m : (m.id || m.name || "")).filter(Boolean);
        if (list.length > 0) { setModels(list); }
      })
      .catch(() => {});
    fetch("/v1/settings", { credentials: "same-origin" })
      .then(r => r.json())
      .then(s => { if (s.default_model) setModel(s.default_model); })
      .catch(() => {});
  }, []);
  const [modelOpen, setModelOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const listEndRef = useRef<HTMLDivElement>(null);

  const activeSession = sessions.find((s) => s.id === activeId) || { id: "", title: "", messages: [] as Message[], createdAt: new Date() };

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSession.messages, streaming]);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.rows = 1;
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    }
  }, [input]);

  const updateSession = useCallback((id: string, updater: (s: Session) => Session) => {
    setSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || streaming) return;
    const userMsg: Message = { id: generateId(), role: "user", content: text.trim(), timestamp: new Date() };
    const sessionId = activeId;
    const assistantId = generateId();

    updateSession(sessionId, (s) => ({
      ...s,
      title: s.messages.length === 0 ? text.trim().slice(0, 30) : s.title,
      messages: [...s.messages, userMsg],
    }));

    // Persist user message to server
    fetch(`/v1/chat/sessions/${sessionId}/messages`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role: "user", content: text.trim() }) }).catch(() => {});

    setInput("");
    setStreaming(true);

    // Add empty assistant message that we'll stream into
    updateSession(sessionId, (s) => ({
      ...s,
      messages: [...s.messages, { id: assistantId, role: "assistant" as Role, content: "", timestamp: new Date() }],
    }));

    try {
      const res = await fetch("/v1/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ model, messages: [...activeSession.messages.slice(-20).map(m => ({ role: m.role, content: m.content.slice(0, 2000) })), { role: "user", content: text.trim() }] }),
      });

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split("\n");
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === "token" || event.type === "content") {
                accumulated += event.content || event.token || "";
                updateSession(sessionId, (s) => ({
                  ...s,
                  messages: s.messages.map((m) => m.id === assistantId ? { ...m, content: accumulated } : m),
                }));
              } else if (event.type === "done") {
                if (event.content && !accumulated) {
                  accumulated = event.content;
                  updateSession(sessionId, (s) => ({
                    ...s,
                    messages: s.messages.map((m) => m.id === assistantId ? { ...m, content: accumulated } : m),
                  }));
                }
              } else if (event.type === "tool_call") {
                accumulated += `\n🔧 ${event.tool || "tool"}…\n`;
                updateSession(sessionId, (s) => ({
                  ...s,
                  messages: s.messages.map((m) => m.id === assistantId ? { ...m, content: accumulated } : m),
                }));
              } else if (event.type === "tool_result") {
                accumulated += `✓ ${event.summary || ""}\n`;
                updateSession(sessionId, (s) => ({
                  ...s,
                  messages: s.messages.map((m) => m.id === assistantId ? { ...m, content: accumulated } : m),
                }));
              } else if (event.type === "status") {
                // Optional: show status in UI
              }
            } catch { /* skip malformed */ }
          }
        }
      }

      // Fallback if stream returned nothing
      if (!accumulated) {
        const fallback = await res.text();
        try {
          const data = JSON.parse(fallback);
          accumulated = data?.choices?.[0]?.message?.content || "No response";
        } catch {
          accumulated = fallback || "No response";
        }
        updateSession(sessionId, (s) => ({
          ...s,
          messages: s.messages.map((m) => m.id === assistantId ? { ...m, content: accumulated } : m),
        }));
      }
    } catch (e: any) {
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) => m.id === assistantId ? { ...m, content: `Error: ${e.message}` } : m),
      }));
    }

    setStreaming(false);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [activeId, streaming, model, updateSession]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
  };

  const newSession = () => {
    fetch("/v1/chat/sessions", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: "New Chat" }) })
      .then((r) => r.json())
      .then((s) => {
        const session: Session = { id: s.id, title: s.title, messages: [], createdAt: new Date() };
        setSessions((prev) => [session, ...prev]);
        setActiveId(s.id);
        setDrawerOpen(false);
        // Fetch personalized greeting
        fetch("/v1/chat/greeting", { credentials: "same-origin" }).then(r => r.json()).then(g => {
          if (g?.greeting) {
            const msg: Message = { role: "assistant", content: g.greeting, timestamp: new Date().toISOString() };
            setSessions((prev) => prev.map(sess => sess.id === s.id ? { ...sess, messages: [msg] } : sess));
          }
        }).catch(() => {});
      })
      .catch(() => {});
  };

  const switchSession = (id: string) => { setActiveId(id); setDrawerOpen(false); setTimeout(() => textareaRef.current?.focus(), 0); };

  const renameSession = (id: string) => {
    const name = prompt("Rename session:");
    if (!name) return;
    setSessions((prev) => prev.map((s) => s.id === id ? { ...s, title: name } : s));
  };

  const autoRenameSession = async (id: string) => {
    const session = sessions.find((s) => s.id === id);
    if (!session || session.messages.length === 0) return;
    const firstMsgs = session.messages.slice(0, 4).map(m => m.content.slice(0, 200)).join("\n");
    try {
      const res = await fetch("/v1/chat/complete", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model, messages: [{ role: "user", content: `Give this conversation a short title (max 5 words, no quotes):\n\n${firstMsgs}` }] }),
      });
      const data = await res.json();
      const title = (data?.choices?.[0]?.message?.content || "").trim().slice(0, 40);
      if (title) setSessions((prev) => prev.map((s) => s.id === id ? { ...s, title } : s));
    } catch { /* ignore */ }
  };

  const deleteSession = (id: string) => {
    if (!confirm("Delete this session?")) return;
    fetch(`/v1/chat/sessions/${id}`, { method: "DELETE", credentials: "same-origin" }).catch(() => {});
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeId === id) {
      const remaining = sessions.filter((s) => s.id !== id);
      setActiveId(remaining.length > 0 ? remaining[0].id : "");
    }
  };

  return (
    <div style={{ display: "flex", height: "100vh", overflow: "hidden", background: "#0a0914", color: "#f3f0fb", fontFamily: "'Inter', -apple-system, system-ui, sans-serif" }}>
      {/* Session drawer — collapsible */}
      {!sidebarCollapsed && (
      <aside style={{ width: sidebarWidth, borderRight: "1px solid rgba(196,166,97,0.14)", background: "rgba(13,12,26,0.6)", display: "flex", flexDirection: "column", height: "100vh", flexShrink: 0, position: "relative" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 12px 8px", flexShrink: 0 }}>
          <span style={{ fontSize: "0.6rem", fontWeight: 700, color: "#c4a661", textTransform: "uppercase", letterSpacing: "0.1em" }}>Sessions</span>
          <div style={{ display: "flex", gap: 4 }}>
            <button onClick={newSession} style={{ background: "none", border: "none", color: "#a78bfa", cursor: "pointer", fontSize: "0.9rem" }}>+</button>
            <button onClick={() => setSidebarCollapsed(true)} style={{ background: "none", border: "none", color: "#5a5478", cursor: "pointer", fontSize: "0.7rem" }}>◁</button>
          </div>
        </div>
        <nav style={{ flex: 1, overflowY: "auto", padding: "0 8px 12px" }}>
        {sessions.map((s) => (
          <div key={s.id} className="sess-item" onClick={() => switchSession(s.id)} style={{
            display: "flex", alignItems: "center", padding: "5px 8px", borderRadius: 6, cursor: "pointer", marginBottom: 1,
            background: s.id === activeId ? "rgba(167,139,250,0.1)" : "transparent",
            borderLeft: s.id === activeId ? "2px solid #c4a661" : "2px solid transparent",
            position: "relative",
          }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: "0.7rem", fontWeight: 500, color: s.id === activeId ? "#f3f0fb" : "#8b83a8", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.title}</div>
              <div style={{ fontSize: "0.52rem", color: "#5a5478" }}>{formatTime(s.createdAt)}</div>
            </div>
            {s.id === activeId && (
              <div className="sess-actions" onClick={e => e.stopPropagation()} style={{ position: "absolute", right: 4, top: "50%", transform: "translateY(-50)", display: "flex", gap: 0, background: "rgba(13,12,26,0.9)", borderRadius: 4, padding: "1px 2px", opacity: 0, pointerEvents: "none" }}>
                <button onClick={() => autoRenameSession(s.id)} title="Auto-name" style={{ background: "none", border: "none", color: "#a78bfa", cursor: "pointer", fontSize: "9px", padding: "1px 2px", lineHeight: 1 }}>✦</button>
                <button onClick={() => renameSession(s.id)} title="Rename" style={{ background: "none", border: "none", color: "#8b83a8", cursor: "pointer", fontSize: "9px", padding: "1px 2px", lineHeight: 1 }}>✎</button>
                <button onClick={() => deleteSession(s.id)} title="Delete" style={{ background: "none", border: "none", color: "#e87c7c", cursor: "pointer", fontSize: "9px", padding: "1px 2px", lineHeight: 1 }}>✕</button>
              </div>
            )}
          </div>
        ))}
        </nav>
        {/* Resize handle */}
        <div onMouseDown={(e) => { e.preventDefault(); sidebarDrag.current = { startX: e.clientX, startW: sidebarWidth }; const onMove = (ev: MouseEvent) => { if (!sidebarDrag.current) return; setSidebarWidth(Math.max(120, Math.min(400, sidebarDrag.current.startW + (ev.clientX - sidebarDrag.current.startX)))); }; const onUp = () => { sidebarDrag.current = null; document.removeEventListener("mousemove", onMove); document.removeEventListener("mouseup", onUp); }; document.addEventListener("mousemove", onMove); document.addEventListener("mouseup", onUp); }}
          style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: 4, cursor: "col-resize", background: "transparent" }}
          onMouseOver={e => (e.currentTarget.style.background = "rgba(167,139,250,0.3)")}
          onMouseOut={e => (e.currentTarget.style.background = "transparent")} />
      </aside>
      )}
      {sidebarCollapsed && (
        <div style={{ width: 32, borderRight: "1px solid rgba(196,166,97,0.14)", background: "rgba(13,12,26,0.6)", display: "flex", flexDirection: "column", alignItems: "center", paddingTop: 12, flexShrink: 0 }}>
          <button onClick={() => setSidebarCollapsed(false)} style={{ background: "none", border: "none", color: "#5a5478", cursor: "pointer", fontSize: "0.7rem" }}>▷</button>
        </div>
      )}

      {/* Main chat area — fills remaining space, scrolls messages only */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 20px", borderBottom: "1px solid rgba(196,166,97,0.14)" }}>
          <span style={{ fontFamily: "Georgia, serif", fontSize: "1rem", fontWeight: 600 }}>Fantasia</span>
          <div style={{ position: "relative" }}>
            <button onClick={() => setModelOpen((o) => !o)} style={{ padding: "4px 10px", borderRadius: 8, border: "1px solid rgba(196,166,97,0.14)", background: "transparent", color: "#8b83a8", fontSize: "0.7rem", cursor: "pointer" }}>
              {model || "select model"} ▾
            </button>
            {modelOpen && (
              <div style={{ position: "absolute", top: "100%", right: 0, marginTop: 4, background: "#16142a", border: "1px solid rgba(196,166,97,0.14)", borderRadius: 8, padding: 4, zIndex: 20, minWidth: 160, maxHeight: 300, overflowY: "auto" }}>
                {MODELS.map((m) => (
                  <button key={m} onClick={() => { setModel(m); setModelOpen(false); }} style={{ display: "block", width: "100%", textAlign: "left", padding: "5px 8px", border: "none", background: m === model ? "rgba(167,139,250,0.1)" : "transparent", color: m === model ? "#f3f0fb" : "#8b83a8", fontSize: "0.7rem", cursor: "pointer", borderRadius: 4 }}>{m}</button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Messages — this scrolls */}
        <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
          {activeSession.messages.length === 0 && !streaming && (
            <div style={{ textAlign: "center", paddingTop: 80 }}>
              <div style={{ fontFamily: "Georgia, serif", fontSize: "1.2rem", marginBottom: 16 }}>What can I help you conduct?</div>
              <div style={{ display: "flex", gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
                {SUGGESTED_PROMPTS.map((p) => (
                  <button key={p} onClick={() => sendMessage(p)} style={{ padding: "8px 14px", borderRadius: 11, border: "1px solid rgba(196,166,97,0.14)", background: "rgba(22,20,38,0.72)", color: "#8b83a8", fontSize: "0.75rem", cursor: "pointer" }}>{p}</button>
                ))}
              </div>
            </div>
          )}
          {activeSession.messages.map((msg, idx) => (
            <div key={msg.id}>
              <div style={{ marginBottom: 8, display: "flex", flexDirection: "column", alignItems: msg.role === "user" ? "flex-end" : "flex-start" }}>
                <div style={{
                  maxWidth: "70%", padding: "10px 14px", borderRadius: 12, fontSize: "0.82rem", lineHeight: 1.5, whiteSpace: "pre-wrap",
                  background: msg.role === "user" ? "rgba(167,139,250,0.12)" : "rgba(22,20,38,0.72)",
                  border: `1px solid ${msg.role === "user" ? "rgba(167,139,250,0.2)" : "rgba(196,166,97,0.1)"}`,
                  color: "#f3f0fb",
                }}>{msg.content}</div>
                <span style={{ fontSize: "0.55rem", color: "#5a5478", marginTop: 3 }}>{formatTime(msg.timestamp)}</span>
              </div>
              {/* Follow-up prompts after last assistant message */}
              {msg.role === "assistant" && idx === activeSession.messages.length - 1 && !streaming && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12, paddingLeft: 4 }}>
                  {getFollowUps(msg.content).map((p) => (
                    <button key={p} onClick={() => sendMessage(p)} style={{ padding: "5px 10px", borderRadius: 8, border: "1px solid rgba(196,166,97,0.14)", background: "transparent", color: "#8b83a8", fontSize: "0.68rem", cursor: "pointer" }}>{p}</button>
                  ))}
                </div>
              )}
            </div>
          ))}
          {streaming && (
            <div style={{ display: "flex", gap: 4, padding: "10px 14px", borderRadius: 12, background: "rgba(22,20,38,0.72)", border: "1px solid rgba(196,166,97,0.1)", width: "fit-content" }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#a78bfa", animation: "orb 1s infinite" }} />
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#a78bfa", animation: "orb 1s 0.2s infinite" }} />
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#a78bfa", animation: "orb 1s 0.4s infinite" }} />
            </div>
          )}
          <div ref={listEndRef} />
        </div>

        {/* Input — pinned to bottom */}
        <div style={{ padding: "12px 20px", borderTop: "1px solid rgba(196,166,97,0.14)", display: "flex", gap: 8, alignItems: "flex-end", flexShrink: 0 }}>
          <textarea ref={textareaRef} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
            placeholder="Message… (Enter to send)" disabled={streaming} rows={1}
            style={{ flex: 1, resize: "none", padding: "10px 14px", borderRadius: 11, border: "1px solid rgba(196,166,97,0.14)", background: "rgba(0,0,0,0.3)", color: "#f3f0fb", fontSize: "0.82rem", fontFamily: "'Inter', sans-serif", outline: "none" }} />
          <button onClick={() => sendMessage(input)} disabled={!input.trim() || streaming}
            style={{ padding: "10px 18px", borderRadius: 11, border: "none", background: "linear-gradient(135deg, #a78bfa, #8b5cf6)", color: "#fff", fontSize: "0.78rem", fontWeight: 600, cursor: !input.trim() || streaming ? "default" : "pointer", opacity: !input.trim() || streaming ? 0.4 : 1 }}>Send</button>
        </div>
      </div>
      <style>{`@keyframes orb{0%,100%{transform:scale(1);opacity:.4}50%{transform:scale(1.3);opacity:1}} .sess-item:hover .sess-actions{opacity:1 !important;pointer-events:auto !important}`}</style>
    </div>
  );
}