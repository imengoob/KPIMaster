import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  Clock3,
  FileCheck2,
  Filter,
  GitBranch,
  ListChecks,
  Loader2,
  Plug,
  ShieldCheck,
  UserRoundCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import DashboardLayout from "@/components/DashboardLayout";
import EmptyProjectState from "@/components/EmptyProjectState";
import ErrorState from "@/components/ErrorState";
import LoadingSpinner from "@/components/LoadingSpinner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/use-toast";
import { useProject } from "@/contexts/ProjectContext";
import { cn } from "@/lib/utils";
import { actionApi } from "@/services/api/actions";
import type { BackendActionItem, BackendActionPriority, BackendActionStatus } from "@/services/api/types";

type ActionView = "project" | "mine" | "critical" | "resolved";

const sourceConfig: Record<string, { label: string; Icon: LucideIcon; className: string }> = {
  blocker: {
    label: "Blocker",
    Icon: AlertTriangle,
    className: "bg-rose-500/15 text-rose-500 ring-1 ring-rose-500/25",
  },
  ticket_quality: {
    label: "Ticket Quality",
    Icon: FileCheck2,
    className: "bg-amber-500/15 text-amber-500 ring-1 ring-amber-500/25",
  },
  repository_mismatch: {
    label: "Repository",
    Icon: GitBranch,
    className: "bg-cyan-500/15 text-cyan-500 ring-1 ring-cyan-500/25",
  },
  integration_health: {
    label: "Integration",
    Icon: Plug,
    className: "bg-violet-500/15 text-violet-500 ring-1 ring-violet-500/25",
  },
};

const priorityConfig: Record<BackendActionPriority, { label: string; className: string }> = {
  critical: { label: "Critical", className: "bg-rose-500 text-white" },
  high: { label: "High", className: "bg-orange-500/15 text-orange-500 ring-1 ring-orange-500/30" },
  medium: { label: "Medium", className: "bg-amber-500/15 text-amber-500 ring-1 ring-amber-500/30" },
  low: { label: "Low", className: "bg-muted text-muted-foreground" },
};

const statusConfig: Record<BackendActionStatus, { label: string; className: string; Icon: LucideIcon }> = {
  open: { label: "Open", className: "bg-muted text-muted-foreground", Icon: CircleDot },
  acknowledged: { label: "Acknowledged", className: "bg-cyan-500/15 text-cyan-500", Icon: UserRoundCheck },
  in_progress: { label: "In Progress", className: "bg-primary/15 text-primary", Icon: Loader2 },
  awaiting_approval: { label: "Awaiting Approval", className: "bg-amber-500/15 text-amber-500", Icon: ShieldCheck },
  approved: { label: "Approved", className: "bg-emerald-500/15 text-emerald-500", Icon: ShieldCheck },
  rejected: { label: "Rejected", className: "bg-rose-500/15 text-rose-500", Icon: XCircle },
  resolved: { label: "Resolved", className: "bg-emerald-500/15 text-emerald-500", Icon: CheckCircle2 },
  dismissed: { label: "Dismissed", className: "bg-muted text-muted-foreground", Icon: XCircle },
};

const sourceOptions = [
  { value: "all", label: "All sources" },
  { value: "blocker", label: "Blockers" },
  { value: "ticket_quality", label: "Ticket quality" },
  { value: "repository_mismatch", label: "Repository" },
  { value: "integration_health", label: "Integrations" },
];

const statCards: Array<{ label: string; key: "open" | "critical" | "approvals" | "overdue"; Icon: LucideIcon; color: string }> = [
  { label: "Open", key: "open", Icon: CircleDot, color: "text-primary" },
  { label: "Critical", key: "critical", Icon: AlertTriangle, color: "text-rose-500" },
  { label: "Approvals", key: "approvals", Icon: ShieldCheck, color: "text-amber-500" },
  { label: "Overdue", key: "overdue", Icon: Clock3, color: "text-orange-500" },
];

function formatDateTime(value: string | null): string {
  if (!value) return "No due date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "No due date";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function isOverdue(action: BackendActionItem): boolean {
  return Boolean(
    action.due_at &&
      !["resolved", "dismissed"].includes(action.status) &&
      new Date(action.due_at).getTime() < Date.now(),
  );
}

function SourceBadge({ source }: { source: string }) {
  const cfg = sourceConfig[source] ?? {
    label: source.replace("_", " "),
    Icon: ListChecks,
    className: "bg-muted text-muted-foreground",
  };
  const Icon = cfg.Icon;
  return (
    <span className={cn("inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium", cfg.className)}>
      <Icon className="h-3.5 w-3.5" />
      {cfg.label}
    </span>
  );
}

function StatusBadge({ status }: { status: BackendActionStatus }) {
  const cfg = statusConfig[status];
  const Icon = cfg.Icon;
  return (
    <span className={cn("inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium", cfg.className)}>
      <Icon className={cn("h-3.5 w-3.5", status === "in_progress" && "animate-spin")} />
      {cfg.label}
    </span>
  );
}

