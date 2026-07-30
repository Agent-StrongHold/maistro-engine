import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiGet, apiPost } from "../lib/api";

export type Workspace = {
  id: string;
  persona_template_id: string;
  name: string;
  theme_id: string;
  voice_tone_override: string | null;
  active: boolean;
};

type CreateWorkspaceInput = {
  name: string;
  persona_template_id: string;
};

type WorkspaceCtxValue = {
  workspaces: Workspace[];
  activeWorkspaceId: string | null;
  activeWorkspace: Workspace | null;
  ready: boolean;
  selectWorkspace: (id: string) => void;
  createWorkspace: (input: CreateWorkspaceInput) => Promise<Workspace>;
  refresh: () => Promise<void>;
};

const noop = () => {};

const WorkspaceCtx = createContext<WorkspaceCtxValue>({
  workspaces: [],
  activeWorkspaceId: null,
  activeWorkspace: null,
  ready: false,
  selectWorkspace: noop,
  createWorkspace: () => Promise.reject(new Error("WorkspaceProvider not mounted")),
  refresh: () => Promise.resolve(),
});

const ACTIVE_WORKSPACE_KEY = "hive_active_workspace_id";

/** A user's live Workspace tabs (Persona/Workspace system). Mount this only
 * once authenticated -- GET /v1/workspaces requires a session. */
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState<string | null>(() =>
    localStorage.getItem(ACTIVE_WORKSPACE_KEY),
  );
  const [ready, setReady] = useState(false);

  async function refresh() {
    try {
      const list = await apiGet<Workspace[]>("/v1/workspaces");
      setWorkspaces(list);
      setActiveWorkspaceId((current) => {
        if (current && list.some((w) => w.id === current)) return current;
        return list[0]?.id ?? null;
      });
    } catch {
      // No workspaces yet, or the account can't reach the route -- the tab
      // bar degrades to "no tabs" rather than breaking the app shell.
      setWorkspaces([]);
    } finally {
      setReady(true);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (activeWorkspaceId) {
      localStorage.setItem(ACTIVE_WORKSPACE_KEY, activeWorkspaceId);
    } else {
      localStorage.removeItem(ACTIVE_WORKSPACE_KEY);
    }
  }, [activeWorkspaceId]);

  const activeWorkspace = workspaces.find((w) => w.id === activeWorkspaceId) ?? null;

  useEffect(() => {
    const themeId = activeWorkspace?.theme_id;
    if (themeId && themeId !== "default") {
      document.documentElement.dataset.theme = themeId;
    } else {
      delete document.documentElement.dataset.theme;
    }
  }, [activeWorkspace?.theme_id]);

  async function createWorkspace(input: CreateWorkspaceInput): Promise<Workspace> {
    const created = await apiPost<Workspace>("/v1/workspaces", input);
    setWorkspaces((prev) => [...prev, created]);
    setActiveWorkspaceId(created.id);
    return created;
  }

  function selectWorkspace(id: string) {
    setActiveWorkspaceId(id);
  }

  return (
    <WorkspaceCtx.Provider
      value={{
        workspaces,
        activeWorkspaceId,
        activeWorkspace,
        ready,
        selectWorkspace,
        createWorkspace,
        refresh,
      }}
    >
      {children}
    </WorkspaceCtx.Provider>
  );
}

export function useWorkspaces(): WorkspaceCtxValue {
  return useContext(WorkspaceCtx);
}
