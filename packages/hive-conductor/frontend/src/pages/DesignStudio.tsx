import { Card, PageHeader } from "../components/shared";

export default function DesignStudio() {
  return (
    <div>
      <PageHeader
        title="Design studio"
        subtitle="Canvas / architecture placeholders — route lives at /cli/canvas per shell nav."
      />
      <Card>
        <p className="muted">
          Phase 1 ships navigation + layout only. Wire Konva or maistro-canvas here in a later phase.
        </p>
      </Card>
    </div>
  );
}
