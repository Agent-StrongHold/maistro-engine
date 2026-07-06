import { defineCollection, z } from "astro:content";

// Producer artifacts are fetched from the live API at BUILD time and rendered as
// static HTML pages (SSG). The loader hits GET /v1/feed and pages every result
// in, so each artifact gets its own statically-generated page under /feed/[id].
//
// GAP: a build-time fetch needs the API reachable during `astro build` and a
// service/admin credential. In dev with an empty feed this yields zero pages;
// CI builds would point PUBLIC_TURING_API at a snapshot/seed API. The
// alternative (a checked-in Markdown content dir) is left out deliberately so
// the source of truth stays the producer pipeline, not duplicated files.
const artifacts = defineCollection({
  loader: async () => {
    const base = import.meta.env.PUBLIC_TURING_API ?? "http://localhost:8120";
    const key = import.meta.env.TURING_BUILD_KEY ?? "";
    try {
      const all: any[] = [];
      let offset = 0;
      const limit = 100;
      while (true) {
        const res = await fetch(`${base}/v1/feed?offset=${offset}&limit=${limit}`, {
          headers: key ? { Authorization: `Bearer ${key}` } : {},
        });
        if (!res.ok) break;
        const page = await res.json();
        for (const item of page.items) all.push({ id: item.artifact_id, ...item });
        offset += limit;
        if (offset >= page.total) break;
      }
      return all;
    } catch {
      // Build proceeds with no artifact pages if the API is unreachable.
      return [];
    }
  },
  schema: z.object({
    artifact_id: z.string(),
    self_id: z.string(),
    kind: z.string(),
    title: z.string(),
    body: z.string(),
    created_at: z.string(),
  }),
});

export const collections = { artifacts };
