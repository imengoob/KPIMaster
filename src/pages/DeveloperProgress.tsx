import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import DashboardLayout from "@/components/DashboardLayout";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";
import EmptyProjectState from "@/components/EmptyProjectState";
import { isDeveloperUser, useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { getApiDateRange } from "@/lib/dateRange";
import type { PlatformFilter } from "@/lib/platforms";
import { developerApi } from "@/services/api/developers";
import { engagementApi } from "@/services/api/engagements";
import { cn } from "@/lib/utils";
import type {
  BackendTeamKPIReport,
  BackendTeamMemberSummary,
  BackendDeveloperKPIReport,
  BackendTaskTypeProfile,
  BackendTeamWarningSignal,
  BackendTrelloMemberCandidate,
} from "@/services/api/types";
import {
  CheckCircle2, AlertTriangle, TrendingDown, Clock, Target, Shield,
  MessageSquare, ChevronDown, ChevronUp, Zap, BarChart3, Users,
  AlertCircle, Bug, Wrench, Search, GitPullRequest, HelpCircle, BriefcaseBusiness
} from "lucide-react";

// ── Status config ─────────────────────────────────────────────────────────────

const STATUS = {
  "on-track": {
    label: "On Track", Icon: CheckCircle2,
    pill: "bg-emerald-500/15 text-emerald-500 ring-1 ring-emerald-500/30",
    border: "border-l-emerald-500",
  },
  "at-risk": {
    label: "At Risk", Icon: AlertTriangle,
    pill: "bg-amber-500/15 text-amber-500 ring-1 ring-amber-500/30",
    border: "border-l-amber-500",
  },
  "behind": {
    label: "Behind", Icon: TrendingDown,
    pill: "bg-rose-500/15 text-rose-500 ring-1 ring-rose-500/30",
    border: "border-l-rose-500",
  },
} as const;

const SEVERITY = {
  critical: { bar: "bg-rose-500/10 border-rose-500/30 text-rose-500", dot: "bg-rose-500" },
  warning:  { bar: "bg-amber-500/10 border-amber-500/30 text-amber-500", dot: "bg-amber-500" },
  info:     { bar: "bg-sky-500/10 border-sky-500/30 text-sky-500", dot: "bg-sky-500" },
} as const;

const TASK_ICONS: Record<string, { Icon: React.ElementType; color: string }> = {
  feature:       { Icon: Zap,           color: "bg-violet-500" },
  bug:           { Icon: Bug,           color: "bg-rose-500"   },
  refactor:      { Icon: Wrench,        color: "bg-amber-500"  },
  investigation: { Icon: Search,        color: "bg-sky-500"    },
  task:          { Icon: GitPullRequest, color: "bg-emerald-500"},
};

// ── Formatters ────────────────────────────────────────────────────────────────

const fmtH = (h: number | null | undefined) => {
  if (h == null) return "—";
  return h < 24 ? `${h.toFixed(1)}h` : `${(h / 24).toFixed(1)}d`;
};
const fmtPct = (v: number | null | undefined) =>
  v == null ? "—" : `${(v * 100).toFixed(0)}%`;
const fmtProvider = (providers: string[] | undefined) =>
  providers?.length ? providers.map(p => p === "microsoft" ? "Planner" : p[0].toUpperCase() + p.slice(1)).join(", ") : "Provider pending";

// ── Shared small components ───────────────────────────────────────────────────

function Avatar({ name }: { name: string }) {
  const initials = name.split(" ").map(p => p[0]).join("").slice(0, 2).toUpperCase();
  const colors = [
    "from-cyan-500 to-blue-600", "from-violet-500 to-purple-600",
    "from-emerald-500 to-teal-600", "from-orange-500 to-rose-600",
    "from-pink-500 to-fuchsia-600", "from-amber-500 to-yellow-600",
  ];
  return (
    <div className={cn(
      "flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br text-xs font-bold text-white shadow-sm",
      colors[name.charCodeAt(0) % colors.length],
    )}>
      {initials}
    </div>
  );
}

function StatusPill({ status }: { status: keyof typeof STATUS }) {
  const cfg = STATUS[status] || STATUS["on-track"];
  const { label, Icon, pill } = cfg;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium shrink-0", pill)}>
      <Icon className="h-3 w-3" />{label}
    </span>
  );
}

