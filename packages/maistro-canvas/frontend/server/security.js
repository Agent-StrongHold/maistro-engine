import { timingSafeEqual } from "crypto";

const LOOPBACK = new Set(["127.0.0.1", "::1", "localhost"]);

// A plain `Number(env.X || fallback)` turns any non-numeric value into NaN, and
// every `>`/`>=` comparison against NaN is false — so a typo (or "unlimited")
// would silently REMOVE the cap it was meant to set, which is the worst
// possible direction for a misconfiguration to fail. Fall back to the default
// and say so instead.
function positiveIntOr(raw, fallback) {
  if (raw === undefined || raw === "") return fallback;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) {
    console.warn(`Ignoring invalid limit ${JSON.stringify(raw)}; using ${fallback}`);
    return fallback;
  }
  return Math.floor(n);
}

export function resolveSecurityConfig(env = process.env) {
  const host = env.CANVAS_HOST || "127.0.0.1";
  const token = env.CANVAS_API_TOKEN || "";
  const origins = (env.CANVAS_ALLOWED_ORIGINS ||
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174")
    .split(",").map(s => s.trim()).filter(Boolean);
  const bodyLimit = env.CANVAS_BODY_LIMIT || "200mb";
  const maxExportPages = positiveIntOr(env.CANVAS_MAX_EXPORT_PAGES, 400);
  const maxConcurrentExports = positiveIntOr(env.CANVAS_MAX_CONCURRENT_EXPORTS, 2);
  const allowTruncate = env.CANVAS_ALLOW_TRUNCATE === "true";
  const exposed = !LOOPBACK.has(host);
  if (exposed && !token) {
    throw new Error(
      "CANVAS_HOST is not loopback but CANVAS_API_TOKEN is unset. This server " +
      "proxies operator LiteLLM/Azure/Gemini credentials and spawns python3 per " +
      "request; refusing to listen on a routable interface without a token."
    );
  }
  return { host, token, origins, bodyLimit, maxExportPages, maxConcurrentExports, allowTruncate, exposed };
}

export function isOriginAllowed(origin, origins) {
  return !origin || origins.includes(origin);   // no Origin == non-browser caller
}

// Constant-time compare. `!==` leaks the length of the shared prefix, and this
// is the only credential guarding a server that holds operator LLM keys.
function tokensMatch(supplied, expected) {
  const a = Buffer.from(supplied);
  const b = Buffer.from(expected);
  // timingSafeEqual throws on a length mismatch, so the length check has to
  // happen first; length alone is not the secret.
  return a.length === b.length && timingSafeEqual(a, b);
}

export function requireToken(config) {
  return (req, res, next) => {
    if (!config.token) return next();           // loopback-only mode
    const header = req.get("authorization") || "";
    const supplied = header.startsWith("Bearer ") ? header.slice(7) : req.get("x-canvas-token") || "";
    if (!tokensMatch(supplied, config.token)) return res.status(401).json({ error: "unauthorized" });
    next();
  };
}