function PriorityBadge({ priority }: { priority: BackendActionPriority }) {
  const cfg = priorityConfig[priority];
  return <span className={cn("inline-flex h-7 items-center rounded-md px-2 text-xs font-semibold", cfg.className)}>{cfg.label}</span>;
}

const Actions = () => {
  const { currentProject } = useProject();
  const projectId = currentProject?.id ?? 0;
  const queryClient = useQueryClient();
  const { toast } = useToast();

  const [view, setView] = useState<ActionView>("project");
  const [sourceType, setSourceType] = useState("all");
  const [selectedActionId, setSelectedActionId] = useState<number | null>(null);
  const [note, setNote] = useState("");

  const includeResolved = view === "resolved";
  const actionsQuery = useQuery({
    queryKey: ["actions", projectId, view, sourceType],
    queryFn: () =>
      actionApi.list({
        projectId,
        owner: view === "mine" ? "mine" : "all",
        includeResolved,
        status: view === "resolved" ? "resolved" : "all",
        sourceType,
      }),
    enabled: projectId > 0,
    staleTime: 60_000,
  });

  const detailQuery = useQuery({
    queryKey: ["actions", "detail", selectedActionId],
    queryFn: () => actionApi.get(selectedActionId as number),
    enabled: selectedActionId !== null,
  });

  const generateMutation = useMutation({
    mutationFn: () => actionApi.generate(projectId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["actions"] });
      toast({
        title: "Actions refreshed",
        description: `${result.generated} new, ${result.refreshed} refreshed, ${result.total_open} open.`,
      });
    },
    onError: () => {
      toast({ title: "Could not generate actions", variant: "destructive" });
    },
  });

  const transitionMutation = useMutation({
    mutationFn: ({ id, transition, note }: { id: number; transition: Parameters<typeof actionApi.transition>[1]; note?: string }) =>
      actionApi.transition(id, transition, note),
    onSuccess: (updated) => {
      setNote("");
      setSelectedActionId(updated.id);
      queryClient.invalidateQueries({ queryKey: ["actions"] });
      toast({ title: "Action updated", description: statusConfig[updated.status].label });
    },
    onError: () => {
      toast({ title: "Could not update action", variant: "destructive" });
    },
  });

  const allActions = useMemo(() => actionsQuery.data ?? [], [actionsQuery.data]);
  const actions = useMemo(() => {
    const list = view === "critical"
      ? allActions.filter((action) => action.priority === "critical" || isOverdue(action))
      : allActions;
    return [...list].sort((a, b) => {
      const p = { critical: 0, high: 1, medium: 2, low: 3 };
      const byPriority = p[a.priority] - p[b.priority];
      if (byPriority !== 0) return byPriority;
      return (a.due_at ?? "9999").localeCompare(b.due_at ?? "9999");
    });
  }, [allActions, view]);

  const stats = useMemo(() => ({
    open: allActions.filter((a) => !["resolved", "dismissed"].includes(a.status)).length,
    critical: allActions.filter((a) => a.priority === "critical" || isOverdue(a)).length,
    approvals: allActions.filter((a) => a.status === "awaiting_approval").length,
    overdue: allActions.filter(isOverdue).length,
  }), [allActions]);

  if (!currentProject) return <EmptyProjectState title="Select a project to review action items" />;
  if (actionsQuery.isLoading) return <DashboardLayout><LoadingSpinner label="Loading action queue..." /></DashboardLayout>;
  if (actionsQuery.isError) return <DashboardLayout><ErrorState message="Could not load action items." /></DashboardLayout>;

  const selectedAction = detailQuery.data;
  const runTransition = (transition: Parameters<typeof actionApi.transition>[1]) => {
    if (!selectedActionId) return;
    transitionMutation.mutate({ id: selectedActionId, transition, note: note.trim() || undefined });
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Action Center - {currentProject.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">Prioritized delivery actions generated from blockers, ticket quality, repository, and integration signals.</p>
          </div>
          <Button
            type="button"
            onClick={() => generateMutation.mutate()}
            disabled={generateMutation.isPending}
            className="h-9 gap-2 self-start lg:self-auto"
          >
            {generateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ListChecks className="h-4 w-4" />}
            Generate
          </Button>
        </div>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {statCards.map(({ label, key, Icon, color }) => (
            <div key={label} className="rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-medium text-muted-foreground">{label}</p>
                <Icon className={cn("h-4 w-4", color)} />
              </div>
              <p className="mt-2 text-2xl font-bold tabular-nums text-foreground">{stats[key]}</p>
            </div>
          ))}
        </section>

        <section className="flex flex-col gap-3 rounded-lg border border-border bg-card px-4 py-3 shadow-sm lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            {([
              ["project", "Project"],
              ["mine", "Mine"],
              ["critical", "Critical"],
              ["resolved", "Resolved"],
            ] as const).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setView(key)}
                className={cn(
                  "h-8 rounded-md px-3 text-xs font-semibold transition-colors",
                  view === key ? "bg-primary text-primary-foreground" : "bg-muted text-muted-foreground hover:text-foreground",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <Select value={sourceType} onValueChange={setSourceType}>
              <SelectTrigger className="h-8 w-[180px] text-xs">
                <SelectValue placeholder="Source" />
              </SelectTrigger>
              <SelectContent>
                {sourceOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </section>

        <section className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          {actions.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-4 py-16 text-center">
              <ListChecks className="h-10 w-10 text-muted-foreground/40" />
              <p className="mt-3 text-sm font-semibold text-foreground">No actions in this view</p>
              <p className="mt-1 text-xs text-muted-foreground">Generate actions to refresh the project queue.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/30 text-left text-xs font-semibold uppercase text-muted-foreground">
                    <th className="px-4 py-3">Action</th>
                    <th className="px-4 py-3">Source</th>
                    <th className="px-4 py-3">Priority</th>
                    <th className="px-4 py-3">Owner</th>
                    <th className="px-4 py-3">Due</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Next</th>
                  </tr>
                </thead>
                <tbody>
                  {actions.map((action) => (
                    <tr key={action.id} className={cn("border-b border-border/50 transition-colors hover:bg-muted/25", isOverdue(action) && "bg-orange-500/5")}>
                      <td className="max-w-[360px] px-4 py-3">
                        <button
                          type="button"
                          onClick={() => setSelectedActionId(action.id)}
                          className="block text-left"
                        >
                          <span className="block truncate font-semibold text-foreground">{action.title}</span>
                          <span className="mt-1 block truncate text-xs text-muted-foreground">{action.recommended_action}</span>
                        </button>
                      </td>
                      <td className="px-4 py-3"><SourceBadge source={action.source_type} /></td>
                      <td className="px-4 py-3"><PriorityBadge priority={action.priority} /></td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{action.owner_role?.replace("_", " ") ?? "Unassigned"}</td>
                      <td className={cn("px-4 py-3 text-xs", isOverdue(action) ? "font-semibold text-orange-500" : "text-muted-foreground")}>{formatDateTime(action.due_at)}</td>
                      <td className="px-4 py-3"><StatusBadge status={action.status} /></td>
                      <td className="px-4 py-3 text-right">
                        <Button type="button" variant="outline" size="sm" onClick={() => setSelectedActionId(action.id)}>
                          Open
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <Dialog open={selectedActionId !== null} onOpenChange={(open) => { if (!open) { setSelectedActionId(null); setNote(""); } }}>
        <DialogContent className="max-w-3xl">
          {detailQuery.isLoading || !selectedAction ? (
            <LoadingSpinner label="Loading action..." />
          ) : (
            <>
              <DialogHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <SourceBadge source={selectedAction.source_type} />
                  <PriorityBadge priority={selectedAction.priority} />
                  <StatusBadge status={selectedAction.status} />
                </div>
                <DialogTitle className="pt-2">{selectedAction.title}</DialogTitle>
                <DialogDescription>{selectedAction.recommended_action}</DialogDescription>
              </DialogHeader>

              <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
                <div className="space-y-4">
                  <div className="rounded-lg border border-border bg-muted/25 p-4">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Evidence</p>
                    <p className="mt-2 text-sm leading-relaxed text-foreground">{selectedAction.description ?? "No description provided."}</p>
                  </div>
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase text-muted-foreground">Note</p>
                    <Textarea
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      placeholder="Optional note for the timeline"
                      className="min-h-[82px]"
                    />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => runTransition("acknowledge")} disabled={transitionMutation.isPending}>Acknowledge</Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => runTransition("dispatch")} disabled={transitionMutation.isPending}>Dispatch</Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => runTransition("approve")} disabled={transitionMutation.isPending}>Approve</Button>
                    <Button type="button" variant="outline" size="sm" onClick={() => runTransition("reject")} disabled={transitionMutation.isPending}>Reject</Button>
                    <Button type="button" size="sm" onClick={() => runTransition("resolve")} disabled={transitionMutation.isPending}>Resolve</Button>
                    <Button type="button" variant="ghost" size="sm" onClick={() => runTransition("dismiss")} disabled={transitionMutation.isPending}>Dismiss</Button>
                  </div>
                </div>

                <aside className="space-y-3">
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Owner</p>
                    <p className="mt-1 text-sm font-medium text-foreground">{selectedAction.owner_role?.replace("_", " ") ?? "Unassigned"}</p>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Due</p>
                    <p className={cn("mt-1 text-sm font-medium", isOverdue(selectedAction) ? "text-orange-500" : "text-foreground")}>{formatDateTime(selectedAction.due_at)}</p>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs font-semibold uppercase text-muted-foreground">Timeline</p>
                    <div className="mt-3 space-y-3">
                      {selectedAction.events.map((event) => (
                        <div key={event.id} className="border-l border-border pl-3">
                          <p className="text-xs font-semibold text-foreground">{event.event_type.replace("_", " ")}</p>
                          <p className="text-[11px] text-muted-foreground">{formatDateTime(event.created_at)}</p>
                          {event.note && <p className="mt-1 text-xs text-muted-foreground">{event.note}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                </aside>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default Actions;
