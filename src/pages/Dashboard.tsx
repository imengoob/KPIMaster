import { motion } from "framer-motion";
import { Activity, Clock, Target, AlertTriangle, Gauge, CheckCircle2, Layers } from "lucide-react";
import KpiCard from "@/components/KpiCard";
import DashboardLayout from "@/components/DashboardLayout";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";
import EmptyProjectState from "@/components/EmptyProjectState";
import { useProject } from "@/contexts/ProjectContext";
import { useCurrentSprint, useSprintKpis, useBurndown, useVelocityHistory, useBlockers } from "@/hooks/useSprintData";
import { getApiDateRange } from "@/lib/dateRange";
import { isTrelloCompatiblePlatform, PLATFORM_LABELS } from "@/lib/platforms";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, PieChart, Pie, Cell } from "recharts";
import { useQuery } from "@tanstack/react-query";
import { trelloApi } from "@/services/api/trello";
import type { BackendBoardListSummaryItem } from "@/services/api/types";

const LIST_TYPE_COLORS: Record<string, { bg: string; text: string; bar: string }> = {
  backlog: { bg: "bg-sky-500/20",     text: "text-sky-600 dark:text-sky-400",     bar: "bg-sky-500" },
  wip:     { bg: "bg-amber-500/20",   text: "text-amber-700 dark:text-amber-400", bar: "bg-amber-500" },
  done:    { bg: "bg-emerald-500/20", text: "text-emerald-700 dark:text-emerald-400", bar: "bg-emerald-500" },
  unknown: { bg: "bg-muted",          text: "text-muted-foreground", bar: "bg-muted-foreground/60" },
};

function BoardListRow({ lst, maxCount }: { lst: BackendBoardListSummaryItem; maxCount: number }) {
  const col = LIST_TYPE_COLORS[lst.list_type] ?? LIST_TYPE_COLORS.unknown;
  const widthPct = maxCount > 0 ? Math.max((lst.card_count / maxCount) * 100, lst.card_count > 0 ? 4 : 0) : 0;
  return (
    <div className="flex items-center gap-3 py-2">
      <div className="w-24 shrink-0">
        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${col.bg} ${col.text}`}>
          {lst.list_type}
        </span>
      </div>
      <span className="w-32 shrink-0 text-xs text-foreground truncate" title={lst.name}>{lst.name}</span>
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full transition-all ${col.bar}`} style={{ width: `${widthPct}%` }} />
      </div>
      <span className="w-6 shrink-0 text-right text-xs font-semibold text-foreground">{lst.card_count}</span>
    </div>
  );
}

const container = { hidden: { opacity: 0 }, show: { opacity: 1, transition: { staggerChildren: 0.06 } } };
const item = { hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } };
const CS = { contentStyle: { backgroundColor: "hsl(220,22%,12%)", border: "1px solid hsl(220,18%,22%)", borderRadius: "8px", fontSize: 12, color: "hsl(220,10%,85%)" } };

