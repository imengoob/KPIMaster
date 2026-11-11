import { motion } from "framer-motion";
import DashboardLayout from "@/components/DashboardLayout";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";
import EmptyProjectState from "@/components/EmptyProjectState";
import { useProject } from "@/contexts/ProjectContext";
import { useCurrentSprint, useBurndown, useSprintKpis, useTickets } from "@/hooks/useSprintData";
import { getApiDateRange } from "@/lib/dateRange";
import { isTrelloCompatiblePlatform, PLATFORM_LABELS } from "@/lib/platforms";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer,
} from "recharts";
import {
  Calendar, Clock, TrendingUp, CheckCircle2, Play,
  ShieldAlert, AlertTriangle, PackageOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { UITicket } from "@/services/api/types";

// ── helpers ───────────────────────────────────────────────────────────────────

const CS = {
  contentStyle: {
    backgroundColor: "hsl(220,22%,9%)",
    border: "1px solid hsl(220,18%,15%)",
    borderRadius: "10px",
    fontSize: 12,
    padding: "8px 12px",
  },
};

const groupConfig = {
  completed:    { label: "Completed",   Icon: CheckCircle2, dot: "bg-emerald-500", pill: "bg-emerald-500/15 text-emerald-500", border: "border-emerald-500/30", card: "bg-emerald-500/5" },
  "in-progress":{ label: "In Progress", Icon: Play,         dot: "bg-cyan-500",    pill: "bg-cyan-500/15 text-cyan-500",       border: "border-cyan-500/30",    card: "bg-cyan-500/5" },
  blocked:      { label: "Blocked",     Icon: ShieldAlert,  dot: "bg-rose-500",    pill: "bg-rose-500/15 text-rose-500",       border: "border-rose-500/30",    card: "bg-rose-500/5" },
  overdue:      { label: "Overdue",     Icon: AlertTriangle,dot: "bg-orange-500",  pill: "bg-orange-500/15 text-orange-500",   border: "border-orange-500/30",  card: "bg-orange-500/5" },
} as const;

function KpiTile({
  icon: Icon, label, value, sub, color = "text-foreground",
}: {
  icon: React.ElementType; label: string; value: string | number; sub?: string; color?: string;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-4 rounded-xl border border-border bg-card px-5 py-4 shadow-sm">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
        <Icon className="h-5 w-5 text-primary" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className={cn("text-2xl font-bold leading-tight mt-0.5", color)}>{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-0.5 truncate">{sub}</p>}
      </div>
    </motion.div>
  );
}

function TicketChip({ t }: { t: UITicket }) {
  return (
    <div className="rounded-lg border border-border/60 bg-background/60 p-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-primary text-[11px] font-semibold">{t.id}</span>
        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">{t.storyPoints}pt</span>
      </div>
      <p className="text-xs text-foreground font-medium mt-1 truncate leading-snug">{t.title}</p>
    </div>
  );
}

// ── page ─────────────────────────────────────────────────────────────────────

const SprintMonitor = () => {
  const { currentProject, globalDateRange, globalPlatformFilter } = useProject();
  const pid = currentProject?.id ?? 0;
  const isTrelloPlatform = isTrelloCompatiblePlatform(globalPlatformFilter);
  const { startDate: sd, endDate: ed } = getApiDateRange(globalDateRange);
  const sprintQ  = useCurrentSprint(pid, sd, ed);
  const burndownQ= useBurndown(pid, sd, ed);
  const kpiQ     = useSprintKpis(pid, sd, ed);
  const ticketsQ = useTickets(pid, sd, ed, globalPlatformFilter);

  if (!currentProject) return <EmptyProjectState title="Import a Trello board to monitor sprint flow" />;
  if (!isTrelloPlatform) {
    return (
      <DashboardLayout>
        <ErrorState
          message={`Sprint Monitor currently supports Trello board flow. Switch the platform filter from ${PLATFORM_LABELS[globalPlatformFilter]} to Trello or All Platforms.`}
        />
      </DashboardLayout>
    );
  }

  if (sprintQ.isLoading) return <DashboardLayout><LoadingSpinner /></DashboardLayout>;
  if (sprintQ.isError)   return <DashboardLayout><ErrorState /></DashboardLayout>;

  const sprint   = sprintQ.data!;
  const burndown = burndownQ.data ?? [];
  const kpi      = kpiQ.data;
  const tickets  = ticketsQ.data ?? [];

  const groups: Record<string, UITicket[]> = {
    completed:     tickets.filter(t => t.status === "completed"),
    "in-progress": tickets.filter(t => t.status === "in-progress"),
    blocked:       tickets.filter(t => t.status === "blocked"),
    overdue:       tickets.filter(t => t.status === "overdue"),
  };

  const pct = sprint.totalTickets > 0
    ? Math.round((sprint.completedTickets / sprint.totalTickets) * 100) : 0;

  // Calculate Sprint Health (Lag vs Expected Pace)
  const getSprintHealth = () => {
    if (!sprint.startDate || !sprint.endDate) return { status: "unknown", color: "text-foreground", fill: "currentColor", hex: "#94a3b8" };
    const start = new Date(sprint.startDate).getTime();
    const end = new Date(sprint.endDate).getTime();
    const now = Date.now();
    const totalTime = end - start;
    if (totalTime <= 0) return { status: "unknown", color: "text-foreground", fill: "currentColor", hex: "#94a3b8" };
    
    // clamp between 0 and 100
    const timeElapsedPct = Math.max(0, Math.min(100, Math.round(((now - start) / totalTime) * 100)));
    const lagPct = timeElapsedPct - pct;

    if (lagPct > 20 || (now > end && pct < 100)) {
      return { status: "late", color: "text-rose-500", fill: "bg-rose-500", hex: "#ef4444" };
    } else if (lagPct > 0) {
      return { status: "behind", color: "text-orange-500", fill: "bg-orange-500", hex: "#f97316" };
    } else {
      return { status: "on-track", color: "text-emerald-500", fill: "bg-emerald-500", hex: "#10b981" };
    }
  };

  const health = getSprintHealth();

  // Sprint progress ring data
  const ringR = 44;
  const ringCirc = 2 * Math.PI * ringR;
  const ringDash = (pct / 100) * ringCirc;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Sprint name banner */}
        <div className="flex items-center justify-between gap-4 rounded-xl border border-border bg-card px-5 py-3 shadow-sm">
          <div>
            <p className="text-xs text-muted-foreground">Active Sprint</p>
            <p className="text-base font-semibold text-foreground mt-0.5">{sprint.name}</p>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Calendar className="h-3.5 w-3.5" />
            {sprint.startDate} → {sprint.endDate}
          </div>
        </div>

        {/* KPI tiles */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <KpiTile
            icon={TrendingUp} label="Sprint Progress"
            value={`${pct}%`}
            sub={`${sprint.completedTickets} of ${sprint.totalTickets} tickets done`}
            color={health.color}
          />
          <KpiTile
            icon={Calendar} label="Days Remaining"
            value={sprint.daysRemaining === 0 ? "Today" : sprint.daysRemaining < 0 ? "Ended" : sprint.daysRemaining}
            sub={health.status === "late" ? "Sprint is significantly behind schedule" : health.status === "behind" ? "Sprint is slightly behind schedule" : "Sprint is progressing well"}
            color={sprint.daysRemaining <= 2 ? "text-rose-500" : "text-foreground"}
          />
          <KpiTile
            icon={Clock} label="Avg Cycle Time"
            value={kpi?.cycleTime.value ?? "—"}
            sub={kpi?.cycleTime.change}
          />
        </div>

        {/* Burndown chart + sprint ring */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-4">
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
            className="rounded-xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-foreground">Sprint Burndown</h3>
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-0.5 w-6 border-t-2 border-dashed border-muted-foreground/50" /> Ideal
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-0.5 w-6 bg-primary/70 rounded" /> Actual
                </span>
              </div>
            </div>
            {burndown.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <PackageOpen className="h-8 w-8 text-muted-foreground/30 mb-2" />
                <p className="text-xs text-muted-foreground">No burndown data yet.</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={burndown} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="actualGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="hsl(190,95%,45%)" stopOpacity={0.2} />
                      <stop offset="95%" stopColor="hsl(190,95%,45%)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(220,18%,15%)" />
                  <XAxis dataKey="day" tick={{ fontSize: 11, fill: "hsl(220,10%,55%)" }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: "hsl(220,10%,55%)" }} axisLine={false} tickLine={false} width={32} />
                  <Tooltip {...CS} />
                  <Area type="monotone" dataKey="ideal"  stroke="hsl(220,10%,40%)" fill="none" strokeDasharray="5 5" name="Ideal pace" strokeWidth={1.5} />
                  <Area type="monotone" dataKey="actual" stroke="hsl(190,95%,45%)" fill="url(#actualGrad)" name="Actual remaining" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </motion.div>

          {/* Sprint progress ring */}
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
            className="flex flex-col items-center justify-center rounded-xl border border-border bg-card p-6 shadow-sm min-w-[160px]">
            <div className="relative">
              <svg width={112} height={112} style={{ transform: "rotate(-90deg)" }}>
                <circle cx={56} cy={56} r={ringR} fill="none" stroke="currentColor" strokeWidth={9} className="text-border" />
                <circle cx={56} cy={56} r={ringR} fill="none"
                  stroke={health.hex}
                  strokeWidth={9}
                  strokeDasharray={`${ringDash} ${ringCirc}`}
                  strokeLinecap="round"
                  style={{ transition: "stroke-dasharray 0.8s ease" }}
                />
              </svg>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className={cn("text-2xl font-bold", health.color)}>{pct}%</span>
              </div>
            </div>
            <p className="text-xs font-medium text-foreground mt-3">Sprint Progress</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {sprint.completedTickets}/{sprint.totalTickets} tickets
            </p>
            <div className="flex flex-col gap-1.5 mt-4 w-full">
              {[
                { label: "Done",     val: sprint.completedTickets,  color: "bg-emerald-500" },
                { label: "Active",   val: sprint.inProgressTickets, color: "bg-cyan-500" },
                { label: "Blocked",  val: sprint.blockedTickets,    color: "bg-rose-500" },
                { label: "Pending",  val: sprint.notStartedTickets, color: "bg-slate-400" },
              ].map(row => (
                <div key={row.label} className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-muted-foreground">
                    <span className={cn("h-1.5 w-1.5 rounded-full", row.color)} />{row.label}
                  </span>
                  <span className="font-semibold text-foreground tabular-nums">{row.val}</span>
                </div>
              ))}
            </div>
          </motion.div>
        </div>

        {/* Ticket breakdown by status */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {(["completed", "in-progress", "blocked", "overdue"] as const).map((status, si) => {
            const cfg = groupConfig[status];
            const Icon = cfg.Icon;
            const group = groups[status];
            return (
              <motion.div
                key={status}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 + si * 0.07 }}
                className={cn("rounded-xl border shadow-sm overflow-hidden", cfg.border, cfg.card)}
              >
                {/* Column header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
                  <span className={cn("inline-flex items-center gap-1.5 text-xs font-semibold rounded-full px-2.5 py-1", cfg.pill)}>
                    <Icon className="h-3.5 w-3.5" />
                    {cfg.label}
                  </span>
                  <span className="text-sm font-bold text-foreground">{group.length}</span>
                </div>

                {/* Ticket list */}
                <div className="px-3 py-3 space-y-2 max-h-72 overflow-y-auto">
                  {group.length === 0 ? (
                    <div className="flex flex-col items-center py-5 text-center">
                      <PackageOpen className="h-6 w-6 text-muted-foreground/30 mb-1.5" />
                      <p className="text-xs text-muted-foreground">
                        {status === "overdue" ? "Nothing overdue" : `No ${cfg.label.toLowerCase()} tickets`}
                      </p>
                    </div>
                  ) : (
                    group.map(t => <TicketChip key={t.id} t={t} />)
                  )}
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </DashboardLayout>
  );
};

export default SprintMonitor;
