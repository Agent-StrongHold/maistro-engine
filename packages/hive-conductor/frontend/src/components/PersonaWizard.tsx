import { useState, type FormEvent } from "react";
import { apiPost } from "../lib/api";

type WizardAgent = {
  agent: string;
  role: string;
  toolsText: string;
  skillsText: string;
};

function parseCommaList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function emptyAgent(): WizardAgent {
  return { agent: "", role: "", toolsText: "", skillsText: "" };
}

const STEPS = ["Basics", "Voice", "Scope", "Agents", "Review"] as const;

/** In-app persona authoring. Every persona was previously a hand-authored
 * YAML file (maistro.personas.schema.PersonaTemplate) -- this walks a user
 * through the same shape step by step and POSTs it to
 * services/persona_authoring.py's writable template store. The result
 * shows up in WorkspaceTabs' persona picker exactly like a shipped persona
 * (e.g. pm_fleet), since both are read through the same
 * all_persona_templates(). */
export function PersonaWizard() {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [id, setId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [tagline, setTagline] = useState("");
  const [archetype, setArchetype] = useState("");
  const [audience, setAudience] = useState("");
  const [tone, setTone] = useState("");
  const [uiScopeText, setUiScopeText] = useState("");
  const [agents, setAgents] = useState<WizardAgent[]>([emptyAgent()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);

  function reset() {
    setStep(0);
    setId("");
    setDisplayName("");
    setTagline("");
    setArchetype("");
    setAudience("");
    setTone("");
    setUiScopeText("");
    setAgents([emptyAgent()]);
    setError(null);
    setCreated(null);
  }

  function close() {
    setOpen(false);
    reset();
  }

  function updateAgent(index: number, patch: Partial<WizardAgent>) {
    setAgents((prev) => prev.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  }

  function addAgent() {
    setAgents((prev) => [...prev, emptyAgent()]);
  }

  function removeAgent(index: number) {
    setAgents((prev) => (prev.length > 1 ? prev.filter((_, i) => i !== index) : prev));
  }

  const validAgents = agents.filter((a) => a.agent.trim());
  const basicsComplete = Boolean(id.trim() && displayName.trim());
  const canFinish = basicsComplete && validAgents.length > 0;

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!canFinish || busy) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost("/v1/workspaces/persona-templates", {
        id: id.trim(),
        display_name: displayName.trim(),
        tagline: tagline.trim(),
        archetype: archetype.trim(),
        audience: audience.trim(),
        tone: tone.trim(),
        ui_scope: parseCommaList(uiScopeText),
        agents: validAgents.map((a) => ({
          agent: a.agent.trim(),
          role: a.role.trim(),
          tools: parseCommaList(a.toolsText),
          skills: parseCommaList(a.skillsText),
        })),
      });
      setCreated(id.trim());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create persona");
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        className="workspace-tab persona-wizard-toggle"
        onClick={() => setOpen(true)}
      >
        New persona
      </button>
    );
  }

  return (
    <div className="persona-wizard-overlay" role="dialog" aria-label="Create a new persona">
      <div className="persona-wizard-panel">
        <div className="persona-wizard-header">
          <span>Create a new persona</span>
          <button type="button" onClick={close} aria-label="Close">
            &#x2715;
          </button>
        </div>

        {created ? (
          <div className="persona-wizard-success">
            <p>&quot;{created}&quot; was created. Pick it the next time you start a workspace.</p>
            <button type="button" onClick={close}>
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={(e) => void handleCreate(e)}>
            <div className="persona-wizard-steps">
              {STEPS.map((label, i) => (
                <span key={label} className={`persona-wizard-step${i === step ? " active" : ""}`}>
                  {i + 1}. {label}
                </span>
              ))}
            </div>

            {step === 0 && (
              <div className="persona-wizard-fields">
                <label>
                  Persona id (lowercase, underscores)
                  <input
                    value={id}
                    onChange={(e) => setId(e.target.value)}
                    placeholder="dinner_party"
                    aria-label="Persona id"
                  />
                </label>
                <label>
                  Display name
                  <input
                    value={displayName}
                    onChange={(e) => setDisplayName(e.target.value)}
                    placeholder="Dinner Party"
                    aria-label="Display name"
                  />
                </label>
                <label>
                  Tagline
                  <input
                    value={tagline}
                    onChange={(e) => setTagline(e.target.value)}
                    placeholder="Plan the night"
                    aria-label="Tagline"
                  />
                </label>
              </div>
            )}

            {step === 1 && (
              <div className="persona-wizard-fields">
                <label>
                  Voice archetype
                  <input
                    value={archetype}
                    onChange={(e) => setArchetype(e.target.value)}
                    placeholder="a gracious host"
                    aria-label="Voice archetype"
                  />
                </label>
                <label>
                  Audience
                  <input
                    value={audience}
                    onChange={(e) => setAudience(e.target.value)}
                    placeholder="small groups"
                    aria-label="Audience"
                  />
                </label>
                <label>
                  Tone
                  <input
                    value={tone}
                    onChange={(e) => setTone(e.target.value)}
                    placeholder="warm, attentive"
                    aria-label="Tone"
                  />
                </label>
              </div>
            )}

            {step === 2 && (
              <div className="persona-wizard-fields">
                <label>
                  Workspace nav sections (comma-separated)
                  <input
                    value={uiScopeText}
                    onChange={(e) => setUiScopeText(e.target.value)}
                    placeholder="Guests, Menu, Schedule"
                    aria-label="Nav sections"
                  />
                </label>
              </div>
            )}

            {step === 3 && (
              <div className="persona-wizard-agents">
                {agents.map((agent, i) => (
                  <div key={i} className="persona-wizard-agent">
                    <input
                      value={agent.agent}
                      onChange={(e) => updateAgent(i, { agent: e.target.value })}
                      placeholder="agent id, e.g. host"
                      aria-label={`Agent ${i + 1} id`}
                    />
                    <input
                      value={agent.role}
                      onChange={(e) => updateAgent(i, { role: e.target.value })}
                      placeholder="role description"
                      aria-label={`Agent ${i + 1} role`}
                    />
                    <input
                      value={agent.toolsText}
                      onChange={(e) => updateAgent(i, { toolsText: e.target.value })}
                      placeholder="tools (comma-separated)"
                      aria-label={`Agent ${i + 1} tools`}
                    />
                    <input
                      value={agent.skillsText}
                      onChange={(e) => updateAgent(i, { skillsText: e.target.value })}
                      placeholder="skills (comma-separated)"
                      aria-label={`Agent ${i + 1} skills`}
                    />
                    <button
                      type="button"
                      onClick={() => removeAgent(i)}
                      disabled={agents.length === 1}
                      aria-label={`Remove agent ${i + 1}`}
                    >
                      &#x2715;
                    </button>
                  </div>
                ))}
                <button type="button" onClick={addAgent}>
                  + Add agent
                </button>
              </div>
            )}

            {step === 4 && (
              <div className="persona-wizard-review">
                <div className="persona-wizard-review-title">
                  <strong>{displayName || id}</strong>
                  {tagline && ` — ${tagline}`}
                </div>
                <div>
                  {archetype}
                  {audience && `, for ${audience}`}
                  {tone && ` (${tone})`}
                </div>
                <ul>
                  {validAgents.map((a) => (
                    <li key={a.agent}>
                      {a.agent}: {a.role || "no role given"}
                      {a.toolsText && ` — tools: ${a.toolsText}`}
                      {a.skillsText && ` — skills: ${a.skillsText}`}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {error && <div className="persona-wizard-error">{error}</div>}

            <div className="persona-wizard-nav">
              {step > 0 && (
                <button type="button" onClick={() => setStep((s) => s - 1)} disabled={busy}>
                  Back
                </button>
              )}
              {step < STEPS.length - 1 ? (
                // Distinct `key`s from the submit button below force React to
                // mount a fresh DOM node on this step's last transition,
                // rather than mutating this same node's `type` attribute in
                // place. Without it, a click's native "submit" activation
                // step -- which runs after React's synchronous onClick --
                // sees the now-already-flipped `type="submit"` and submits
                // the form on the very click that was supposed to just
                // advance to the Review step.
                <button
                  key="next"
                  type="button"
                  onClick={() => setStep((s) => s + 1)}
                  disabled={busy || (step === 0 && !basicsComplete)}
                >
                  Next
                </button>
              ) : (
                <button key="submit" type="submit" disabled={busy || !canFinish}>
                  Create persona
                </button>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
