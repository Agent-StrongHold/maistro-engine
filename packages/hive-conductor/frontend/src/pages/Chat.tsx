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

const MODELS = ["claude-sonnet-4-6", "claude-opus-4-6", "o3-pro", "gemini-3.5-flash", "gpt-5", "gpt-5-mini"];

const SUGGESTED_PROMPTS = [
  "Explain quantum entanglement simply",
  "Write a short poem about autumn",
  "Help me debug a React useEffect hook",
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

export default function ChatPage() {
  const [sessions, setSessions] = useState<Session[]>([createSession()]);
  const [activeId, setActiveId] = useState(sessions[0].id);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [model, setModel] = useState(MODELS[0]);
  const [modelOpen, setModelOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const listEndRef = useRef<HTMLDivElement>(null);

  const activeSession = sessions.find((s) => s.id === activeId)!;

  useEffect(() => {
    listEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeSession.messages, streaming]);

  const updateSession = useCallback((id: string, updater: (s: Session) => Session) => {
    setSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || streaming) return;
    const userMsg: Message = { id: generateId(), role: "user", content: text.trim(), timestamp: new Date() };
    const sessionId = activeId;

    updateSession(sessionId, (s) => ({
      ...s,
      title: s.messages.length === 0 ? text.trim().slice(0, 30) : s.title,
      messages: [...s.messages, userMsg],
    }));

    setInput("");
    setStreaming(true);
    setTimeout(() => textareaRef.current?.focus(), 0);

    try {
      const res = await fetch("/v1/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ model, messages: [{ role: "user", content: text.trim() }] }),
      });
      const data = await res.json();
      const reply = data?.choices?.[0]?.message?.content || data?.response || "No response";
      const assistantMsg: Message = { id: generateId(), role: "assistant", content: reply, timestamp: new Date() };
      updateSession(sessionId, (s) => ({ ...s, messages: [...s.messages, assistantMsg] }));
    } catch (e: any) {
      const errMsg: Message = { id: generateId(), role: "assistant", content: `Error: ${e.message}`, timestamp: new Date() };
      updateSession(sessionId, (s) => ({ ...s, messages: [...s.messages, errMsg] }));
    }

    setStreaming(false);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, [activeId, streaming, updateSession]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(input); }
  };

  const newSession = () => {
    const s = createSession();
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
    setDrawerOpen(false);
    setTimeout(() => textareaRef.current?.focus(), 0);
  };

  const switchSession = (id: string) => { setActiveId(id); setDrawerOpen(false); setTimeout(() => textareaRef.current?.focus(), 0); };

  return (
    <div className="chat-layout">
      {drawerOpen && <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)} aria-hidden="true" />}
      <aside className={`drawer${drawerOpen ? " drawer--open" : ""}`} aria-label="Chat sessions">
        <div className="drawer-header">
          <span className="drawer-title">Sessions</span>
          <button className="btn-icon" onClick={newSession} aria-label="New chat">＋</button>
        </div>
        <nav>
          {sessions.map((s) => (
            <button key={s.id} className={`drawer-link${s.id === activeId ? " drawer-link--active" : ""}`} onClick={() => switchSession(s.id)} aria-current={s.id === activeId ? "page" : undefined}>
              <span className="drawer-link-title">{s.title}</span>
              <span className="drawer-link-time">{formatTime(s.createdAt)}</span>
            </button>
          ))}
        </nav>
      </aside>
      <div className="chat-layout">
        <header className="chat-header">
          <button className="btn-icon hamburger" onClick={() => setDrawerOpen((o) => !o)} aria-label="Toggle session drawer" aria-expanded={drawerOpen}>☰</button>
          <span className="chat-header-title">AI Assistant</span>
          <div className="model-selector">
            <button className="btn-model" onClick={() => setModelOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={modelOpen} aria-label={`Current model: ${model}`}>
              {model} <span aria-hidden="true">▾</span>
            </button>
            {modelOpen && (
              <ul className="model-dropdown" role="listbox" aria-label="Select model">
                {MODELS.map((m) => (
                  <li key={m} role="option" aria-selected={m === model} className={`model-option${m === model ? " model-option--active" : ""}`} onClick={() => { setModel(m); setModelOpen(false); }}>{m}</li>
                ))}
              </ul>
            )}
          </div>
        </header>
        <main className="chat-main">
          <div role="log" aria-live="polite" aria-label="Chat messages" className="message-list">
            {activeSession.messages.length === 0 && !streaming && (
              <div className="empty-state">
                <p className="empty-title">What can I help you with?</p>
                <div className="suggested-prompts">
                  {SUGGESTED_PROMPTS.map((p) => (
                    <button key={p} className="card prompt-btn" onClick={() => sendMessage(p)} aria-label={`Suggested prompt: ${p}`}>{p}</button>
                  ))}
                </div>
              </div>
            )}
            {activeSession.messages.map((msg) => (
              <div key={msg.id} className={`message message--${msg.role}`}>
                <div className="message-bubble card">{msg.content}</div>
                <span className="message-time">{formatTime(msg.timestamp)}</span>
              </div>
            ))}
            {streaming && (
              <div className="message message--assistant">
                <div className="message-bubble card typing-indicator" aria-label="Assistant is typing">
                  <span className="dot" /><span className="dot" /><span className="dot" />
                </div>
              </div>
            )}
            <div ref={listEndRef} />
          </div>
          <div className="chat-input-bar">
            <textarea ref={textareaRef} className="chat-textarea" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown} placeholder="Message… (Enter to send, Shift+Enter for newline)" aria-label="Message input" rows={2} disabled={streaming} />
            <button className="btn-primary send-btn" onClick={() => sendMessage(input)} disabled={!input.trim() || streaming} aria-label="Send message">Send</button>
          </div>
        </main>
      </div>
    </div>
  );
}