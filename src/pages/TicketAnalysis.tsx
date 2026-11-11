import { motion } from "framer-motion";
import { useState, useMemo } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";
import EmptyProjectState from "@/components/EmptyProjectState";
import { useProject } from "@/contexts/ProjectContext";
import { useTickets } from "@/hooks/useSprintData";
import { getApiDateRange } from "@/lib/dateRange";
import { isTrelloCompatiblePlatform, PLATFORM_LABELS } from "@/lib/platforms";
import { cn } from "@/lib/utils";
import {
  AlertCircle, CheckCircle2, XCircle, Clock, ArrowUpDown,
  Star, Filter, ChevronRight, PackageOpen,
} from "lucide-react";
import type { UITicket } from "@/services/api/types";

// ── helpers ───────────────────────────────────────────────────────────────────

const statusConfig: Record<string, { label: string; dot: string; pill: string }> = {
  "completed":   { label: "Completed",   dot: "bg-emerald-500", pill: "bg-emerald-500/15 text-emerald-500 ring-1 ring-emerald-500/25" },
  "in-progress": { label: "In Progress", dot: "bg-cyan-500",    pill: "bg-cyan-500/15 text-cyan-500 ring-1 ring-cyan-500/25" },
  "blocked":     { label: "Blocked",     dot: "bg-rose-500",    pill: "bg-rose-500/15 text-rose-500 ring-1 ring-rose-500/25" },
  "not-started": { label: "Not Started", dot: "bg-slate-400",   pill: "bg-slate-400/15 text-slate-400 ring-1 ring-slate-400/25" },
  "overdue":     { label: "Overdue",     dot: "bg-orange-500",  pill: "bg-orange-500/15 text-orange-500 ring-1 ring-orange-500/25" },
};

const priorityConfig: Record<string, { label: string; pill: string }> = {
  critical: { label: "Critical", pill: "bg-rose-500/20 text-rose-500 ring-1 ring-rose-500/30" },
  high:     { label: "High",     pill: "bg-orange-500/20 text-orange-500 ring-1 ring-orange-500/30" },
  medium:   { label: "Medium",   pill: "bg-amber-500/20 text-amber-500 ring-1 ring-amber-500/30" },
  low:      { label: "Low",      pill: "bg-slate-400/20 text-slate-400 ring-1 ring-slate-400/30" },
};

function QualityBar({ score }: { score: number }) {
  const color = score >= 80 ? "bg-emerald-500" : score >= 60 ? "bg-amber-500" : "bg-rose-500";
  const textColor = score >= 80 ? "text-emerald-500" : score >= 60 ? "text-amber-500" : "text-rose-500";
  return (
    <div className="flex items-center gap-2 min-w-[90px]">
      <div className="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${score}%` }} />
      </div>
      <span className={cn("text-xs font-semibold tabular-nums w-8 text-right", textColor)}>{score}%</span>
    </div>
  );
}

function QualityIcon({ score }: { score: number }) {
  if (score >= 80) return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
  if (score >= 60) return <AlertCircle  className="h-4 w-4 text-amber-500" />;
  return <XCircle className="h-4 w-4 text-rose-500" />;
}

type SortKey = "id" | "status" | "priority" | "storyPoints" | "qualityScore";
const ALL = "all";

// ── component ─────────────────────────────────────────────────────────────────

