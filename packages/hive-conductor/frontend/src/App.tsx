import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import Agents from "./pages/Agents";
import Chat from "./pages/Chat";
import CLI from "./pages/CLI";
import Containers from "./pages/Containers";
import DesignStudio from "./pages/DesignStudio";
import Install from "./pages/Install";
import MCP from "./pages/MCP";
import Memory from "./pages/Memory";
import Missions from "./pages/Missions";
import Schedules from "./pages/Schedules";
import Settings from "./pages/Settings";
import Skills from "./pages/Skills";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<AppShell />}>
        <Route index element={<Navigate to="chat" replace />} />
        <Route path="chat" element={<Chat />} />
        <Route path="missions" element={<Missions />} />
        <Route path="schedules" element={<Schedules />} />
        <Route path="skills" element={<Skills />} />
        <Route path="agents" element={<Agents />} />
        <Route path="mcp" element={<MCP />} />
        <Route path="cli" element={<CLI />} />
        <Route path="cli/canvas" element={<DesignStudio />} />
        <Route path="containers" element={<Containers />} />
        <Route path="memory" element={<Memory />} />
        <Route path="settings" element={<Settings />} />
        <Route path="install" element={<Install />} />
      </Route>
    </Routes>
  );
}
