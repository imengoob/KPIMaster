/**
 * AssistantStats — small observability dashboard for the AI Assistant.
 *
 * Fetches GET /api/v1/assistant/stats and renders four cards: total
 * questions answered, "no data found" rate, average Gemini latency, and a
 * breakdown of questions by detected intent.
 *
 * Drop this into any existing page/route (e.g. an admin or settings page).
 * It is a self-contained component — only depends on fetch + your existing
 * auth token in localStorage, same pattern as useAssistant.ts.
 */
import { useEffect, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

interface Stats {
  total_questions: number;
  no_data_count: number;
  no_data_rate: number;
  error_count: number;
  avg_gemini_latency_ms: number;
  questions_by_intent: Record<string, number>;
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("kpimaster.authToken");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-border bg-card px-5 py-4 flex flex-col gap-1">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold text-foreground">{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

export default function AssistantStats() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const res = await fetch(`${API_BASE}/api/v1/assistant/stats`, { headers: authHeaders() });
        if (!res.ok) throw new Error(`Erreur serveur (${res.status})`);
        const data: Stats = await res.json();
        if (!cancelled) setStats(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load stats");
      }
    }

    load();
    const interval = setInterval(load, 15000); // refresh every 15s for a live demo feel
    return () => { cancelled = true; clearInterval(interval); };
  }, []);

  if (error) {
    return <p className="text-sm text-destructive">Could not load assistant stats: {error}</p>;
  }
  if (!stats) {
    return <p className="text-sm text-muted-foreground">Loading assistant stats…</p>;
  }

  const topIntents = Object.entries(stats.questions_by_intent)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-foreground">AI Assistant — Observability</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Questions answered" value={String(stats.total_questions)} />
        <StatCard
          label="No-data rate"
          value={`${(stats.no_data_rate * 100).toFixed(0)}%`}
          sub={`${stats.no_data_count} empty answers`}
        />
        <StatCard
          label="Avg. Gemini latency"
          value={`${stats.avg_gemini_latency_ms.toFixed(0)} ms`}
        />
        <StatCard label="Errors" value={String(stats.error_count)} />
      </div>

      {topIntents.length > 0 && (
        <div className="rounded-2xl border border-border bg-card px-5 py-4">
          <p className="text-xs text-muted-foreground mb-2">Questions by intent</p>
          <div className="space-y-1.5">
            {topIntents.map(([intent, count]) => (
              <div key={intent} className="flex items-center gap-2 text-sm">
                <span className="w-24 shrink-0 capitalize text-foreground">{intent}</span>
                <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    className="h-full bg-primary"
                    style={{ width: `${(count / stats.total_questions) * 100}%` }}
                  />
                </div>
                <span className="w-8 text-right text-muted-foreground">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}