/** Relative API base (Vite proxies /v1 and /health in dev). */
export const API_BASE = "";

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { credentials: "same-origin" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export async function apiDelete<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    credentials: "same-origin",
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { credentials: "same-origin", ...init });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json() as Promise<T>;
}