function Ring({ pct, size = 48 }: { pct: number; size?: number }) {
  const r = (size - 7) / 2;
  const c = 2 * Math.PI * r;
  const color = pct >= 70 ? "#22c55e" : pct >= 40 ? "#f59e0b" : "#ef4444";
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="currentColor" strokeWidth={5} className="text-border" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={5}
        strokeDasharray={`${(pct/100)*c} ${c}`} strokeLinecap="round"
        style={{ transition: "stroke-dasharray .5s ease" }} />
    </svg>
  );
}

function Bar({ value, max, color = "bg-primary" }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.min(Math.round((value / max) * 100), 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
        <div className={cn("h-full rounded-full transition-all duration-500", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[11px] tabular-nums text-muted-foreground w-10 text-right">{value}/{max}</span>
    </div>
  );
}

// ── Team health strip ─────────────────────────────────────────────────────────

function HealthStrip({ r }: { r: BackendTeamKPIReport }) {
  const cards = [
    { label: "Avg Cycle Time",   value: fmtH(r.team_avg_cycle_time_hours),
      sub: "per ticket", Icon: Clock, accent: "text-sky-500", bg: "bg-sky-500/10" },
    { label: "Completion Rate",  value: fmtPct(r.team_completion_rate),
      sub: "done / total", Icon: Target, accent: "text-emerald-500", bg: "bg-emerald-500/10" },
    { label: "Blocker Rate",     value: fmtPct(r.team_blocker_rate),
      sub: "tickets blocked",
      Icon: Shield,
      accent: r.team_blocker_rate > 0.3 ? "text-rose-500" : "text-violet-500",
      bg:     r.team_blocker_rate > 0.3 ? "bg-rose-500/10" : "bg-violet-500/10" },
    { label: "Avg Question Response", value: fmtH(r.team_question_response_time_hours),
      sub: r.team_unanswered_question_rate != null
        ? `${fmtPct(r.team_unanswered_question_rate)} unanswered` : "no data yet",
      Icon: MessageSquare,
      accent: r.team_question_response_time_hours != null && r.team_question_response_time_hours > 8
        ? "text-amber-500" : "text-cyan-500",
      bg: r.team_question_response_time_hours != null && r.team_question_response_time_hours > 8
        ? "bg-amber-500/10" : "bg-cyan-500/10" },
  ];
  return (
    <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
      {cards.map((c, i) => (
        <motion.div key={c.label} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.05 }}
          className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-4 shadow-sm">
          <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-lg", c.bg)}>
            <c.Icon className={cn("h-4 w-4", c.accent)} />
          </div>
          <div className="min-w-0">
            <p className={cn("text-xl font-bold leading-none", c.accent)}>{c.value}</p>
            <p className="text-[10px] font-medium text-muted-foreground mt-1 truncate">{c.label}</p>
            <p className="text-[10px] text-muted-foreground/60 truncate">{c.sub}</p>
          </div>
        </motion.div>
      ))}
    </div>
  );
}

// ── Warning signals panel ─────────────────────────────────────────────────────

