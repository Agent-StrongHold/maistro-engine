import { useState } from "react";

export default function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Login failed");
      }
      window.location.href = "/";
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#e9e3d3" }}>
      <form onSubmit={handleSubmit} style={{ width: 320, background: "var(--paper)", border: "2px solid var(--ink)", borderRadius: 8, padding: "24px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontFamily: "var(--hand)", fontSize: 32, fontWeight: 700 }}>{"\uD83D\uDC1D"}</div>
          <div style={{ fontFamily: "var(--hand)", fontSize: 20, fontWeight: 600, marginTop: 4 }}>Hive Conductor</div>
          <div style={{ fontFamily: "var(--hand)", fontSize: 12, color: "var(--pencil)", marginTop: 2 }}>Sign in to your hive</div>
        </div>

        {error && <div style={{ padding: "6px 10px", background: "rgba(196,69,42,0.12)", border: "1px solid var(--danger)", borderRadius: 4, fontFamily: "var(--mono)", fontSize: 9, color: "var(--danger)" }}>{error}</div>}

        <div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginBottom: 3 }}>USERNAME</div>
          <input className="input-field" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus />
        </div>
        <div>
          <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--pencil)", marginBottom: 3 }}>PASSWORD</div>
          <input className="input-field" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </div>

        <button className="btn btn-accent" type="submit" disabled={loading || !username || !password} style={{ width: "100%", marginTop: 4 }}>
          {loading ? "signing in..." : "enter the hive"}
        </button>
      </form>
    </div>
  );
}
