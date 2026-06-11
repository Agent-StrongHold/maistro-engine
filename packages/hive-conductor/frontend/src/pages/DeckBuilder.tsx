import { useState, useRef, useCallback, useEffect } from "react";

const C = { bg: "#0a0914", card: "#11101e", border: "rgba(196,166,97,0.14)", gold: "#c4a661", ink: "#f3f0fb", muted: "#8b83a8", dim: "#5a5478", acc: "#a78bfa" };

interface Slide { id: string; html: string; notes: string; }

function uid() { return Math.random().toString(36).slice(2, 10); }

const BLANK_SLIDE: () => Slide = () => ({ id: uid(), html: "<h1>Title</h1><p>Content</p>", notes: "" });

const TEMPLATES = [
  { name: "Title Slide", html: '<h1 style="font-size:3rem;font-family:Georgia,serif">Your Title Here</h1><p style="font-size:1.2rem;opacity:0.7;margin-top:1rem">Subtitle or author</p>' },
  { name: "Bullet Points", html: '<h2>Key Points</h2><ul style="font-size:1.1rem;line-height:2.2;margin-top:1rem"><li>First point</li><li>Second point</li><li>Third point</li></ul>' },
  { name: "Big Number", html: '<div style="text-align:center"><p style="font-size:5rem;font-weight:800;color:#a78bfa">42%</p><p style="font-size:1.2rem;opacity:0.7;margin-top:0.5rem">Improvement over baseline</p></div>' },
  { name: "Quote", html: '<blockquote style="font-size:1.6rem;font-style:italic;border-left:4px solid #a78bfa;padding-left:1.5rem;max-width:50ch;line-height:1.6">"The best way to predict the future is to invent it."</blockquote><p style="margin-top:1rem;opacity:0.6">— Alan Kay</p>' },
  { name: "Two Columns", html: '<h2>Comparison</h2><div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;margin-top:1.5rem"><div><h3 style="color:#a78bfa">Before</h3><p>Manual process, slow iteration, error-prone</p></div><div><h3 style="color:#c4a661">After</h3><p>Automated, fast feedback, consistent quality</p></div></div>' },
  { name: "Image + Text", html: '<div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;align-items:center"><div style="background:rgba(167,139,250,0.1);border-radius:12px;height:250px;display:flex;align-items:center;justify-content:center;font-size:0.8rem;color:#8b83a8">[Image placeholder]</div><div><h2>Visual Context</h2><p style="margin-top:0.5rem;line-height:1.6">Describe what the image shows and why it matters to your narrative.</p></div></div>' },
  { name: "Timeline", html: '<h2>Timeline</h2><div style="margin-top:1.5rem;display:flex;flex-direction:column;gap:1rem"><div style="display:flex;gap:1rem;align-items:baseline"><span style="color:#a78bfa;font-weight:700;min-width:80px">Q1</span><span>Discovery & research phase</span></div><div style="display:flex;gap:1rem;align-items:baseline"><span style="color:#a78bfa;font-weight:700;min-width:80px">Q2</span><span>Build & validate MVP</span></div><div style="display:flex;gap:1rem;align-items:baseline"><span style="color:#a78bfa;font-weight:700;min-width:80px">Q3</span><span>Production launch</span></div></div>' },
  { name: "Thank You", html: '<div style="text-align:center"><h1 style="font-size:2.5rem;font-family:Georgia,serif">Thank You</h1><p style="margin-top:1rem;opacity:0.6;font-size:1.1rem">Questions?</p></div>' },
];

