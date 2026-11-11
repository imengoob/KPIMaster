import DashboardLayout from "@/components/DashboardLayout";
import EmptyProjectState from "@/components/EmptyProjectState";
import ErrorState from "@/components/ErrorState";
import LoadingSpinner from "@/components/LoadingSpinner";
import { useProject } from "@/contexts/ProjectContext";
import { getApiDateRange } from "@/lib/dateRange";
import { cn } from "@/lib/utils";
import { developerApi } from "@/services/api/developers";
import type {
  BackendClientProgressMember,
  BackendClientProgressReport,
} from "@/services/api/types";
import { useQuery } from "@tanstack/react-query";
import type { ElementType } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  ShieldAlert,
  TrendingUp,
  Users,
} from "lucide-react";

const STATUS = {
  "on-track": {
    label: "On Track",
    pill: "bg-emerald-500/12 text-emerald-600 ring-1 ring-emerald-500/20",
    accent: "text-emerald-600",
    border: "border-emerald-500/25",
  },
  "at-risk": {
    label: "At Risk",
    pill: "bg-amber-500/12 text-amber-600 ring-1 ring-amber-500/20",
    accent: "text-amber-600",
    border: "border-amber-500/25",
  },
  "behind": {
    label: "Behind",
    pill: "bg-rose-500/12 text-rose-600 ring-1 ring-rose-500/20",
    accent: "text-rose-600",
    border: "border-rose-500/25",
  },
} as const;

const FRESHNESS = {
  active: "bg-cyan-500/10 text-cyan-700",
  recent: "bg-sky-500/10 text-sky-700",
  stale: "bg-muted text-muted-foreground",
  unknown: "bg-muted text-muted-foreground",
} as const;

const fmtPct = (value: number) => `${Math.round(value * 100)}%`;
const fmtHours = (value: number | null) => {
  if (value == null) return "—";
  return value < 24 ? `${value.toFixed(1)}h` : `${(value / 24).toFixed(1)}d`;
};

function relativeTime(iso: string | null) {
  if (!iso) return "No recent activity";
  const deltaHours = (Date.now() - new Date(iso).getTime()) / 36e5;
  if (deltaHours < 1) return "Updated less than 1h ago";
  if (deltaHours < 24) return `Updated ${Math.round(deltaHours)}h ago`;
  const days = Math.round(deltaHours / 24);
  return `Updated ${days}d ago`;
}

function initials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

