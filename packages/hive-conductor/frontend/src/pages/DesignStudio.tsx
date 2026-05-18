export default function DesignStudio() {
  return (
    <div>
      <div className="page-header">
        <h1 style={{ fontFamily: "var(--hand)", fontSize: 24, fontWeight: 600 }}>Design Studio</h1>
        <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--pencil)" }}>agent-assisted design</span>
      </div>
      <div className="card" style={{ textAlign: "center", padding: 40 }}>
        <div style={{ fontFamily: "var(--hand)", fontSize: 24, color: "var(--pencil)" }}>Phase 1 ships navigation + layout only</div>
        <div style={{ fontFamily: "var(--hand)", fontSize: 14, color: "var(--pencil)", marginTop: 8 }}>Wire Konva or maistro-canvas here in a later phase.</div>
      </div>
    </div>
  );
}