function DeckChat({ slides, onUpdateSlides, activeIdx }: { slides: Slide[]; onUpdateSlides: (s: Slide[]) => void; activeIdx: number }) {
  const [value, setValue] = useState("");
  const [msgs, setMsgs] = useState<{ role: string; content: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [msgs]);

  const submit = async () => {
    if (!value.trim() || loading) return;
    const userMsg = value.trim();
    setValue("");
    setMsgs(m => [...m, { role: "user", content: userMsg }]);
    setLoading(true);
    try {
      const deckContext = slides.map((s, i) => `Slide ${i + 1}: ${s.html.replace(/<[^>]+>/g, " ").slice(0, 100)}`).join("\n");
      const r = await fetch("/v1/chat/complete", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [
            { role: "system", content: `You are a deck-building assistant. Help create stunning presentation slides.
Current deck has ${slides.length} slides, active slide is #${activeIdx + 1}.
${deckContext}

When generating slides, respond with HTML content wrapped in <slide> tags. Each <slide>...</slide> becomes one slide.
Use clean semantic HTML: h1, h2, p, ul/li, blockquote, div with inline styles for layout.
Style tips: use font-family:Georgia,serif for headings, keep text concise, use color:#a78bfa for accents, max 6 bullet points per slide.
If editing existing slides, output the full replacement HTML in <slide index="N">...</slide> where N is 1-based.` },
            ...msgs.slice(-6),
            { role: "user", content: userMsg },
          ],
        }),
      });
      const data = await r.json();
      const reply = data?.choices?.[0]?.message?.content || data?.content || "No response";
      setMsgs(m => [...m, { role: "assistant", content: reply }]);

      // Parse <slide> tags from response and apply them
      const slideMatches = [...reply.matchAll(/<slide(?:\s+index="(\d+)")?>([\s\S]*?)<\/slide>/gi)];
      if (slideMatches.length > 0) {
        let newSlides = [...slides];
        for (const match of slideMatches) {
          const idx = match[1] ? parseInt(match[1]) - 1 : -1;
          const html = match[2].trim();
          if (idx >= 0 && idx < newSlides.length) {
            newSlides[idx] = { ...newSlides[idx], html };
          } else {
            newSlides.push({ id: uid(), html, notes: "" });
          }
        }
        onUpdateSlides(newSlides);
      }
    } catch {
      setMsgs(m => [...m, { role: "assistant", content: "Connection error — check that the backend is running." }]);
    }
    setLoading(false);
  };

  return (
    <div style={{ borderTop: `1px solid ${C.border}`, marginTop: "1rem", paddingTop: "0.75rem" }}>
      {msgs.length > 0 && (
        <div ref={ref} style={{ maxHeight: 150, overflowY: "auto", marginBottom: 8, display: "flex", flexDirection: "column", gap: 4 }}>
          {msgs.slice(-6).map((m, i) => (
            <div key={i} style={{ fontSize: "0.65rem", color: m.role === "user" ? C.gold : C.muted, lineHeight: 1.4 }}>
              <span style={{ fontWeight: 600 }}>{m.role === "user" ? "You" : "✦"}: </span>
              {m.content.replace(/<slide[^>]*>[\s\S]*?<\/slide>/gi, "[slide generated]").slice(0, 200)}
            </div>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 6 }}>
        <input value={value} onChange={e => setValue(e.target.value)}
          onKeyDown={e => e.key === "Enter" && submit()}
          placeholder="✦ Describe slides to generate, or ask to edit..."
          style={{ flex: 1, background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, padding: "8px 12px", color: C.ink, fontSize: "0.72rem", outline: "none" }} />
        <button onClick={submit} disabled={loading} style={{ padding: "8px 14px", borderRadius: 8, border: "none", background: C.acc, color: "#fff", fontSize: "0.68rem", fontWeight: 600, cursor: "pointer", opacity: loading ? 0.5 : 1 }}>
          {loading ? "..." : "Generate"}
        </button>
      </div>
    </div>
  );
}

export default function DeckBuilder() {
  const [slides, setSlides] = useState<Slide[]>([BLANK_SLIDE()]);
  const [active, setActive] = useState(0);
  const [title, setTitle] = useState("Untitled Deck");
  const [presenting, setPresenting] = useState(false);
  const previewRef = useRef<HTMLDivElement>(null);

  const updateSlide = useCallback((idx: number, html: string) => {
    setSlides(s => s.map((sl, i) => i === idx ? { ...sl, html } : sl));
  }, []);

  const addSlide = () => { setSlides(s => [...s, BLANK_SLIDE()]); setActive(slides.length); };
  const removeSlide = (idx: number) => { if (slides.length <= 1) return; setSlides(s => s.filter((_, i) => i !== idx)); setActive(Math.max(0, idx - 1)); };
  const moveSlide = (from: number, dir: number) => {
    const to = from + dir;
    if (to < 0 || to >= slides.length) return;
    setSlides(s => { const n = [...s]; [n[from], n[to]] = [n[to], n[from]]; return n; });
    setActive(to);
  };

  const exportHTML = () => {
    const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${title}</title><style>
*{margin:0;padding:0;box-sizing:border-box}html,body{height:100%;overflow:hidden;font-family:system-ui,sans-serif;background:#0a0914;color:#f3f0fb}
.deck{height:100vh;overflow-y:scroll;scroll-snap-type:y mandatory}.slide{height:100vh;scroll-snap-align:start;display:flex;align-items:center;justify-content:center;padding:4rem;flex-direction:column}
.slide h1{font-size:3rem;margin-bottom:1rem;font-family:Georgia,serif}.slide h2{font-size:2rem;margin-bottom:0.75rem}.slide p{font-size:1.25rem;opacity:0.8;max-width:60ch;line-height:1.6}
.slide ul,.slide ol{font-size:1.1rem;text-align:left;line-height:2}</style></head><body><div class="deck">
${slides.map(s => `<div class="slide">${s.html}</div>`).join("\n")}</div></body></html>`;
    const blob = new Blob([html], { type: "text/html" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${title.replace(/\s+/g, "-")}.html`; a.click();
  };

  const exportPDF = () => { window.print(); };

  // Presentation mode
  if (presenting) {
    return (
      <div style={{ position: "fixed", inset: 0, background: C.bg, zIndex: 9999, overflow: "hidden" }}>
        <div style={{ height: "100vh", overflowY: "scroll", scrollSnapType: "y mandatory" }}>
          {slides.map((s, i) => (
            <div key={s.id} style={{ height: "100vh", scrollSnapAlign: "start", display: "flex", alignItems: "center", justifyContent: "center", padding: "4rem", flexDirection: "column" }}
              dangerouslySetInnerHTML={{ __html: s.html }} />
          ))}
        </div>
        <button onClick={() => setPresenting(false)} style={{ position: "fixed", top: 12, right: 12, background: "rgba(0,0,0,0.6)", border: "none", color: C.ink, padding: "6px 12px", borderRadius: 6, cursor: "pointer", fontSize: "0.7rem" }}>Exit (Esc)</button>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.ink, fontFamily: "'Inter', -apple-system, system-ui, sans-serif", padding: "1.5rem 2rem" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <input value={title} onChange={e => setTitle(e.target.value)} style={{ background: "transparent", border: "none", color: C.ink, fontSize: "1.2rem", fontWeight: 700, fontFamily: "Georgia, serif", outline: "none", width: 300 }} />
          <span style={{ fontSize: "0.6rem", color: C.muted }}>{slides.length} slides</span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <button onClick={() => setPresenting(true)} style={{ padding: "5px 12px", borderRadius: 6, border: "none", background: C.acc, color: "#fff", fontSize: "0.68rem", fontWeight: 600, cursor: "pointer" }}>Present</button>
          <button onClick={exportHTML} style={{ padding: "5px 12px", borderRadius: 6, border: `1px solid ${C.border}`, background: "transparent", color: C.ink, fontSize: "0.68rem", cursor: "pointer" }}>Export HTML</button>
          <button onClick={exportPDF} style={{ padding: "5px 12px", borderRadius: 6, border: `1px solid ${C.border}`, background: "transparent", color: C.ink, fontSize: "0.68rem", cursor: "pointer" }}>Print/PDF</button>
        </div>
      </div>

      <div style={{ display: "flex", gap: "1rem" }}>
        {/* Slide list */}
        <div style={{ width: 140, flexShrink: 0 }}>
          {slides.map((s, i) => (
            <div key={s.id} onClick={() => setActive(i)} style={{ padding: "8px 10px", borderRadius: 8, marginBottom: 4, cursor: "pointer", border: `1px solid ${i === active ? C.acc : C.border}`, background: i === active ? "rgba(167,139,250,0.08)" : C.card, fontSize: "0.65rem", color: i === active ? C.ink : C.muted }}>
              Slide {i + 1}
            </div>
          ))}
          <button onClick={addSlide} style={{ width: "100%", padding: "6px", borderRadius: 6, border: `1px dashed ${C.border}`, background: "transparent", color: C.muted, fontSize: "0.65rem", cursor: "pointer", marginTop: 4 }}>+ Add Slide</button>
        </div>

        {/* Editor */}
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
            <button onClick={() => moveSlide(active, -1)} disabled={active === 0} style={{ background: "none", border: "none", color: active === 0 ? C.dim : C.muted, cursor: "pointer", fontSize: "0.7rem" }}>◀ Move</button>
            <button onClick={() => moveSlide(active, 1)} disabled={active === slides.length - 1} style={{ background: "none", border: "none", color: active === slides.length - 1 ? C.dim : C.muted, cursor: "pointer", fontSize: "0.7rem" }}>Move ▶</button>
            <button onClick={() => removeSlide(active)} disabled={slides.length <= 1} style={{ background: "none", border: "none", color: slides.length <= 1 ? C.dim : C.danger ?? "#e87c7c", cursor: "pointer", fontSize: "0.7rem", marginLeft: "auto" }}>Delete</button>
          </div>
          {/* Editable slide preview */}
          <div ref={previewRef} contentEditable suppressContentEditableWarning
            onBlur={e => updateSlide(active, e.currentTarget.innerHTML)}
            dangerouslySetInnerHTML={{ __html: slides[active]?.html || "" }}
            style={{ minHeight: 400, background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: "3rem", display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", fontSize: "1.1rem", lineHeight: 1.6, outline: "none" }} />
          {/* Speaker notes */}
          <textarea value={slides[active]?.notes || ""} onChange={e => setSlides(s => s.map((sl, i) => i === active ? { ...sl, notes: e.target.value } : sl))}
            placeholder="Speaker notes..."
            style={{ width: "100%", marginTop: 8, minHeight: 60, background: C.card, border: `1px solid ${C.border}`, borderRadius: 8, padding: "8px 12px", color: C.muted, fontSize: "0.72rem", resize: "vertical", outline: "none", fontFamily: "inherit" }} />

          {/* Templates */}
          <div style={{ marginTop: 12 }}>
            <div style={{ fontSize: "0.6rem", color: C.muted, marginBottom: 6, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>Templates</div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {TEMPLATES.map(t => (
                <button key={t.name} onClick={() => { setSlides(s => [...s, { id: uid(), html: t.html, notes: "" }]); setActive(slides.length); }}
                  style={{ padding: "4px 10px", borderRadius: 6, border: `1px solid ${C.border}`, background: "transparent", color: C.muted, fontSize: "0.6rem", cursor: "pointer" }}>
                  {t.name}
                </button>
              ))}
            </div>
          </div>

          {/* AI Assistant */}
          <DeckChat slides={slides} onUpdateSlides={setSlides} activeIdx={active} />
        </div>
      </div>
    </div>
  );
}
