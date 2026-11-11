import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import DashboardLayout from "@/components/DashboardLayout";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";
import EmptyProjectState from "@/components/EmptyProjectState";
import { isDeveloperUser, useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";

import { useState } from "react";
import { DateRange } from "react-day-picker";
import { format } from "date-fns";
import { sprintApi } from "@/services/api/index";
import { DatePickerWithRange } from "@/components/ui/date-range-picker";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import { analyticsApi } from "@/services/api/analytics";
import { developerApi } from "@/services/api/developers";
import { getApiDateRange } from "@/lib/dateRange";
import { cn } from "@/lib/utils";
import type { BackendDeveloperKPIReport } from "@/services/api/types";
import {
  CheckCircle2, AlertTriangle, TrendingDown, Clock, Target, Shield,
  MessageSquare, BarChart3, HelpCircle, BriefcaseBusiness, ArrowUp, ArrowDown
} from "lucide-react";

// ── Shared UI ─────────────────────────────────────────────────────────────────

const STATUS = {
  "on-track": {
    label: "On Track", Icon: CheckCircle2,
    pill: "bg-emerald-500/15 text-emerald-500 ring-1 ring-emerald-500/30",
  },
  "at-risk": {
    label: "At Risk", Icon: AlertTriangle,
    pill: "bg-amber-500/15 text-amber-500 ring-1 ring-amber-500/30",
  },
  "behind": {
    label: "Behind", Icon: TrendingDown,
    pill: "bg-rose-500/15 text-rose-500 ring-1 ring-rose-500/30",
  },
} as const;

const fmtH = (h: number | null | undefined) => {
  if (h == null) return "—";
  return h < 24 ? `${h.toFixed(1)}h` : `${(h / 24).toFixed(1)}d`;
};

const fmtPct = (v: number | null | undefined) =>
  v == null ? "—" : `${(v * 100).toFixed(0)}%`;

function Ring({ pct, size = 48 }: { pct: number; size?: number }) {
  const r = (size - 7) / 2;
  const c = 2 * Math.PI * r;
  const color = pct >= 70 ? "#22c55e" : pct >= 40 ? "#f59e0b" : "#ef4444";
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="currentColor" strokeWidth={4} className="text-border" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={4}
        strokeDasharray={`${(pct/100)*c} ${c}`} strokeLinecap="round"
        style={{ transition: "stroke-dasharray .8s cubic-bezier(0.4, 0, 0.2, 1)" }} />
    </svg>
  );
}

