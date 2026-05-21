# HiveConductor (upstream)

The Git remote `https://github.com/BlakeMatthews-dev/HiveConductor.git` currently
has **no commits**, and a local checkout at `/Users/blake.matthews/HiveConductor`
contained only `.git` — there was **no file tree** to snapshot into this folder.

**Shipped replacement:** a **Hive Conductor–style** static UI lives inside
**maistro-engine** at:

`packages/maistro-server/src/maistro_server/static/hive/`

and is served by the FastAPI app at **`/conductor/`** (see
`packages/maistro-server/README.md`). The existing multi-page UI remains at **`/dashboard/`**.

When the HiveConductor repo gains a real web client, copy it here for diffing:

```bash
cd /Users/blake.matthews/maistro-engine
cp -R /path/to/HiveConductor/web potential-dead-code/code-worth-implementing-from-HiveConductor/web
```

Then port routes into `static/hive/` or a proper SPA build wired in
`maistro_server/main.py`.
