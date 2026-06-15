import "./wdpr-parks-next-theme.css"; // 1. Hyperion primitives (--color-*, --theme-color-*)
import "./theme.css";               // 2. App theme (maps --ink, --paper etc → Hyperion)
import "./components.css";           // 3. Shared component patterns
import "./app-shell.css";           // 4. Shell layout
import "./index.css";               // 5. Resets
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { defineCustomElements } from "@wdpr/ra-web-components/loader";
defineCustomElements();
import App from "./App";

// When Vite is built with VITE_BASE_PATH=/pm/, the browser is at /pm/ but
// React Router needs `basename` to strip that prefix before matching nested
// routes (otherwise only the Toast portal at #root > div renders and the
// rest of the app tree is empty). import.meta.env.BASE_URL = "/pm/" with
// our build args; strip the trailing slash for BrowserRouter's basename.
const ROUTER_BASENAME =
  (import.meta.env.BASE_URL || "/").replace(/\/$/, "") || undefined;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter basename={ROUTER_BASENAME}>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
