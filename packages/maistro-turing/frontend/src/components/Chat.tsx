import { useRef, useState } from "react";
import { api } from "@/lib/api";

interface Msg {
  role: "user" | "turing";
  text: string;
}

export default function Chat() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const session = useRef<string | undefined>(undefined);
  const logRef = useRef<HTMLDivElement>(null);

  function scroll() {
    requestAnimationFrame(() => {
      if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    });
  }

  async function send() {
    const text = input.trim();
    if (!text || pending) return;
    setErr(null);
    setInput("");
    setMsgs((m) => [...m, { role: "user", text }]);
    setPending(true);
    scroll();
    try {
      // The backend is non-streaming today; the streaming indicator stands in
      // until the runtime exposes a token stream (see backend routes/chat.py).
      const res = await api.chat(text, session.current);
      session.current = res.session_id;
      setMsgs((m) => [...m, { role: "turing", text: res.reply }]);
    } catch (e) {
      setErr(String(e));
    } finally {
      setPending(false);
      scroll();
    }
  }

  return (
    <div className="chat">
      <div className="chat-log" ref={logRef}>
        {msgs.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.text}
          </div>
        ))}
        {pending && <div className="streaming">turing is thinking</div>}
      </div>
      {err && <p className="err">{err}</p>}
      <div className="chat-input">
        <input
          value={input}
          placeholder="say something to turing…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button onClick={send} disabled={pending}>
          send
        </button>
      </div>
    </div>
  );
}
