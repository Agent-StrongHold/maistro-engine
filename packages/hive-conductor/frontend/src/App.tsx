import { createContext, useContext, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ToastProvider } from "./components/shared";
import Agents from "./pages/Agents";
import AuditLog from "./pages/AuditLog";
import Chat from "./pages/Chat";
import CLI from "./pages/CLI";
import Containers from "./pages/Containers";
import DagBuilder from "./pages/DagBuilder";
import Dashboard from "./pages/Dashboard";
import DesignStudio from "./pages/DesignStudio";
import Install from "./pages/Install";
import Login from "./pages/Login";
import MCP from "./pages/MCP";
import Memory from "./pages/Memory";
import MessageBoard from "./pages/MessageBoard";
import Missions from "./pages/Missions";
import Quotas from "./pages/Quotas";
import Schedules from "./pages/Schedules";
import Settings from "./pages/Settings";
import Setup from "./pages/Setup";
import Skills from "./pages/Skills";
import Topology from "./pages/Topology";

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

  useEffect(() => {
    (async () => {
      try {
        const setupRes = await fetch("/v1/setup/status");
        const setupData = await setupRes.json();
        if (!setupData.setup_complete) {
          setSetupDone(false);
          setReady(true);
          return;
        }
        setSetupDone(true);
        const whoRes = await fetch("/v1/auth/whoami");
        const whoData = await whoRes.json();
        if (whoData.authenticated) {
          setUser(whoData.user);
        }
      } catch {
        setSetupDone(false);
      }
      setReady(true);
    })();
  }, []);

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
    return <Login />;
  }

  return <UserCtx.Provider value={user}>{children}</UserCtx.Provider>;
}

export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/setup" element={<Setup />} />
        <Route
          path="/*"
          element={
            <AuthGuard>
              <Routes>
                <Route path="/" element={<AppShell />}>
                  <Route index element={<Navigate to="dashboard" replace />} />
                  <Route path="dashboard" element={<Dashboard />} />
                  <Route path="chat" element={<Chat />} />
                  <Route path="missions" element={<Missions />} />
                  <Route path="dags" element={<DagBuilder />} />
                  <Route path="schedules" element={<Schedules />} />
                  <Route path="agents" element={<Agents />} />
                  <Route path="skills" element={<Skills />} />
                  <Route path="mcp" element={<MCP />} />
                  <Route path="topology" element={<Topology />} />
                  <Route path="messages" element={<MessageBoard />} />
                  <Route path="quotas" element={<Quotas />} />
                  <Route path="audit" element={<AuditLog />} />
                  <Route path="cli" element={<CLI />} />
                  <Route path="cli/canvas" element={<DesignStudio />} />
                  <Route path="containers" element={<Containers />} />
                  <Route path="memory" element={<Memory />} />
                  <Route path="settings" element={<Settings />} />
                  <Route path="install" element={<Install />} />
                </Route>
              </Routes>
            </AuthGuard>
          }
        />
      </Routes>
    </ToastProvider>
  );
}
