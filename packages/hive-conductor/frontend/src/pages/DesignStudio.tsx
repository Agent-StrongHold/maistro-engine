import { PageHeader } from "../components/shared";

export default function DesignStudio() {
  return (
    <div>
      <PageHeader title="Design Studio" subtitle="Agent-assisted visual design — coming soon" />
      <div className="card" style={{ textAlign: "center", padding: 40 }}>
        <div style={{ fontFamily: "var(--hand)", fontSize: 24, color: "var(--pencil)" }}>Phase 1 ships navigation + layout only</div>
        <div style={{ fontFamily: "var(--hand)", fontSize: 14, color: "var(--pencil)", marginTop: 8 }}>Wire Konva or maistro-canvas here in a later phase.</div>
      </div>
    </div>
  );
}