const Dashboard = () => {
  const { currentProject, globalDateRange, globalPlatformFilter } = useProject();
  const pid = currentProject?.id ?? 0;
  const isTrelloPlatform = isTrelloCompatiblePlatform(globalPlatformFilter);
  const { startDate: sd, endDate: ed } = getApiDateRange(globalDateRange);
  const sprintQ   = useCurrentSprint(pid, sd, ed);
  const kpiQ      = useSprintKpis(pid, sd, ed);
  const burndownQ = useBurndown(pid, sd, ed);
  const velocityQ = useVelocityHistory(pid, sd, ed);
  const blockersQ = useBlockers(pid, sd, ed, globalPlatformFilter);

  const boardSummaryQ = useQuery({
    queryKey: ["boardSummary", pid, sd, ed],
    queryFn: () => trelloApi.getProjectBoardSummary(pid, sd, ed),
    staleTime: 60_000,
    retry: false,
    enabled: pid > 0 && isTrelloPlatform,
  });

  if (!currentProject) return <EmptyProjectState />;
  if (!isTrelloPlatform) {
    return (
      <DashboardLayout>
        <ErrorState
          message={`Dashboard currently shows Trello sprint data. Switch the platform filter from ${PLATFORM_LABELS[globalPlatformFilter]} to Trello or All Platforms.`}
        />
      </DashboardLayout>
    );
  }

  if (sprintQ.isLoading || kpiQ.isLoading) return <DashboardLayout><LoadingSpinner /></DashboardLayout>;
  if (sprintQ.isError || kpiQ.isError)     return <DashboardLayout><ErrorState /></DashboardLayout>;

  const sprint   = sprintQ.data!;
  const kpi      = kpiQ.data!;
  const burndown = burndownQ.data ?? [];
  const velocity = velocityQ.data ?? [];
  const blockers = blockersQ.data ?? [];
  const boardSummary = boardSummaryQ.data ?? null;

  const pct = sprint.totalTickets > 0 ? Math.round((sprint.completedTickets / sprint.totalTickets) * 100) : 0;
  const pieData = [
    { name: "Completed",   value: sprint.completedTickets,  color: "hsl(150,60%,45%)" },
    { name: "In Progress", value: sprint.inProgressTickets, color: "hsl(190,95%,45%)" },
    { name: "Not Started", value: sprint.notStartedTickets, color: "hsl(220,10%,68%)" },
    { name: "Blocked",     value: sprint.blockedTickets,    color: "hsl(0,72%,55%)" },
  ];

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">{sprint.name} — {currentProject.name}</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {sprint.startDate} → {sprint.endDate} · {sprint.daysRemaining === 0 ? "Sprint ends today" : `${sprint.daysRemaining} days remaining`}
            </p>
          </div>
        </div>

        <motion.div variants={container} initial="hidden" animate="show" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
          <motion.div variants={item}><KpiCard title="Velocity"   value={kpi.velocity.value}           change={kpi.velocity.change}           changeType={kpi.velocity.type}           icon={Gauge} /></motion.div>
          <motion.div variants={item}><KpiCard title="Cycle Time" value={kpi.cycleTime.value}          change={kpi.cycleTime.change}          changeType={kpi.cycleTime.type}          icon={Clock} /></motion.div>
          <motion.div variants={item}><KpiCard title="Lead Time"  value={kpi.leadTime.value}           change={kpi.leadTime.change}           changeType={kpi.leadTime.type}           icon={Activity} /></motion.div>
          <motion.div variants={item}><KpiCard title="Estimation" value={kpi.estimationAccuracy.value} change={kpi.estimationAccuracy.change} changeType={kpi.estimationAccuracy.type} icon={Target} /></motion.div>
          <motion.div variants={item}><KpiCard title="Blockers"   value={kpi.blockedCount.value}       change={kpi.blockedCount.change}       changeType={kpi.blockedCount.type}       icon={AlertTriangle} /></motion.div>
          <motion.div variants={item}><KpiCard title="Completion" value={kpi.completionRate.value}     change={kpi.completionRate.change}     changeType={kpi.completionRate.type}     icon={CheckCircle2} /></motion.div>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="lg:col-span-2 glass-card rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Sprint Burndown</h3>
            {burndown.length === 0 ? (
              <p className="text-xs text-muted-foreground py-8 text-center">No burndown data yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={burndown}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(220,15%,22%)" />
                  <XAxis dataKey="day" tick={{ fontSize: 11, fill: "hsl(220,10%,68%)" }} />
                  <YAxis tick={{ fontSize: 11, fill: "hsl(220,10%,68%)" }} />
                  <Tooltip {...CS} />
                  <Area type="monotone" dataKey="ideal"  stroke="hsl(220,10%,40%)" fill="none" strokeDasharray="5 5" />
                  <Area type="monotone" dataKey="actual" stroke="hsl(190,95%,45%)" fill="hsl(190,95%,45%)" fillOpacity={0.1} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }} className="glass-card rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Sprint Progress</h3>
            <div className="flex flex-col items-center">
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={3} dataKey="value">
                    {pieData.map((e, i) => <Cell key={i} fill={e.color} />)}
                  </Pie>
                  <Tooltip {...CS} />
                </PieChart>
              </ResponsiveContainer>
              <p className="text-3xl font-bold text-gradient">{pct}%</p>
              <p className="text-xs text-muted-foreground">{sprint.completedTickets}/{sprint.totalTickets} tickets completed</p>
              <div className="flex flex-wrap gap-2 mt-3 justify-center">
                {pieData.map(d => (
                  <div key={d.name} className="flex items-center gap-1.5 text-xs text-foreground/80">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: d.color }} />
                    {d.name} ({d.value})
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="glass-card rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4">Velocity Trend</h3>
            {velocity.length === 0 ? (
              <p className="text-xs text-muted-foreground py-8 text-center">No completed sprints yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={velocity}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(220,15%,22%)" />
                  <XAxis dataKey="sprint" tick={{ fontSize: 10, fill: "hsl(220,10%,68%)" }} />
                  <YAxis tick={{ fontSize: 11, fill: "hsl(220,10%,68%)" }} />
                  <Tooltip {...CS} />
                  <Bar dataKey="points" fill="hsl(190,95%,45%)" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }} className="glass-card rounded-xl p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-destructive" />
              Active Blockers
            </h3>
            {blockers.length === 0 ? (
              <p className="text-xs text-muted-foreground py-4 text-center">No active blockers.</p>
            ) : (
              <div className="space-y-3">
                {blockers.slice(0, 3).map(b => (
                  <div key={b.id} className="rounded-lg border border-destructive/40 bg-destructive/10 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-mono text-primary">{b.ticketId}</span>
                      <span className="text-xs font-medium text-destructive">Level {b.escalationLevel} · {b.stalledHours}h</span>
                    </div>
                    <p className="text-sm font-medium text-foreground">{b.title}</p>
                    <p className="text-xs text-muted-foreground mt-1">{b.reason}</p>
                    <p className="text-xs text-warning mt-1">Impact: {b.impact}</p>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        </div>

        {boardSummary && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.7 }} className="glass-card rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Layers className="h-4 w-4 text-primary" />
                Board Lists — {boardSummary.board_name}
              </h3>
              <div className="flex items-center gap-3 text-xs text-foreground/70">
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-sky-500" />
                  Backlog&nbsp;<strong className="text-foreground">{boardSummary.backlog_count}</strong>
                </span>
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-amber-500" />
                  WIP&nbsp;<strong className="text-foreground">{boardSummary.wip_count}</strong>
                </span>
                <span className="flex items-center gap-1">
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  Done&nbsp;<strong className="text-foreground">{boardSummary.done_count}</strong>
                </span>
                <span className="text-muted-foreground/60">|</span>
                <span>
                  Completion&nbsp;
                  <strong className="text-emerald-400">{Math.round(boardSummary.completion_rate * 100)}%</strong>
                </span>
              </div>
            </div>
            <div className="divide-y divide-border">
              {boardSummary.lists.map(lst => (
                <BoardListRow
                  key={lst.list_id}
                  lst={lst}
                  maxCount={Math.max(...boardSummary.lists.map(l => l.card_count), 1)}
                />
              ))}
            </div>
          </motion.div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default Dashboard;