const TicketAnalysis = () => {
  const { currentProject, globalDateRange, globalPlatformFilter } = useProject();
  const projectId = currentProject?.id ?? 0;
  const isTrelloPlatform = isTrelloCompatiblePlatform(globalPlatformFilter);
  const { startDate: sd, endDate: ed } = getApiDateRange(globalDateRange);

  const { data: tickets = [], isLoading, isError } = useTickets(projectId, sd, ed, globalPlatformFilter);

  const [statusFilter,   setStatusFilter]   = useState<string>(ALL);
  const [priorityFilter, setPriorityFilter] = useState<string>(ALL);
  const [qualityFilter,  setQualityFilter]  = useState<string>(ALL);
  const [sortKey,        setSortKey]        = useState<SortKey>("id");
  const [sortAsc,        setSortAsc]        = useState(true);

  const filtered = useMemo(() => {
    let out = [...tickets];
    if (statusFilter   !== ALL) out = out.filter(t => t.status   === statusFilter);
    if (priorityFilter !== ALL) out = out.filter(t => t.priority === priorityFilter);
    if (qualityFilter === "good")  out = out.filter(t => t.qualityScore >= 80);
    if (qualityFilter === "fair")  out = out.filter(t => t.qualityScore >= 60 && t.qualityScore < 80);
    if (qualityFilter === "poor")  out = out.filter(t => t.qualityScore < 60);
    out.sort((a, b) => {
      let av: number | string = a[sortKey as keyof UITicket] as number | string;
      let bv: number | string = b[sortKey as keyof UITicket] as number | string;
      if (typeof av === "string") av = av.toLowerCase();
      if (typeof bv === "string") bv = bv.toLowerCase();
      return sortAsc ? (av < bv ? -1 : av > bv ? 1 : 0) : (av > bv ? -1 : av < bv ? 1 : 0);
    });
    return out;
  }, [tickets, statusFilter, priorityFilter, qualityFilter, sortKey, sortAsc]);

  if (!currentProject) return <EmptyProjectState title="Import a Trello board to analyze tickets" />;
  if (!isTrelloPlatform) {
    return (
      <DashboardLayout>
        <ErrorState
          message={`Ticket Analysis is currently Trello-based. Switch the platform filter from ${PLATFORM_LABELS[globalPlatformFilter]} to Trello or All Platforms.`}
        />
      </DashboardLayout>
    );
  }

  if (isLoading) return <DashboardLayout><LoadingSpinner /></DashboardLayout>;
  if (isError)   return <DashboardLayout><ErrorState /></DashboardLayout>;

  const avgQuality  = tickets.length > 0 ? Math.round(tickets.reduce((s, t) => s + t.qualityScore, 0) / tickets.length) : 0;
  const poorCount   = tickets.filter(t => t.qualityScore < 60).length;
  const fairCount   = tickets.filter(t => t.qualityScore >= 60 && t.qualityScore < 80).length;
  const goodCount   = tickets.filter(t => t.qualityScore >= 80).length;

  const allStatuses   = [...new Set(tickets.map(t => t.status))];
  const allPriorities = [...new Set(tickets.map(t => t.priority))];

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(v => !v);
    else { setSortKey(key); setSortAsc(true); }
  };

  const SortBtn = ({ k, label }: { k: SortKey; label: string }) => (
    <button
      onClick={() => toggleSort(k)}
      className="flex items-center gap-1 hover:text-foreground transition-colors"
    >
      {label}
      <ArrowUpDown className={cn("h-3 w-3", sortKey === k ? "text-primary" : "text-muted-foreground/50")} />
    </button>
  );

  const FilterChip = ({ value, active, onClick, children }: {
    value: string; active: boolean; onClick: () => void; children: React.ReactNode;
  }) => (
    <button
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1 text-xs font-medium transition-all",
        active
          ? "bg-primary text-primary-foreground shadow-sm"
          : "bg-muted text-muted-foreground hover:bg-muted/80"
      )}
    >
      {children}
    </button>
  );

  const barTotal = tickets.length || 1;

  return (
    <DashboardLayout>
      <div className="space-y-6">

        {/* KPI Summary cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Average quality */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-border bg-card px-5 py-4 shadow-sm flex items-center gap-4">
            <div className="relative shrink-0">
              <svg width={64} height={64} style={{ transform: "rotate(-90deg)" }}>
                <circle cx={32} cy={32} r={26} fill="none" stroke="currentColor" strokeWidth={7} className="text-border" />
                <circle cx={32} cy={32} r={26} fill="none"
                  stroke={avgQuality >= 80 ? "#22c55e" : avgQuality >= 60 ? "#f59e0b" : "#ef4444"}
                  strokeWidth={7}
                  strokeDasharray={`${(avgQuality / 100) * 2 * Math.PI * 26} ${2 * Math.PI * 26}`}
                  strokeLinecap="round" />
              </svg>
              <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-foreground">{avgQuality}%</span>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Average Quality</p>
              <p className={cn("text-2xl font-bold mt-0.5",
                avgQuality >= 80 ? "text-emerald-500" : avgQuality >= 60 ? "text-amber-500" : "text-rose-500"
              )}>{avgQuality >= 80 ? "Good" : avgQuality >= 60 ? "Fair" : "Poor"}</p>
              <p className="text-xs text-muted-foreground mt-0.5">across {tickets.length} tickets</p>
            </div>
          </motion.div>

          {/* Needs attention */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}
            className={cn("rounded-xl border bg-card px-5 py-4 shadow-sm", poorCount > 0 ? "border-rose-500/30 bg-rose-500/5" : "border-border")}>
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-rose-500/15">
                <AlertCircle className="h-5 w-5 text-rose-500" />
              </div>
              <div className="flex-1">
                <p className="text-xs text-muted-foreground">Needs Attention</p>
                <p className="text-2xl font-bold text-rose-500 mt-0.5">{poorCount}</p>
                <p className="text-xs text-muted-foreground mt-0.5">quality score below 60%</p>
              </div>
              {poorCount > 0 && (
                <button
                  onClick={() => setQualityFilter("poor")}
                  className="flex items-center gap-1 text-xs text-rose-500 font-medium hover:underline shrink-0 mt-1"
                >
                  Review <ChevronRight className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </motion.div>

          {/* High quality */}
          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16 }}
            className="rounded-xl border border-border bg-card px-5 py-4 shadow-sm">
            <div className="flex items-start gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500/15">
                <Star className="h-5 w-5 text-emerald-500" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">High Quality</p>
                <p className="text-2xl font-bold text-emerald-500 mt-0.5">{goodCount}</p>
                <p className="text-xs text-muted-foreground mt-0.5">scoring 80% or above</p>
              </div>
            </div>
            {/* Quality distribution stacked bar */}
            <div className="mt-4">
              <div className="flex h-2 w-full rounded-full overflow-hidden gap-0.5">
                <div className="bg-emerald-500 transition-all" style={{ width: `${(goodCount / barTotal) * 100}%` }} />
                <div className="bg-amber-500 transition-all"  style={{ width: `${(fairCount / barTotal) * 100}%` }} />
                <div className="bg-rose-500 transition-all"   style={{ width: `${(poorCount / barTotal) * 100}%` }} />
              </div>
              <div className="flex justify-between mt-1.5 text-[10px] text-muted-foreground">
                <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-emerald-500 inline-block" /> Good ({goodCount})</span>
                <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-amber-500 inline-block" /> Fair ({fairCount})</span>
                <span className="flex items-center gap-1"><span className="h-1.5 w-1.5 rounded-full bg-rose-500 inline-block" /> Poor ({poorCount})</span>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Filters */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card px-4 py-3">
          <Filter className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
          <span className="text-xs text-muted-foreground mr-1">Status:</span>
          <FilterChip value={ALL} active={statusFilter === ALL} onClick={() => setStatusFilter(ALL)}>All</FilterChip>
          {allStatuses.map(s => (
            <FilterChip key={s} value={s} active={statusFilter === s} onClick={() => setStatusFilter(s)}>
              {statusConfig[s]?.label ?? s}
            </FilterChip>
          ))}
          <span className="mx-1 h-4 w-px bg-border" />
          <span className="text-xs text-muted-foreground mr-1">Priority:</span>
          <FilterChip value={ALL} active={priorityFilter === ALL} onClick={() => setPriorityFilter(ALL)}>All</FilterChip>
          {allPriorities.map(p => (
            <FilterChip key={p} value={p} active={priorityFilter === p} onClick={() => setPriorityFilter(p)}>
              {priorityConfig[p]?.label ?? p}
            </FilterChip>
          ))}
          <span className="mx-1 h-4 w-px bg-border" />
          <span className="text-xs text-muted-foreground mr-1">Quality:</span>
          {[["all","All"], ["good","Good"], ["fair","Fair"], ["poor","Poor"]].map(([v, l]) => (
            <FilterChip key={v} value={v} active={qualityFilter === v} onClick={() => setQualityFilter(v)}>{l}</FilterChip>
          ))}
        </motion.div>

        {/* Table */}
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
          className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <PackageOpen className="h-10 w-10 text-muted-foreground/30 mb-3" />
              <p className="text-sm font-medium text-muted-foreground">No tickets match the current filters.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/30">
                    {(["Ticket / Title", "Status", "Priority", "Points", "Quality", "Labels"] as const).map((h, idx) => (
                      <th key={h} className="text-left py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                        {idx === 3 ? <SortBtn k="storyPoints" label={h} /> :
                         idx === 4 ? <SortBtn k="qualityScore" label={h} /> : h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filtered.map((t, i) => {
                    const sc = statusConfig[t.status] ?? statusConfig["not-started"];
                    const pc = priorityConfig[t.priority] ?? priorityConfig.medium;
                    return (
                      <motion.tr
                        key={t.id}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: i * 0.02 }}
                        className="hover:bg-muted/30 transition-colors group"
                      >
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2">
                            <QualityIcon score={t.qualityScore} />
                            <div>
                              <span className="font-mono text-primary text-xs">{t.id}</span>
                              <p className="text-foreground font-medium mt-0.5 max-w-[220px] truncate text-xs">{t.title}</p>
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", sc.pill)}>
                            <span className={cn("h-1.5 w-1.5 rounded-full shrink-0", sc.dot)} />
                            {sc.label}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <span className={cn("inline-flex rounded-full px-2.5 py-1 text-xs font-medium", pc.pill)}>
                            {pc.label}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <span className="flex items-center justify-center h-6 w-10 rounded-md bg-muted text-xs font-mono font-semibold text-foreground">
                            {t.storyPoints}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <QualityBar score={t.qualityScore} />
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex gap-1 flex-wrap">
                            {t.labels.length === 0 ? (
                              <span className="text-xs text-muted-foreground/50">—</span>
                            ) : t.labels.map(l => (
                              <span key={l} className="text-xs rounded-full bg-primary/10 text-primary px-2 py-0.5 font-medium">{l}</span>
                            ))}
                          </div>
                        </td>
                      </motion.tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="px-4 py-2.5 border-t border-border bg-muted/20 flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Showing {filtered.length} of {tickets.length} tickets
                </p>
                <div className="flex items-center gap-1.5">
                  <Clock className="h-3 w-3 text-muted-foreground" />
                  <span className="text-xs text-muted-foreground">Auto-refreshed</span>
                </div>
              </div>
            </div>
          )}
        </motion.div>
      </div>
    </DashboardLayout>
  );
};

export default TicketAnalysis;
