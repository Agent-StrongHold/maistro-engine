import { useState, type FormEvent } from "react";
import { useWorkspaces } from "../context/WorkspaceContext";

/** Persona/Workspace system: the live tab strip a user switches between.
 * Each tab is one adopted persona's Workspace; switching applies that
 * workspace's theme. Creation is deliberately minimal (name only, persona
 * defaults to "pm_fleet") since it's the only real PersonaTemplate seeded
 * on disk today -- a persona picker is meaningful once more exist. */
export function WorkspaceTabs() {
  const { workspaces, activeWorkspaceId, selectWorkspace, createWorkspace, ready } =
    useWorkspaces();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!ready) return null;

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      await createWorkspace({ name: trimmed, persona_template_id: "pm_fleet" });
      setName("");
      setCreating(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="workspace-tabs" role="tablist" aria-label="Workspaces">
      {workspaces.map((w) => (
        <button
          key={w.id}
          type="button"
          role="tab"
          aria-selected={w.id === activeWorkspaceId}
          className={`workspace-tab${w.id === activeWorkspaceId ? " active" : ""}`}
          onClick={() => selectWorkspace(w.id)}
          title={w.persona_template_id}
        >
          {w.name}
        </button>
      ))}

      {creating ? (
        <form onSubmit={(e) => void handleCreate(e)} className="workspace-tab-new-form">
          <input
            autoFocus
            value={name}
            disabled={busy}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => {
              if (!name.trim()) setCreating(false);
            }}
            placeholder="Workspace name"
            aria-label="New workspace name"
          />
        </form>
      ) : (
        <button
          type="button"
          className="workspace-tab workspace-tab-add"
          onClick={() => setCreating(true)}
          aria-label="New workspace"
          title="New workspace"
        >
          +
        </button>
      )}
      {error && <span className="workspace-tab-error">{error}</span>}
    </div>
  );
}
