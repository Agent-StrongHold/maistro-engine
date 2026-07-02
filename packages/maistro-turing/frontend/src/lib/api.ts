// Thin client for the Turing live API. Used by the hydrated React islands
// (dashboard, feed, chat, admin). Credentials: human session cookie, so all
// requests are sent with `credentials: "include"`.

export const API_BASE: string =
  (import.meta as any).env?.PUBLIC_TURING_API ?? "http://localhost:8120";

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export interface Snapshot {
  self_id: string;
  mood: { valence: number; arousal: number; focus: number; updated_at: string };
  personality: Record<string, Record<string, number>>;
  drives: {
    creative_urge: number;
    curiosity: number;
    diligence: number;
    restlessness: number;
  };
}

export interface Artifact {
  artifact_id: string;
  self_id: string;
  kind: string;
  title: string;
  body: string;
  created_at: string;
}

export interface FeedPage {
  items: Artifact[];
  total: number;
  offset: number;
  limit: number;
}

export const api = {
  login: (username: string, password: string) =>
    req<{ role: string }>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  whoami: () => req<{ authenticated: boolean; role?: string }>("/v1/auth/whoami"),
  snapshot: () => req<Snapshot>("/v1/state/snapshot"),
  feed: (offset = 0, limit = 20, kind?: string) =>
    req<FeedPage>(
      `/v1/feed?offset=${offset}&limit=${limit}${kind ? `&kind=${kind}` : ""}`,
    ),
  chat: (message: string, session_id?: string) =>
    req<{ session_id: string; reply: string }>("/v1/chat", {
      method: "POST",
      body: JSON.stringify({ message, session_id }),
    }),
  patchMood: (fields: Partial<Snapshot["mood"]>) =>
    req("/v1/admin/mood", { method: "PATCH", body: JSON.stringify(fields) }),
  patchFacet: (facet_id: string, score: number) =>
    req("/v1/admin/facet", {
      method: "PATCH",
      body: JSON.stringify({ facet_id, score }),
    }),
};
