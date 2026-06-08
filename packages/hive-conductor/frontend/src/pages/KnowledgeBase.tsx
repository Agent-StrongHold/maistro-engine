import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPut } from "../lib/api";
import { PageHeader, Card } from "../components/shared";

type ProgramContext = {
  program_name: string;
  summary: string;
  goals: string[];
  constraints: string[];
  stakeholders: string[];
  tools: string[];
  facts: string[];
  open_questions: string[];
  guidance_log: string[];
  interview_complete: boolean;
  interview_step: number;
  updated_at: string;
};

type ContextResponse = {
  context: ProgramContext;
  interview: { complete: boolean; next_question?: string };
};

type EditableListField = "goals" | "constraints" | "stakeholders" | "tools" | "facts" | "open_questions" | "guidance_log";
type EditableTextField = "program_name" | "summary";

function ListEditor({ label, items, onSave }: { label: string; items: string[]; onSave: (items: string[]) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  function startEdit() {
    setDraft(items.join("\n"));
    setEditing(true);
  }

  function save() {
    const lines = draft.split("\n").map((l) => l.trim()).filter(Boolean);
    onSave(lines);
    setEditing(false);
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <strong style={{ fontFamily: "var(--mono)", fontSize: 11 }}>{label}</strong>
        {!editing && (
          <button className="btn btn-sm" onClick={startEdit} style={{ fontSize: 10, padding: "2px 8px" }}>
            edit
          </button>
        )}
      </div>
      {editing ? (
        <div>
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={Math.max(3, items.length + 1)}
            style={{ width: "100%", fontFamily: "var(--mono)", fontSize: 11, padding: 8, border: "1.5px solid var(--accent)", borderRadius: 4, resize: "vertical" }}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
            <button className="btn btn-sm" onClick={save}>save</button>
            <button className="btn btn-sm" onClick={() => setEditing(false)} style={{ background: "var(--rule)" }}>cancel</button>
          </div>
        </div>
      ) : items.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 18, fontFamily: "var(--mono)", fontSize: 11 }}>
          {items.map((item, i) => <li key={i} style={{ marginBottom: 2 }}>{item}</li>)}
        </ul>
      ) : (
        <span style={{ fontFamily: "var(--mono)", fontSize: 11, opacity: 0.5 }}>— none —</span>
      )}
    </div>
  );
}

function TextEditor({ label, value, onSave }: { label: string; value: string; onSave: (v: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  function startEdit() {
    setDraft(value);
    setEditing(true);
  }

  function save() {
    onSave(draft.trim());
    setEditing(false);
  }

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <strong style={{ fontFamily: "var(--mono)", fontSize: 11 }}>{label}</strong>
        {!editing && (
          <button className="btn btn-sm" onClick={startEdit} style={{ fontSize: 10, padding: "2px 8px" }}>
            edit
          </button>
        )}
      </div>
      {editing ? (
        <div>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            style={{ width: "100%", fontFamily: "var(--mono)", fontSize: 11, padding: 6, border: "1.5px solid var(--accent)", borderRadius: 4 }}
          />
          <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
            <button className="btn btn-sm" onClick={save}>save</button>
            <button className="btn btn-sm" onClick={() => setEditing(false)} style={{ background: "var(--rule)" }}>cancel</button>
          </div>
        </div>
      ) : (
        <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>{value || <span style={{ opacity: 0.5 }}>— not set —</span>}</span>
      )}
    </div>
  );
}

export default function KnowledgeBase() {
  const [ctx, setCtx] = useState<ProgramContext | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await apiGet<ContextResponse>("/v1/program/context");
      setCtx(res.context);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function saveField(field: string, value: unknown) {
    setSaving(true);
    try {
      const res = await apiPut<ContextResponse>("/v1/program/context", { [field]: value });
      setCtx(res.context);
    } catch (e) {
      setError(String(e));
    }
    setSaving(false);
  }

  if (error && !ctx) return <div style={{ padding: 24, color: "var(--danger)" }}>{error}</div>;
  if (!ctx) return <div style={{ padding: 24, fontFamily: "var(--hand)", fontSize: 18 }}>loading...</div>;

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      <PageHeader
        title="Knowledge Base"
        subtitle="What the PM fleet knows about you and your program. Edit anything to correct or steer the agents."
      />
      {saving && <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--accent)", marginBottom: 8 }}>saving...</div>}

      <Card>
        <h3 style={{ fontFamily: "var(--hand)", fontSize: 16, margin: "0 0 12px" }}>🧠 Program Identity</h3>
        <TextEditor label="Program name" value={ctx.program_name} onSave={(v) => saveField("program_name", v)} />
        <TextEditor label="Summary" value={ctx.summary} onSave={(v) => saveField("summary", v)} />
      </Card>

      <Card>
        <h3 style={{ fontFamily: "var(--hand)", fontSize: 16, margin: "0 0 12px" }}>🎯 Goals &amp; Constraints</h3>
        <ListEditor label="Goals (90-day outcomes)" items={ctx.goals} onSave={(v) => saveField("goals", v)} />
        <ListEditor label="Constraints / risks" items={ctx.constraints} onSave={(v) => saveField("constraints", v)} />
      </Card>

      <Card>
        <h3 style={{ fontFamily: "var(--hand)", fontSize: 16, margin: "0 0 12px" }}>👥 People &amp; Tools</h3>
        <ListEditor label="Stakeholders" items={ctx.stakeholders} onSave={(v) => saveField("stakeholders", v)} />
        <ListEditor label="Tools" items={ctx.tools} onSave={(v) => saveField("tools", v)} />
      </Card>

      <Card>
        <h3 style={{ fontFamily: "var(--hand)", fontSize: 16, margin: "0 0 12px" }}>📝 Learned Facts</h3>
        <ListEditor label="Facts the fleet has learned" items={ctx.facts} onSave={(v) => saveField("facts", v)} />
        <ListEditor label="Open questions" items={ctx.open_questions} onSave={(v) => saveField("open_questions", v)} />
      </Card>

      <Card>
        <h3 style={{ fontFamily: "var(--hand)", fontSize: 16, margin: "0 0 12px" }}>💬 Guidance History</h3>
        <p style={{ fontFamily: "var(--mono)", fontSize: 10, opacity: 0.7, margin: "0 0 8px" }}>
          The last 3 entries are injected into every agent prompt as "PM goals for the next 90 days".
        </p>
        <ListEditor label="Guidance log" items={ctx.guidance_log} onSave={(v) => saveField("guidance_log", v)} />
      </Card>

      <div style={{ fontFamily: "var(--mono)", fontSize: 9, opacity: 0.5, marginTop: 16, textAlign: "right" }}>
        Last updated: {ctx.updated_at ? new Date(ctx.updated_at).toLocaleString() : "never"}
        {" · "}Interview: {ctx.interview_complete ? "complete" : `step ${ctx.interview_step}/${5}`}
      </div>
    </div>
  );
}
