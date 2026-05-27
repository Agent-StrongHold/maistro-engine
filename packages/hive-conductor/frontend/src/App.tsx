import { createContext, useContext, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ToastProvider } from "./components/shared";
import { PocModeProvider, usePmPoc } from "./context/PocMode";
import Agents from "./pages/Agents";
import Fleet from "./pages/Fleet";
import AuditLog from "./pages/AuditLog";
import Chat from "./pages/Chat";
import CLI from "./pages/CLI";
import Containers from "./pages/Containers";
import DagBuilder from "./pages/DagBuilder";
import Dashboard from "./pages/Dashboard";
import DesignStudio from "./pages/DesignStudio";
import Docs from "./pages/Docs";
import Evolution from "./pages/Evolution";
import Login from "./pages/Login";
import MCP from "./pages/MCP";
import Memory from "./pages/Memory";
import MessageBoard from "./pages/MessageBoard";
import Missions from "./pages/Missions";
import OptimizationInbox from "./pages/OptimizationInbox";
import Quotas from "./pages/Quotas";
import Schedules from "./pages/Schedules";
import Settings from "./pages/Settings";
import Credentials from "./pages/Credentials";
import Setup from "./pages/Setup";
import Skills from "./pages/Skills";
import Topology from "./pages/Topology";
import WorkItems from "./pages/WorkItems";

type UserInfo = {
  id: string;
  username: string;
  role: "admin" | "user";
  permissions: string[];
  did: string | null;
  elevated: boolean;
  elevated_until: number | null;
};

const UserCtx = createContext<UserInfo | null>(null);
export const useUser = () => useContext(UserCtx);

function AuthGuard({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [setupDone, setSetupDone] = useState(false);
  const [user, setUser] = useState<UserInfo | null>(null);

  async function loadSession(): Promise<UserInfo | null> {
    const whoRes = await fetch("/v1/auth/whoami", { credentials: "same-origin" });
    const whoData = await whoRes.json();
    if (whoData.authenticated && whoData.user) {
      return whoData.user as UserInfo;
    }
    return null;
  }

  useEffect(() => {
    (async () => {
      try {
        const setupRes = await fetch("/v1/setup/status", { credentials: "same-origin" });
        const setupData = await setupRes.json();
        if (!setupData.setup_complete) {
          setSetupDone(false);
          setReady(true);
          return;
        }
        setSetupDone(true);
        setUser(await loadSession());
      } catch {
        setSetupDone(false);
      }
      setReady(true);
    })();
  }, []);

  async function handleAuthenticated() {
    const next = await loadSession();
    if (next) {
      setUser(next);
    }
  }

  if (!ready) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "#e9e3d3", fontFamily: "var(--hand)", fontSize: 24, color: "var(--pencil)" }}>
        loading hive...
      </div>
    );
  }

  if (!setupDone) {
    return <Setup />;
  }

  if (!user) {
    return <Login onAuthenticated={handleAuthenticated} />;
  }

  return <UserCtx.Provider value={user}>{children}</UserCtx.Provider>;
}

function AppRoutes() {
  const pmPoc = usePmPoc();

  return (
    <Routes>
      <Route path="/setup" element={<Setup />} />
      <Route
        path="/*"
        element={
          <AuthGuard>
            <Routes>
              <Route path="/" element={<AppShell />}>
                <Route index element={<Navigate to={pmPoc ? "chat" : "dashboard"} replace />} />
                {!pmPoc && <Route path="dashboard" element={<Dashboard />} />}
                {pmPoc && <Route path="dashboard" element={<Dashboard />} />}
                <Route path="chat" element={<Chat />} />
                <Route path="missions" element={<Missions />} />
                {!pmPoc && <Route path="dags" element={<DagBuilder />} />}
                {!pmPoc && <Route path="schedules" element={<Schedules />} />}
                <Route path="agents" element={pmPoc ? <Fleet /> : <Agents />} />
                {pmPoc && <Route path="work-items" element={<WorkItems />} />}
                {!pmPoc && <Route path="skills" element={<Skills />} />}
                <Route path="mcp" element={<MCP />} />
                {!pmPoc && <Route path="topology" element={<Topology />} />}
                <Route path="optimizer" element={<OptimizationInbox />} />
                <Route path="optimization-inbox" element={<OptimizationInbox />} />
                {!pmPoc && <Route path="messages" element={<MessageBoard />} />}
                {!pmPoc && <Route path="quotas" element={<Quotas />} />}
                {!pmPoc && <Route path="audit" element={<AuditLog />} />}
                {!pmPoc && <Route path="cli" element={<CLI />} />}
                {!pmPoc && <Route path="cli/canvas" element={<DesignStudio />} />}
                {!pmPoc && <Route path="containers" element={<Containers />} />}
                {!pmPoc && <Route path="docs" element={<Docs />} />}
                {!pmPoc && <Route path="evolution" element={<Evolution />} />}
                {!pmPoc && <Route path="memory" element={<Memory />} />}
                <Route path="settings" element={<Settings />} />
                <Route path="credentials" element={<Credentials />} />
              </Route>
            </Routes>
          </AuthGuard>
        }
      />
    </Routes>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <PocModeProvider>
        <AppRoutes />
      </PocModeProvider>
    </ToastProvider>
  );
}