function StatTile({ label, value, Icon, warn, trendNode }: { label: string, value: string, Icon: React.ElementType, warn?: boolean, trendNode?: React.ReactNode }) {
  return (
    <div className={cn(
      "flex flex-col gap-2 rounded-2xl border px-4 py-4 transition-all hover:-translate-y-0.5",
      warn ? "border-amber-500/30 bg-amber-500/5 shadow-[0_4px_12px_rgba(245,158,11,0.05)]" : "border-border bg-card shadow-sm"
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className={cn("p-1.5 rounded-lg", warn ? "bg-amber-500/10 text-amber-600" : "bg-primary/10 text-primary")}>
            <Icon className="h-4 w-4" />
          </div>
          <span className="text-xs font-semibold text-muted-foreground">{label}</span>
        </div>
        {trendNode}
      </div>
      <p className={cn("text-2xl font-bold tracking-tight", warn ? "text-amber-500" : "text-foreground")}>{value}</p>
    </div>
  );
}

// ── Developer Personal Dashboard ────────────────────────────────────────────────

export default function DeveloperDashboard() {
  const { currentProject, globalDateRange, globalPlatformFilter } = useProject();
  const { user } = useAuth();
  const pid = currentProject?.id ?? 0;
  const isSelfService = isDeveloperUser(user);
  const { startDate, endDate } = getApiDateRange(globalDateRange);

  const [selectedSprintId, setSelectedSprintId] = useState<string>("all");

  const personalKpiQuery = useQuery({
    queryKey: ["dev-kpis-me", pid, selectedSprintId, startDate, endDate, globalPlatformFilter],
    queryFn: () => {
      const spId = selectedSprintId !== "all" ? parseInt(selectedSprintId, 10) : undefined;
      return analyticsApi.getDeveloperMe(pid, spId, startDate, endDate, globalPlatformFilter);
    },
    staleTime: 60_000,
    enabled: isSelfService && pid > 0,
  });

  const sprintsQuery = useQuery({
    queryKey: ["sprints", pid],
    queryFn: () => sprintApi.list(pid),
    enabled: isSelfService && pid > 0,
  });

  const d = personalKpiQuery?.data as BackendDeveloperKPIReport | undefined;

  const historyQuery = useQuery({
    queryKey: ["dev-history", d?.developer_id, pid],
    queryFn: () => developerApi.getDeveloperKPIHistory(d!.developer_id, pid),
    enabled: !!d?.developer_id && pid > 0,
  });

  if (!isSelfService) {
    return <EmptyProjectState title="Only Developers can access the Personal Dashboard" />;
  }

  if (!currentProject) {
    return <EmptyProjectState title="Link a Project to view your personal KPIs" />;
  }

  if (personalKpiQuery?.isLoading) {
    return <DashboardLayout><LoadingSpinner title="Loading Your Activity..." /></DashboardLayout>;
  }

  if (personalKpiQuery?.isError || !personalKpiQuery?.data) {
    return (
      <DashboardLayout>
        <div className="rounded-3xl border border-border bg-card p-10 text-center mt-6 max-w-2xl mx-auto shadow-sm">
          <div className="mx-auto w-16 h-16 rounded-full bg-muted/50 flex items-center justify-center mb-6">
            <BarChart3 className="h-8 w-8 text-muted-foreground/50" />
          </div>
          <h3 className="font-semibold text-foreground text-xl mb-3">No KPI Records Found</h3>
          <p className="mb-4 text-muted-foreground">We could not pull performance KPIs for your profile on this specific project.</p>
          <p className="text-sm opacity-70">This typically happens when you haven't been assigned any tickets yet, or your developer account is not properly linked to your Git/Trello profile.</p>
        </div>
      </DashboardLayout>
    );
  }

  if (!d) {
    return <DashboardLayout><ErrorState /></DashboardLayout>;
  }
  
  const historyData = historyQuery.data || [];
  const previousSprint = historyData.length > 0 ? historyData[0] : null;

  const renderTrend = (current: number, previous: number | null | undefined, reversedGood = false) => {
     if (previous == null) return null;
     const delta = current - previous;
     if (delta === 0) return null;
     const isUp = delta > 0;
     const isGood = reversedGood ? !isUp : isUp;
     return (
       <div className={`flex items-center gap-1 text-[10px] font-bold ${isGood ? 'text-emerald-500' : 'text-rose-500'} bg-black/5 dark:bg-white/5 px-2 py-0.5 rounded-full`}>
         {isUp ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}
         <span>{Math.abs(delta).toFixed(1)}</span>
       </div>
     );
  };

  const isAtRisk = d.status === "at-risk" || d.status === "behind";
  const pct = d.tickets_total > 0 ? Math.round((d.tickets_done / d.tickets_total) * 100) : 0;
  const ertExceeded = d.ert_status === "exceeded";

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-6xl mx-auto pb-10">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col md:flex-row items-start md:items-end justify-between gap-4 mb-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-primary drop-shadow-sm mb-2">
              Personal Insights
            </p>
            <h1 className="text-3xl font-bold tracking-tight text-foreground drop-shadow-sm">Tracking {currentProject.name}</h1>
            <p className="text-sm text-muted-foreground mt-2 max-w-xl">
              Real-time actionable metrics on your delivery completion, blockers, and responsiveness to help you optimize your workflow.
            </p>
          </div>
          {d.status && (
            <div className="bg-card px-4 py-2.5 rounded-xl shadow-sm border border-border/50 flex items-center gap-3 backdrop-blur-sm">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Pace</span>
              <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold uppercase shrink-0 tracking-wider", STATUS[d.status]?.pill)}>
                {STATUS[d.status]?.label ?? "Unknown"}
              </span>
            </div>
          )}
        </motion.div>

        {/* Header Profile Card */}
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="relative rounded-3xl overflow-hidden border border-border shadow-lg">
          <div className={cn(
            "absolute inset-x-0 top-0 h-32 bg-gradient-to-br opacity-[0.15] dark:opacity-10",
            isAtRisk ? "from-rose-500 via-rose-500/20 to-amber-500" : "from-emerald-400 via-cyan-500/20 to-blue-500"
          )} />
          <div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-transparent to-card" />
          
          <div className="relative bg-card px-8 md:px-10 pb-10 pt-12">
            <div className="flex flex-col md:flex-row gap-8 items-center md:items-start">
              <div className="p-1 rounded-3xl bg-background border shadow-md shrink-0">
                <div className="w-24 h-24 rounded-2xl bg-gradient-to-br flex items-center justify-center text-3xl font-bold text-white from-indigo-500 via-purple-500 to-pink-500 shadow-inner">
                  {d.developer_name?.slice(0, 2).toUpperCase() ?? "ME"}
                </div>
              </div>
              <div className="flex-1 text-center md:text-left mt-2">
                <h3 className="text-3xl font-bold tracking-tight">{d.developer_name ?? "Developer"}</h3>
                <p className="text-sm text-muted-foreground font-medium flex items-center justify-center md:justify-start gap-2 mt-2">
                  <BriefcaseBusiness className="w-4 h-4" /> 
                  {d.developer_role || "Software Engineer"}
                </p>
                <div className="mt-5 inline-flex items-center gap-6 px-5 py-3 bg-muted/40 rounded-2xl border border-border/50 backdrop-blur-sm">
                  <div className="flex items-center gap-4 border-r border-border/50 pr-6">
                    <div className="relative">
                      <Ring pct={pct} size={40} />
                      <span className="absolute inset-0 flex items-center justify-center text-[10px] font-bold">{pct}%</span>
                    </div>
                    <div className="text-left">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-xs text-muted-foreground uppercase tracking-widest font-semibold">Done</p>
                        {renderTrend(pct, previousSprint ? Math.round(previousSprint.completion_rate * 100) : null)}
                      </div>
                      <p className="text-lg font-bold leading-none mt-1">{d.tickets_done} / {d.tickets_total}</p>
                    </div>
                  </div>
                  <div className="text-left">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs text-muted-foreground uppercase tracking-widest font-semibold">Blocked</p>
                      {renderTrend(d.active_blockers, previousSprint?.blocker_count, true)}
                    </div>
                    <p className={cn("text-lg font-bold leading-none mt-1", d.active_blockers > 0 ? "text-rose-500" : "text-emerald-500")}>
                      {d.active_blockers} <span className="text-xs font-medium text-muted-foreground">active</span>
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Detailed Metrics Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mt-8">
          <StatTile label="Cycle Time" value={fmtH(d.avg_cycle_time_hours)} Icon={Clock} trendNode={renderTrend(d.avg_cycle_time_hours ?? 0, previousSprint?.avg_cycle_time_hours ?? 0, true)} />
          <StatTile label="Avg Response" value={fmtH(d.comment_response_time_hours ?? d.question_response_time_hours)} warn={ertExceeded} Icon={MessageSquare} trendNode={renderTrend(d.comment_response_time_hours ?? d.question_response_time_hours ?? 0, previousSprint?.question_response_time_hours ?? previousSprint?.question_response_time_hours ?? 0, true)} />
          <StatTile label="Stalled Duration" value={fmtH(d.avg_blocker_age_hours)} warn={d.avg_blocker_age_hours != null && d.avg_blocker_age_hours > 24} Icon={Shield} />
          <StatTile label="Unanswered" value={String(d.unanswered_questions_count ?? 0)} warn={(d.unanswered_questions_count ?? 0) > 0} Icon={HelpCircle} />
        </div>

        {/* Footer info */}
        <div className="flex items-center justify-between text-[11px] text-muted-foreground px-2 pt-4">
          <span className="flex items-center gap-1.5"><Shield className="w-3.5 h-3.5" /> Private Dashboard</span>
          <p>
            Last Updated: <span className="font-medium text-foreground">{d.computed_at ? new Date(d.computed_at).toLocaleString() : "just now"}</span>
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
}
