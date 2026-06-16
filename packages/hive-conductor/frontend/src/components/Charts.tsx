import { useEffect, useRef } from "react";
import { Chart, registerables } from "chart.js";

Chart.register(...registerables);

const PALETTE = [
  "var(--color-purple-500, #7c5cfc)",
  "var(--color-blue-500, #3b82f6)",
  "var(--color-green-500, #2da563)",
  "var(--color-gold-500, #d4a017)",
  "var(--color-orange-500, #e67e22)",
  "var(--color-pink-500, #ec4899)",
  "var(--color-aqua-500, #06b6d4)",
  "var(--color-violet-500, #a855f7)",
  "var(--color-lime-500, #84cc16)",
  "var(--color-red-500, #e74c3c)",
];

// Resolve CSS vars to actual colors for Chart.js
function resolveColor(c: string): string {
  if (!c.startsWith("var(")) return c;
  const fallback = c.match(/,\s*([^)]+)\)/)?.[1]?.trim();
  return fallback || "#7c5cfc";
}

// ─── Donut Chart ───
export function DonutChart({ data, centerLabel }: { data: { labels: string[]; values: number[] }; centerLabel?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: "doughnut",
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          backgroundColor: PALETTE.slice(0, data.values.length).map(resolveColor),
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "65%",
        plugins: {
          legend: { position: "right", labels: { color: "var(--ink, #17132b)", font: { size: 11 } } },
        },
      },
    });
    return () => { chartRef.current?.destroy(); };
  }, [data]);

  return (
    <div style={{ position: "relative", height: "100%", minHeight: 160 }}>
      <canvas ref={ref} />
      {centerLabel && <div style={{ position: "absolute", top: "50%", left: "35%", transform: "translate(-50%, -50%)", textAlign: "center", fontSize: "1.5rem", fontWeight: 800, color: "var(--ink)" }}>{centerLabel}</div>}
    </div>
  );
}

// ─── Vertical Bar Chart (ColumnBars) ───
export function ColumnChart({ data, color }: { data: { labels: string[]; values: number[] }; color?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          backgroundColor: resolveColor(color || PALETTE[0]),
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: "var(--muted, #6e6885)", font: { size: 10 } } },
          y: { grid: { color: "rgba(0,0,0,0.05)" }, ticks: { color: "var(--muted, #6e6885)", font: { size: 10 } } },
        },
      },
    });
    return () => { chartRef.current?.destroy(); };
  }, [data, color]);

  return <div style={{ height: "100%", minHeight: 160 }}><canvas ref={ref} /></div>;
}

// ─── Line Chart ───
export function LineChart({ data, color }: { data: { labels: string[]; values: number[] }; color?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    const c = resolveColor(color || PALETTE[0]);
    chartRef.current = new Chart(ref.current, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          borderColor: c,
          backgroundColor: c + "20",
          fill: true,
          tension: 0.3,
          pointRadius: 3,
          pointBackgroundColor: c,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: "var(--muted, #6e6885)", font: { size: 10 } } },
          y: { grid: { color: "rgba(0,0,0,0.05)" }, ticks: { color: "var(--muted, #6e6885)", font: { size: 10 } } },
        },
      },
    });
    return () => { chartRef.current?.destroy(); };
  }, [data, color]);

  return <div style={{ height: "100%", minHeight: 160 }}><canvas ref={ref} /></div>;
}

// ─── Stacked Bar (SegmentedBar/StackedBarRows) ───
export function StackedBarChart({ data }: { data: { labels: string[]; datasets: { label: string; values: number[]; color?: string }[] } }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: data.datasets.map((ds, i) => ({
          label: ds.label,
          data: ds.values,
          backgroundColor: resolveColor(ds.color || PALETTE[i % PALETTE.length]),
          borderRadius: 2,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        plugins: { legend: { position: "bottom", labels: { color: "var(--ink, #17132b)", font: { size: 10 } } } },
        scales: {
          x: { stacked: true, grid: { color: "rgba(0,0,0,0.05)" }, ticks: { color: "var(--muted, #6e6885)", font: { size: 10 } } },
          y: { stacked: true, grid: { display: false }, ticks: { color: "var(--ink, #17132b)", font: { size: 11 } } },
        },
      },
    });
    return () => { chartRef.current?.destroy(); };
  }, [data]);

  return <div style={{ height: "100%", minHeight: 180 }}><canvas ref={ref} /></div>;
}

// ─── Horizontal Funnel (FunnelStages) ───
export function FunnelChart({ data }: { data: { labels: string[]; values: number[] } }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current?.destroy();
    chartRef.current = new Chart(ref.current, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [{
          data: data.values,
          backgroundColor: data.values.map((_, i) => resolveColor(PALETTE[i % PALETTE.length])),
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: "rgba(0,0,0,0.05)" }, ticks: { color: "var(--muted, #6e6885)", font: { size: 10 } } },
          y: { grid: { display: false }, ticks: { color: "var(--ink, #17132b)", font: { size: 11 } } },
        },
      },
    });
    return () => { chartRef.current?.destroy(); };
  }, [data]);

  return <div style={{ height: "100%", minHeight: 160 }}><canvas ref={ref} /></div>;
}