function Meter({
  label,
  done,
  total,
  colorClass,
}: {
  label: string;
  done: number;
  total: number;
  colorClass: string;
}) {
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
        <span>{label}</span>
        <span className="font-medium text-foreground">{done}/{total}</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div className={cn("h-full rounded-full transition-all duration-500", colorClass)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function SummaryCard({
  title,
  value,
  caption,
  Icon,
  tone = "text-foreground",
}: {
  title: string;
  value: string;
  caption: string;
  Icon: ElementType;
  tone?: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card px-4 py-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
          <p className={cn("mt-2 text-2xl font-bold tracking-tight", tone)}>{value}</p>
          <p className="mt-1 text-xs text-muted-foreground">{caption}</p>
        </div>
        <div className="rounded-xl bg-muted/70 p-2.5">
          <Icon className="h-4 w-4 text-muted-foreground" />
        </div>
      </div>
    </div>
  );
}

function MemberCard({ member }: { member: BackendClientProgressMember }) {
  const status = STATUS[member.status];
  const freshnessClass = FRESHNESS[member.activity_freshness];

  return (
    <article className={cn("rounded-2xl border bg-card shadow-sm overflow-hidden", status.border)}>
      <div className="border-b border-border bg-gradient-to-r from-background via-background to-muted/30 px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500 to-blue-600 text-sm font-bold text-white shadow-sm">
              {initials(member.developer_name)}
            </div>
            <div className="min-w-0">
              <h3 className="truncate text-base font-semibold text-foreground">{member.developer_name}</h3>
              <p className="text-xs capitalize text-muted-foreground">{member.role}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className={cn("inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold", freshnessClass)}>
              {relativeTime(member.latest_activity_at)}
            </span>
            <span className={cn("inline-flex rounded-full px-2.5 py-1 text-[11px] font-semibold", status.pill)}>
              {status.label}
            </span>
          </div>
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        <div className="grid gap-4 lg:grid-cols-[1.35fr,1fr]">
          <div className="space-y-3">
            <Meter
              label="Completed tickets"
              done={member.tickets_completed}
              total={member.tickets_total}
              colorClass="bg-cyan-500"
            />
            <Meter
              label="Delivered story points"
              done={member.story_points_completed}
              total={member.story_points_total}
              colorClass="bg-emerald-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-xl border border-border bg-muted/30 px-3 py-3">
              <p className="text-[11px] text-muted-foreground">Active work</p>
              <p className="mt-1 text-lg font-bold text-foreground">{member.active_work_items}</p>
            </div>
            <div className="rounded-xl border border-border bg-muted/30 px-3 py-3">
              <p className="text-[11px] text-muted-foreground">Blockers</p>
              <p className={cn("mt-1 text-lg font-bold", member.active_blockers > 0 ? "text-rose-600" : "text-foreground")}>
                {member.active_blockers}
              </p>
            </div>
            <div className="rounded-xl border border-border bg-muted/30 px-3 py-3">
              <p className="text-[11px] text-muted-foreground">Cycle time</p>
              <p className="mt-1 text-lg font-bold text-foreground">{fmtHours(member.avg_cycle_time_hours)}</p>
            </div>
            <div className="rounded-xl border border-border bg-muted/30 px-3 py-3">
              <p className="text-[11px] text-muted-foreground">Delivery ratio</p>
              <p className="mt-1 text-lg font-bold text-foreground">
                {member.tickets_total > 0 ? fmtPct(member.tickets_completed / member.tickets_total) : "0%"}
              </p>
            </div>
          </div>
        </div>

        <div className={cn(
          "rounded-xl border px-3.5 py-3 text-sm",
          member.risk_note
            ? "border-amber-500/25 bg-amber-500/8 text-amber-700"
            : "border-emerald-500/20 bg-emerald-500/8 text-emerald-700",
        )}>
          <span className="font-semibold">{member.risk_note ? "Delivery note:" : "Delivery note:"}</span>{" "}
          {member.risk_note ?? "Delivery is moving as expected for this developer."}
        </div>
      </div>
    </article>
  );
}

const ClientProgress = () => {
  const { currentProject, globalDateRange, globalPlatformFilter } = useProject();
  const projectId = currentProject?.id ?? 0;
  const { startDate, endDate } = getApiDateRange(globalDateRange);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["client-progress", projectId, startDate, endDate, globalPlatformFilter],
    queryFn: () => developerApi.getClientProgress(projectId, undefined, startDate, endDate, globalPlatformFilter),
    staleTime: 60_000,
    enabled: projectId > 0,
  });

  if (!currentProject) {
    return <EmptyProjectState title="Import a Trello board to open the client delivery dashboard" />;
  }

  if (isLoading) return <DashboardLayout><LoadingSpinner /></DashboardLayout>;
  if (isError || !data) return <DashboardLayout><ErrorState /></DashboardLayout>;

  const report = data as BackendClientProgressReport;
  const { summary, members } = report;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <section className="rounded-[28px] border border-border bg-gradient-to-br from-cyan-500/[0.08] via-background to-emerald-500/[0.08] px-5 py-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-2xl">
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-muted-foreground">Client Delivery View</p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-foreground">Client Progress for {currentProject.name}</h2>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                A client-ready view of delivery progress, completion pace, and current risks across the developers assigned to this engagement.
              </p>
            </div>
            <div className="rounded-2xl border border-border bg-background/80 px-4 py-3 text-right shadow-sm">
              <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Last updated</p>
              <p className="mt-1 text-sm font-semibold text-foreground">
                {new Date(summary.last_updated_at).toLocaleString()}
              </p>
            </div>
          </div>
        </section>

        <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <SummaryCard
            title="Developers"
            value={String(summary.total_developers)}
            caption={`${summary.on_track_count} on track, ${summary.at_risk_count} at risk, ${summary.behind_count} behind`}
            Icon={Users}
          />
          <SummaryCard
            title="Completion"
            value={fmtPct(summary.overall_completion_rate)}
            caption={`${summary.story_points_completed}/${summary.story_points_total} story points delivered`}
            Icon={TrendingUp}
            tone="text-cyan-600"
          />
          <SummaryCard
            title="Active Blockers"
            value={String(summary.active_blockers)}
            caption={summary.active_blockers > 0 ? "Delivery risk needs follow-up" : "No blocked work right now"}
            Icon={ShieldAlert}
            tone={summary.active_blockers > 0 ? "text-rose-600" : "text-foreground"}
          />
          <SummaryCard
            title="Average Cycle Time"
            value={fmtHours(summary.avg_cycle_time_hours)}
            caption="Average time to move work to done"
            Icon={Clock3}
          />
          <SummaryCard
            title="On Track"
            value={String(summary.on_track_count)}
            caption="Developers progressing to plan"
            Icon={CheckCircle2}
            tone="text-emerald-600"
          />
          <SummaryCard
            title="Attention Needed"
            value={String(summary.at_risk_count + summary.behind_count)}
            caption="Developers requiring follow-up"
            Icon={AlertTriangle}
            tone={(summary.at_risk_count + summary.behind_count) > 0 ? "text-amber-600" : "text-foreground"}
          />
        </section>

        {members.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-border bg-card py-16 text-center">
            <Activity className="h-10 w-10 text-muted-foreground/30" />
            <p className="mt-3 text-sm font-medium text-muted-foreground">No assigned developer work is available for this project yet.</p>
            <p className="mt-1 text-xs text-muted-foreground/70">Once cards are assigned in Trello, this client delivery view will populate automatically.</p>
          </div>
        ) : (
          <section className="space-y-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-semibold text-foreground">Developer delivery status</h3>
                <p className="text-sm text-muted-foreground">Each card summarizes delivery progress, active work, and current risk in client-friendly language.</p>
              </div>
            </div>
            <div className="grid gap-4 xl:grid-cols-2">
              {members.map((member) => (
                <MemberCard key={member.developer_id} member={member} />
              ))}
            </div>
          </section>
        )}

        <p className="text-[11px] text-muted-foreground/70">
          Report generated {new Date(report.computed_at).toLocaleString()} from the current project board data.
        </p>
      </div>
    </DashboardLayout>
  );
};

export default ClientProgress;