function Warnings({ signals }: { signals: BackendTeamWarningSignal[] }) {
  if (!signals.length) return null;
  const sorted = [
    ...signals.filter(s => s.severity === "critical"),
    ...signals.filter(s => s.severity === "warning"),
    ...signals.filter(s => s.severity === "info"),
  ];
  return (
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-border bg-rose-500/5">
        <AlertCircle className="h-4 w-4 text-rose-500" />
        <h3 className="text-sm font-semibold text-foreground">
          Manager Alerts
          <span className="ml-2 inline-flex items-center justify-center rounded-full bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-bold text-rose-500">
            {sorted.length}
          </span>
        </h3>
      </div>
      <div className="divide-y divide-border">
        {sorted.slice(0, 8).map((sig, i) => {
          const cfg = SEVERITY[sig.severity];
          return (
            <div key={i} className="flex items-start gap-3 px-5 py-3">
              <div className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", cfg.dot)} />
              <div className="flex-1 min-w-0">
                <span className="text-xs font-semibold text-foreground">{sig.developer_name}</span>
                <span className="mx-1.5 text-muted-foreground/40">·</span>
                <span className="text-xs text-muted-foreground">{sig.description}</span>
              </div>
              <span className={cn("shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] font-medium capitalize", cfg.bar)}>
                {sig.severity}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Task-type profile ─────────────────────────────────────────────────────────

function TypeProfile({ profile }: { profile: BackendTaskTypeProfile[] }) {
  if (!profile.length) return <p className="text-xs text-muted-foreground">No task data.</p>;
  const maxTotal = Math.max(...profile.map(p => p.count_total), 1);
  return (
    <div className="space-y-2.5">
      {profile.map(p => {
        const cfg = TASK_ICONS[p.ticket_type] ?? { Icon: BarChart3, color: "bg-muted-foreground" };
        return (
          <div key={p.ticket_type} className="flex items-center gap-3">
            <div className="flex w-24 items-center gap-1.5 shrink-0">
              <cfg.Icon className="h-3 w-3 text-muted-foreground shrink-0" />
              <span className="text-[11px] text-muted-foreground capitalize truncate">{p.ticket_type}</span>
            </div>
            <div className="flex-1 flex items-center gap-2">
              <div className="flex-1 h-2 rounded-full bg-border overflow-hidden">
                <div className={cn("h-full rounded-full transition-all duration-500", cfg.color)}
                  style={{ width: `${Math.round((p.count_total / maxTotal) * 100)}%` }} />
              </div>
              <span className="text-[11px] tabular-nums text-muted-foreground w-12 shrink-0">
                {p.count_done}/{p.count_total}
              </span>
            </div>
            <span className="text-[11px] tabular-nums text-muted-foreground w-14 shrink-0 text-right">
              {fmtH(p.avg_cycle_time_hours)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Per-developer detail panel (fetched on demand) ────────────────────────────

function DevDetail({
  pid,
  devId,
  sd,
  ed,
  platform,
}: {
  pid: number;
  devId: number;
  sd?: string;
  ed?: string;
  platform: PlatformFilter;
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dev-kpis", pid, devId, sd, ed, platform],
    queryFn: () => developerApi.getDeveloperKPIs(devId, pid, undefined, sd, ed, platform),
    staleTime: 60_000,
  });

  if (isLoading) return <div className="flex justify-center py-8"><LoadingSpinner /></div>;
  if (isError || !data) return (
    <p className="py-6 text-center text-xs text-muted-foreground">Could not load KPI detail.</p>
  );

  const d = data as BackendDeveloperKPIReport;
  const pct = d.tickets_total > 0 ? Math.round((d.tickets_done / d.tickets_total) * 100) : 0;
  const responseTime = d.comment_response_time_hours ?? d.question_response_time_hours;
  const ertExceeded = d.ert_status === "exceeded";
  const ticketMetrics = d.ticket_response_metrics ?? [];

  return (
    <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.2 }}
      className="border-t border-border bg-muted/20 px-5 py-5 overflow-hidden">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">

        {/* KPI stats */}
        <div className="space-y-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">KPI Summary</p>
          <div className="rounded-lg border border-border bg-card px-3 py-2 text-[11px] text-muted-foreground">
            <p><span className="font-semibold text-foreground">Source:</span> {fmtProvider(d.provider_sources)}</p>
            {(d.client_name || d.engagement_name) && (
              <p className="mt-0.5 truncate">
                <span className="font-semibold text-foreground">Engagement:</span>{" "}
                {[d.client_name, d.engagement_name].filter(Boolean).join(" · ")}
              </p>
            )}
          </div>
          <div className="flex items-center gap-4">
            <div className="relative shrink-0">
              <Ring pct={pct} size={52} />
              <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold text-foreground">{pct}%</span>
            </div>
            <div className="flex-1 space-y-1.5">
              <Bar value={d.tickets_done} max={d.tickets_total} color="bg-primary" />
              <Bar value={d.story_points_completed} max={d.story_points_total} color="bg-violet-500" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {[
              { label: "Cycle Time",  value: fmtH(d.avg_cycle_time_hours),   Icon: Clock },
              { label: "Blocker Age", value: fmtH(d.avg_blocker_age_hours),  Icon: Shield },
              { label: "Stalled",     value: String(d.stalled_ticket_count), Icon: AlertTriangle },
              { label: "Blockers",    value: String(d.active_blockers),       Icon: Target },
            ].map(({ label, value, Icon }) => (
              <div key={label} className="rounded-lg border border-border bg-card px-3 py-2.5">
                <div className="flex items-center gap-1.5 mb-1">
                  <Icon className="h-3 w-3 text-muted-foreground" />
                  <span className="text-[10px] text-muted-foreground">{label}</span>
                </div>
                <p className="text-sm font-bold text-foreground">{value}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Task-type profile */}
        <div className="space-y-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            Task-Type Profile <span className="normal-case font-normal">(done/total · avg cycle)</span>
          </p>
          <TypeProfile profile={d.task_type_profile ?? []} />
        </div>

        {/* Collaboration + warnings */}
        <div className="space-y-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Collaboration</p>
          <div className="space-y-2">
            {[
              { label: "Avg Comment Response", value: fmtH(responseTime), Icon: Clock,
                warn: ertExceeded },
              { label: "Median Response", value: fmtH(d.median_comment_response_time_hours), Icon: MessageSquare,
                warn: false },
              { label: "ERT Target", value: fmtH(d.ert_target_hours), Icon: Target,
                warn: ertExceeded },
              { label: "Unanswered Questions",   value: String(d.unanswered_questions_count ?? 0), Icon: HelpCircle,
                warn: d.unanswered_question_rate != null && d.unanswered_question_rate > 0.3 },
            ].map(({ label, value, Icon, warn }) => (
              <div key={label} className={cn(
                "flex items-center justify-between rounded-lg border px-3 py-2.5",
                warn ? "border-amber-500/30 bg-amber-500/5" : "border-border bg-card",
              )}>
                <div className="flex items-center gap-2">
                  <Icon className={cn("h-3.5 w-3.5", warn ? "text-amber-500" : "text-muted-foreground")} />
                  <span className="text-xs text-muted-foreground">{label}</span>
                </div>
                <span className={cn("text-sm font-bold", warn ? "text-amber-500" : "text-foreground")}>{value}</span>
              </div>
            ))}
          </div>
          <div className={cn(
            "rounded-lg border px-3 py-2 text-xs",
            ertExceeded ? "border-rose-500/30 bg-rose-500/5 text-rose-600" : "border-border bg-card text-muted-foreground",
          )}>
            ERT status: <span className="font-semibold capitalize">{(d.ert_status ?? "not-available").replace("-", " ")}</span>
            {(d.tickets_exceeded_ert ?? 0) > 0 && ` · ${d.tickets_exceeded_ert} ticket${d.tickets_exceeded_ert === 1 ? "" : "s"} exceeded`}
          </div>
          {(d.warning_signals?.length ?? 0) > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">Active Signals</p>
              {d.warning_signals?.map((sig, i) => (
                <div key={i} className="flex items-start gap-2 rounded-md border border-rose-500/20 bg-rose-500/5 px-3 py-2">
                  <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-500" />
                  <span className="text-[11px] text-rose-600 leading-snug">{sig}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {ticketMetrics.length > 0 && (
        <div className="mt-5 rounded-lg border border-border bg-card overflow-hidden">
          <div className="grid grid-cols-[1fr_90px_90px_90px] gap-3 border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
            <span>Ticket</span>
            <span>Response</span>
            <span>Blocker</span>
            <span>ERT</span>
          </div>
          <div className="divide-y divide-border">
            {ticketMetrics.slice(0, 8).map(metric => (
              <div key={`${metric.provider}-${metric.ticket_id}`} className="grid grid-cols-[1fr_90px_90px_90px] gap-3 px-3 py-2 text-xs">
                <div className="min-w-0">
                  <p className="truncate font-medium text-foreground">{metric.ticket_title}</p>
                  <p className="text-[10px] text-muted-foreground">{metric.provider} · {metric.ticket_id}</p>
                </div>
                <span className="font-medium text-foreground">{fmtH(metric.response_time_hours)}</span>
                <span className={cn("font-medium capitalize", metric.blocker_status === "blocked" ? "text-rose-500" : "text-muted-foreground")}>
                  {metric.blocker_status}
                  {metric.blocker_duration_hours != null && ` (${fmtH(metric.blocker_duration_hours)})`}
                </span>
                <span className={cn("font-medium", metric.exceeded_ert ? "text-rose-500" : "text-muted-foreground")}>
                  {metric.exceeded_ert == null ? "—" : metric.exceeded_ert ? "Exceeded" : "Within"}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}

// ── Cards view ────────────────────────────────────────────────────────────────

function Cards({ members, selected, onSelect }: {
  members: BackendTeamMemberSummary[];
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
      {members.map((m, i) => {
        const cfg = STATUS[m.status as keyof typeof STATUS] ?? STATUS["on-track"];
        const pct = m.story_points_total > 0
          ? Math.round((m.story_points_completed / m.story_points_total) * 100) : 0;
        const isSelected = selected === m.developer_id;
        return (
          <motion.div key={m.developer_id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            onClick={() => onSelect(m.developer_id)}
            className={cn(
              "rounded-xl border border-border border-l-4 bg-card shadow-sm overflow-hidden cursor-pointer transition-shadow",
              cfg.border, isSelected ? "ring-2 ring-primary/30" : "hover:shadow-md",
            )}>
            <div className="flex items-center gap-3 px-4 pt-4 pb-3">
              <Avatar name={m.developer_name} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-foreground truncate">{m.developer_name}</p>
                  <StatusPill status={m.status} />
                </div>
                <p className="text-[11px] text-muted-foreground capitalize">
                  {m.role} · {fmtProvider(m.provider_sources)}
                </p>
              </div>
            </div>
            <div className="px-4 pb-4 space-y-3">
              <div className="flex items-center gap-3">
                <div className="relative shrink-0">
                  <Ring pct={pct} size={44} />
                  <span className="absolute inset-0 flex items-center justify-center text-[9px] font-bold text-foreground">{pct}%</span>
                </div>
                <div className="flex-1 space-y-1.5">
                  <Bar value={m.story_points_completed} max={m.story_points_total} color="bg-primary" />
                  <Bar value={Math.round(m.completion_rate * 10)} max={10} color="bg-violet-500" />
                </div>
              </div>
              <div className="grid grid-cols-4 gap-1 border-t border-border pt-3">
                {[
                  { l: "Cycle",   v: fmtH(m.avg_cycle_time_hours),         Icon: Clock,
                    w: false },
                  { l: "Blocker", v: String(m.active_blockers),             Icon: Shield,
                    w: m.active_blockers > 0 },
                  { l: "QRT",     v: fmtH(m.question_response_time_hours),  Icon: MessageSquare,
                    w: m.ert_status === "exceeded" },
                  { l: "UQR",     v: fmtPct(m.unanswered_question_rate),    Icon: HelpCircle,
                    w: m.unanswered_question_rate != null && m.unanswered_question_rate > 0.3 },
                ].map(({ l, v, Icon, w }) => (
                  <div key={l} className="flex flex-col items-center gap-0.5">
                    <Icon className="h-3 w-3 text-muted-foreground" />
                    <p className={cn("text-[11px] font-semibold text-foreground", w && "text-rose-500")}>{v}</p>
                    <p className="text-[9px] text-muted-foreground">{l}</p>
                  </div>
                ))}
              </div>
              {m.warning_count > 0 && (
                <div className="flex items-center gap-1.5 rounded-md bg-rose-500/5 border border-rose-500/20 px-2 py-1.5">
                  <AlertCircle className="h-3 w-3 text-rose-500 shrink-0" />
                  <span className="text-[10px] text-rose-600 font-medium">
                    {m.warning_count} active signal{m.warning_count > 1 ? "s" : ""}
                  </span>
                </div>
              )}
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

// ── Matrix (table) view ───────────────────────────────────────────────────────

function Matrix({ members, pid, selected, onSelect }: {
  members: BackendTeamMemberSummary[];
  pid: number;
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  const cols = ["Developer", "Status", "Pts", "Cycle", "Done%", "Blockers", "Blk%", "QRT", "UQR", "Signals", ""];
  return (
    <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border text-left">
              {cols.map(h => (
                <th key={h} className="px-4 py-2.5 text-[11px] font-semibold text-muted-foreground whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {members.map(m => {
              const isSelected = selected === m.developer_id;
              return (
                <>
                  <tr key={m.developer_id}
                    onClick={() => onSelect(m.developer_id)}
                    className={cn(
                      "cursor-pointer border-b border-border transition-colors",
                      isSelected ? "bg-sidebar-accent" : "hover:bg-muted/40",
                    )}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Avatar name={m.developer_name} />
                        <div>
                          <p className="font-semibold text-foreground">{m.developer_name}</p>
                          <p className="text-[10px] text-muted-foreground capitalize">
                            {m.role} · {fmtProvider(m.provider_sources)}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3"><StatusPill status={m.status} /></td>
                    <td className="px-4 py-3 tabular-nums">
                      <span className="font-medium text-foreground">{m.story_points_completed}</span>
                      <span className="text-muted-foreground">/{m.story_points_total}</span>
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground">{fmtH(m.avg_cycle_time_hours)}</td>
                    <td className="px-4 py-3">
                      <span className={cn("font-semibold",
                        m.completion_rate >= 0.7 ? "text-emerald-500" :
                        m.completion_rate >= 0.4 ? "text-amber-500" : "text-rose-500")}>
                        {fmtPct(m.completion_rate)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("font-bold", m.active_blockers > 0 ? "text-rose-500" : "text-muted-foreground")}>
                        {m.active_blockers}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("font-medium",
                        m.blocker_rate > 0.4 ? "text-rose-500" :
                        m.blocker_rate > 0.2 ? "text-amber-500" : "text-muted-foreground")}>
                        {fmtPct(m.blocker_rate)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("font-medium",
                        m.ert_status === "exceeded"
                          ? "text-amber-500" : "text-muted-foreground")}>
                        {fmtH(m.question_response_time_hours)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={cn("font-medium",
                        m.unanswered_question_rate != null && m.unanswered_question_rate > 0.3
                          ? "text-rose-500" : "text-muted-foreground")}>
                        {fmtPct(m.unanswered_question_rate)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {m.warning_count > 0
                        ? <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-[10px] font-medium text-rose-500">
                            <AlertCircle className="h-2.5 w-2.5" />{m.warning_count}
                          </span>
                        : <span className="text-muted-foreground/40">—</span>}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {isSelected ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    </td>
                  </tr>
                  {isSelected && (
                    <tr key={`${m.developer_id}-detail`}>
                      <td colSpan={11} className="p-0">
                        <DevDetail pid={pid} devId={m.developer_id} sd={sd} ed={ed} platform={globalPlatformFilter} />
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}



// ── Page ──────────────────────────────────────────────────────────────────────

const DeveloperProgress = () => {
  const { currentProject, globalDateRange, globalPlatformFilter } = useProject();
  const { user } = useAuth();
  const [view, setView] = useState<"cards" | "matrix">("cards");
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const pid = currentProject?.id ?? 0;
  const { startDate: sd, endDate: ed } = getApiDateRange(globalDateRange);
  const isSelfService = isDeveloperUser(user);

  const personalKpiQuery = useQuery({
    queryKey: ["dev-kpis", pid, user?.kpi_subject_id, "self", sd, ed, globalPlatformFilter],
    queryFn: () => developerApi.getDeveloperKPIs(user!.kpi_subject_id!, pid, undefined, sd, ed, globalPlatformFilter),
    staleTime: 60_000,
    enabled: isSelfService && pid > 0 && Boolean(user?.kpi_subject_id),
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["team-kpis", pid, sd, ed, globalPlatformFilter],
    queryFn: () => developerApi.getTeamKPIs(pid, undefined, sd, ed, globalPlatformFilter),
    staleTime: 60_000,
    enabled: !isSelfService && pid > 0,
  });

  if (!currentProject) {
    return <EmptyProjectState title="Import a Trello board to track developer KPIs" />;
  }

  if (isSelfService) {
    if (!user?.kpi_subject_id) {
      return (
        <DashboardLayout>
          <div className="rounded-2xl border border-border bg-card p-8 text-sm text-muted-foreground">
            Your account is active, but it is not linked to a Trello developer profile yet.
          </div>
        </DashboardLayout>
      );
    }
    if (personalKpiQuery.isLoading) return <DashboardLayout><LoadingSpinner /></DashboardLayout>;
    if (personalKpiQuery.isError || !personalKpiQuery.data) return (
       <DashboardLayout>
          <div className="rounded-2xl border border-border bg-card p-8 text-center text-sm text-muted-foreground mt-6 max-w-2xl mx-auto shadow-sm">
             <h3 className="font-semibold text-foreground text-lg mb-2">No KPI Records Found</h3>
             <p className="mb-4">We could not pull performance KPIs for your profile on this specific project.</p>
             <p className="text-xs opacity-70">This typically happens when you haven't been assigned or completed any Trello tickets here yet, or if your integration mapping isn't fully synchronized by your company admin.</p>
          </div>
       </DashboardLayout>
    );
    const personal = personalKpiQuery.data as BackendDeveloperKPIReport;
    const isAtRisk = personal?.status === "at-risk" || personal?.status === "behind";
    
    return (
      <DashboardLayout>
        <div className="space-y-6 max-w-5xl mx-auto pb-10">
          <div className="flex flex-col md:flex-row items-start md:items-end justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-widest text-primary drop-shadow-sm mb-1">
                Developer Profile
              </p>
              <h2 className="text-2xl font-bold text-foreground drop-shadow-sm">My KPI Dashboard</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Personal delivery, blockers, and collaboration metrics for <span className="font-medium text-foreground">{currentProject.name}</span>.
              </p>
            </div>
            {personal?.status && (
              <div className="bg-card px-4 py-2 rounded-xl shadow-sm border flex items-center gap-3">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Current Status</span>
                <StatusPill status={personal.status} />
              </div>
            )}
          </div>

          <div className="relative rounded-2xl overflow-hidden border border-border shadow-md">
             {/* Beautiful gradient header */}
            <div className={cn(
              "absolute inset-x-0 top-0 h-32 bg-gradient-to-br opacity-20 dark:opacity-10",
              isAtRisk ? "from-rose-500 to-amber-500" : "from-emerald-400 to-cyan-500"
            )} />
            <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-transparent to-card" />
            
            <div className="relative bg-card px-6 pb-8 pt-10">
               {/* Avatar and Welcome */}
               <div className="flex items-center gap-5 mb-8">
                  <div className="p-1 rounded-full bg-background border shadow-sm shrink-0">
                     <div className="w-16 h-16 rounded-full bg-gradient-to-br flex items-center justify-center text-xl font-bold text-white from-cyan-500 to-blue-600 shadow-inner">
                        {personal?.developer_name?.slice(0, 2).toUpperCase() ?? "ME"}
                     </div>
                  </div>
                  <div>
                    <h3 className="text-2xl font-bold tracking-tight">{personal?.developer_name ?? "Developer"}</h3>
                    <p className="text-sm text-muted-foreground flex items-center gap-2 mt-1">
                       <BriefcaseBusiness className="w-4 h-4" /> 
                       {isAtRisk ? "Requires Attention" : "Performing Exceptionally"}
                    </p>
                  </div>
               </div>
               
               <div className="bg-background/50 rounded-xl border p-1 shadow-sm">
                  {personal?.developer_id && <DevDetail pid={pid} devId={personal.developer_id} sd={sd} ed={ed} platform={globalPlatformFilter} />}
               </div>
            </div>
          </div>

          <div className="flex items-center justify-between text-xs text-muted-foreground px-2">
            <span className="flex items-center gap-1.5"><Shield className="w-3.5 h-3.5" /> Secure & Private KPI Access</span>
            <p>
              Computed {personal?.computed_at ? new Date(personal.computed_at).toLocaleString() : "just now"}
            </p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (isLoading) return <DashboardLayout><LoadingSpinner /></DashboardLayout>;
  if (isError || !data) return <DashboardLayout><ErrorState /></DashboardLayout>;

  const report = data as BackendTeamKPIReport;
  const members = report.members;
  const isVendorUser = user?.role === "esn_admin" || user?.role === "esn_delivery_manager";
  const counts = {
    "on-track": members.filter(m => m.status === "on-track").length,
    "at-risk":  members.filter(m => m.status === "at-risk").length,
    "behind":   members.filter(m => m.status === "behind").length,
  };

  const toggle = (id: number) => setSelectedId(prev => prev === id ? null : id);

  return (
    <DashboardLayout>
      <div className="space-y-5">

        {/* Header */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-base font-bold text-foreground">Developer KPI Dashboard</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              {members.length} developer{members.length !== 1 ? "s" : ""} ·{" "}
              <span className="text-emerald-500">{counts["on-track"]} on track</span>
              {counts["at-risk"] > 0 && <>, <span className="text-amber-500">{counts["at-risk"]} at risk</span></>}
              {counts.behind > 0 && <>, <span className="text-rose-500">{counts.behind} behind</span></>}
            </p>
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-border bg-muted/40 p-0.5">
            {(["cards", "matrix"] as const).map(v => (
              <button key={v} onClick={() => setView(v)}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-all",
                  view === v ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
                )}>
                {v === "cards" ? "Cards" : "Matrix"}
              </button>
            ))}
          </div>
        </div>



        {/* Team health */}
        <HealthStrip r={report} />

        {/* Warnings */}
        <Warnings signals={report.warning_signals ?? []} />

        {/* Empty state */}
        {members.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-card py-16 text-center">
            <Users className="h-10 w-10 text-muted-foreground/30 mb-3" />
            <p className="text-sm font-medium text-muted-foreground">
              {isVendorUser
                ? "No external developer work is assigned to this engagement yet."
                : "No developers found for this project."}
            </p>
            <p className="text-xs text-muted-foreground/60 mt-1">
              {isVendorUser
                ? "Vendor dashboards only show your assigned external developers and their Trello work."
                : "Assign tickets to developers to start tracking KPIs."}
            </p>
          </div>
        ) : view === "matrix" ? (
          <Matrix members={members} pid={pid} selected={selectedId} onSelect={toggle} />
        ) : (
          <div className="space-y-4">
            <Cards members={members} selected={selectedId} onSelect={toggle} />
            <AnimatePresence>
              {selectedId !== null && (
                <motion.div key={selectedId} initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
                  <div className="flex items-center justify-between px-5 py-3 border-b border-border">
                    <p className="text-sm font-semibold text-foreground">
                      {members.find(m => m.developer_id === selectedId)?.developer_name} — KPI Detail
                    </p>
                    <button onClick={() => setSelectedId(null)}
                      className="text-xs text-muted-foreground hover:text-foreground transition-colors">
                      Close
                    </button>
                  </div>
                  <DevDetail pid={pid} devId={selectedId} sd={sd} ed={ed} platform={globalPlatformFilter} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        <p className="text-[10px] text-muted-foreground/50 text-right">
          Computed {new Date(report.computed_at).toLocaleString()}
        </p>
      </div>
    </DashboardLayout>
  );
};

export default DeveloperProgress;
