import { motion, AnimatePresence } from "framer-motion";
import { useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";
import EmptyProjectState from "@/components/EmptyProjectState";
import { useProject } from "@/contexts/ProjectContext";
import { useBlockers } from "@/hooks/useSprintData";
import { getApiDateRange } from "@/lib/dateRange";
import { isTrelloCompatiblePlatform, PLATFORM_LABELS } from "@/lib/platforms";
import {
  Zap, Bell, AlertOctagon, Clock, MessageCircle,
  ArrowUpRight, ShieldCheck, ChevronDown, ChevronUp,
  Eye,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useToast } from "@/components/ui/use-toast";
import { ticketApi } from "@/services/api/tickets";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import type { UIBlocker } from "@/services/api/types";

// ── config ────────────────────────────────────────────────────────────────────

const levelConfig = {
  1: {
    label:     "Developer Prompt",
    sublabel:  "24h inactivity",
    desc:      "Prompt the developer for an immediate status update",
    Icon:      Zap,
    stripe:    "bg-amber-500",
    border:    "border-amber-500/60",
    card:      "bg-amber-500/12",
    badge:     "bg-amber-500/25 text-amber-600 ring-1 ring-amber-500/40",
    iconBg:    "bg-amber-500/20",
    iconColor: "text-amber-600",
    btnPrimary:"bg-amber-500 hover:bg-amber-600 text-black",
  },
  2: {
    label:     "Team Lead Alert",
    sublabel:  "48h inactivity",
    desc:      "Notify the team lead with full context and impact analysis",
    Icon:      Bell,
    stripe:    "bg-orange-500",
    border:    "border-orange-500/60",
    card:      "bg-orange-500/12",
    badge:     "bg-orange-500/25 text-orange-600 ring-1 ring-orange-500/40",
    iconBg:    "bg-orange-500/20",
    iconColor: "text-orange-600",
    btnPrimary:"bg-orange-500 hover:bg-orange-600 text-white",
  },
  3: {
    label:     "Management Escalation",
    sublabel:  "72h+ inactivity",
    desc:      "Escalate to management with full impact assessment",
    Icon:      AlertOctagon,
    stripe:    "bg-rose-500",
    border:    "border-rose-500/60",
    card:      "bg-rose-500/12",
    badge:     "bg-rose-500/25 text-rose-600 ring-1 ring-rose-500/40",
    iconBg:    "bg-rose-500/20",
    iconColor: "text-rose-600",
    btnPrimary:"bg-rose-500 hover:bg-rose-600 text-white",
  },
} as const;

type Level = 1 | 2 | 3;

// ── sub-components ────────────────────────────────────────────────────────────

function EscalationStep({ level, count, active }: { level: Level; count: number; active: boolean }) {
  const cfg = levelConfig[level];
  const Icon = cfg.Icon;
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: (level - 1) * 0.06 }}
      className={cn(
        "flex-1 rounded-xl border p-4 shadow-sm transition-all",
        active ? cn(cfg.border, cfg.card) : "border-border bg-card"
      )}
    >
      <div className="flex items-center justify-between mb-3">
        <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg", cfg.iconBg)}>
          <Icon className={cn("h-4.5 w-4.5", cfg.iconColor)} />
        </div>
        <span className={cn(
          "text-xl font-bold",
          active ? cfg.iconColor : "text-foreground"
        )}>{count}</span>
      </div>
      <p className="text-sm font-semibold text-foreground">Level {level}</p>
      <p className={cn("text-xs font-medium mt-0.5", cfg.iconColor)}>{cfg.label}</p>
      <p className="text-[11px] text-muted-foreground mt-1">{cfg.sublabel} → {cfg.desc}</p>
    </motion.div>
  );
}

function BlockerCard({ blocker, idx }: { blocker: UIBlocker; idx: number }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [isOpen, setIsOpen] = useState(false);

  const actionMutation = useMutation({
    mutationFn: (type: string) => ticketApi.actionBlocker(blocker.id, type),
    onSuccess: (_, type) => {
      queryClient.invalidateQueries({ queryKey: ["blockers-all"] });
      const msg = type === "prompt_developer" ? "Developer prompted successfully." :
                  type === "alert_lead" ? "Team lead alerted." : "Escalated to management.";
      toast({ title: "Action Dispatched", description: msg });
    },
    onError: () => {
      toast({ title: "Action Failed", description: "Could not dispatch the action.", variant: "destructive" });
    }
  });

  const handleAction = () => {
    const lvl = blocker.escalationLevel;
    const type = lvl === 1 ? "prompt_developer" : lvl === 2 ? "alert_lead" : "escalate_management";
    actionMutation.mutate(type);
  };

  const lvl = blocker.escalationLevel as Level;
  const cfg = levelConfig[lvl];
  const Icon = cfg.Icon;

  const stalledDays = Math.floor(blocker.stalledHours / 24);
  const stalledRemH = blocker.stalledHours % 24;
  const stalledLabel = stalledDays > 0
    ? `${stalledDays}d ${stalledRemH}h`
    : `${blocker.stalledHours}h`;

  return (
    <motion.div
      key={blocker.id}
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: idx * 0.06 }}
      className={cn(
        "relative rounded-xl border overflow-hidden shadow-sm",
        cfg.border, cfg.card
      )}
    >
      {/* Left color stripe */}
      <div className={cn("absolute left-0 inset-y-0 w-1", cfg.stripe)} />

      <div className="pl-5 pr-5 py-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0 space-y-2">
            {/* Header row */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-primary text-xs font-semibold">{blocker.ticketId}</span>
              <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold", cfg.badge)}>
                <Icon className="h-3 w-3" />
                Level {lvl}
              </span>
            </div>

            {/* Title */}
            <h4 className="text-sm font-semibold text-foreground leading-snug">{blocker.title}</h4>
            <p className="text-xs text-muted-foreground">{blocker.reason}</p>

            {/* Meta chips */}
            <div className="flex flex-wrap gap-3 pt-1">
              <div className={cn("flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium", cfg.badge)}>
                <Clock className="h-3.5 w-3.5" />
                Stalled {stalledLabel}
              </div>
              <div className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium bg-muted text-muted-foreground">
                <MessageCircle className="h-3.5 w-3.5" />
                Last active: {blocker.lastActivity}
              </div>
              {blocker.impact && (
                <div className="flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium bg-warning/15 text-warning">
                  <ArrowUpRight className="h-3.5 w-3.5" />
                  {blocker.impact}
                </div>
              )}
            </div>
          </div>

          {/* Stalled time badge (big) */}
          <div className={cn("shrink-0 flex flex-col items-center justify-center rounded-xl px-4 py-3 text-center min-w-[72px]", cfg.iconBg)}>
            <span className={cn("text-xl font-bold tabular-nums leading-none", cfg.iconColor)}>
              {blocker.stalledHours}
            </span>
            <span className={cn("text-[10px] font-medium mt-0.5", cfg.iconColor)}>hrs stalled</span>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-border">
          <button
            disabled={actionMutation.isPending}
            onClick={handleAction}
            className={cn("rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors flex items-center gap-2", cfg.btnPrimary, actionMutation.isPending && "opacity-50 pointer-events-none")}>
            {actionMutation.isPending ? "Sending..." : (lvl === 1 ? "Send Prompt" : lvl === 2 ? "Alert Team Lead" : "Escalate Now")}
          </button>
          <button
            onClick={() => setIsOpen(true)}
            className="rounded-lg px-3 py-1.5 text-xs font-semibold bg-muted text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1.5">
            <Eye className="h-3.5 w-3.5" /> View Details
          </button>
        </div>
      </div>

      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{blocker.title}</DialogTitle>
            <DialogDescription>Stalled for {stalledLabel}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 text-sm text-foreground mt-4">
            <div>
              <span className="font-semibold text-muted-foreground block mb-1">Reason:</span>
              <div className="p-3 bg-muted/50 rounded-lg border">{blocker.reason}</div>
            </div>
            <div>
              <span className="font-semibold text-muted-foreground block mb-1">Impact:</span>
              <p>{blocker.impact}</p>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </motion.div>
  );
}

// ── page ─────────────────────────────────────────────────────────────────────

const BlockerDetection = () => {
  const { currentProject, globalDateRange, globalPlatformFilter } = useProject();
  const pid = currentProject?.id ?? 0;
  const isTrelloPlatform = isTrelloCompatiblePlatform(globalPlatformFilter);
  const { startDate: sd, endDate: ed } = getApiDateRange(globalDateRange);
  const { data: blockers = [], isLoading, isError } = useBlockers(pid, sd, ed, globalPlatformFilter);
  const [activeLevel, setActiveLevel] = useState<Level | "all">("all");
  const [collapsed, setCollapsed] = useState<Set<Level>>(new Set());

  if (!currentProject) return <EmptyProjectState title="Import a Trello board to detect blockers" />;
  if (!isTrelloPlatform) {
    return (
      <DashboardLayout>
        <ErrorState
          message={`Blocker Detection currently uses Trello stall signals. Switch the platform filter from ${PLATFORM_LABELS[globalPlatformFilter]} to Trello or All Platforms.`}
        />
      </DashboardLayout>
    );
  }

  if (isLoading) return <DashboardLayout><LoadingSpinner /></DashboardLayout>;
  if (isError)   return <DashboardLayout><ErrorState /></DashboardLayout>;

  const byLevel = (lvl: Level) => blockers.filter(b => b.escalationLevel === lvl);
  const filtered = activeLevel === "all" ? blockers : blockers.filter(b => b.escalationLevel === activeLevel);

  const toggleCollapse = (lvl: Level) =>
    setCollapsed(s => {
      const n = new Set(s);
      if (n.has(lvl)) n.delete(lvl);
      else n.add(lvl);
      return n;
    });

  return (
    <DashboardLayout>
      <div className="space-y-6">

        {/* Escalation matrix */}
        <div className="flex flex-col sm:flex-row gap-4">
          {([1, 2, 3] as Level[]).map(lvl => (
            <EscalationStep key={lvl} level={lvl} count={byLevel(lvl).length} active={byLevel(lvl).length > 0} />
          ))}
        </div>

        {/* Filter tabs */}
        <div className="flex items-center gap-2 flex-wrap">
          {(["all", 1, 2, 3] as const).map(lvl => (
            <button
              key={lvl}
              onClick={() => setActiveLevel(lvl)}
              className={cn(
                "rounded-full px-4 py-1.5 text-xs font-semibold transition-all",
                activeLevel === lvl
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              )}
            >
              {lvl === "all" ? `All (${blockers.length})` : `Level ${lvl} (${byLevel(lvl).length})`}
            </button>
          ))}
        </div>

        {/* Active blockers */}
        {filtered.length === 0 ? (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            className="flex flex-col items-center justify-center rounded-2xl border border-border bg-card py-16 text-center">
            <ShieldCheck className="h-12 w-12 text-emerald-500/50 mb-3" />
            <p className="text-sm font-semibold text-foreground">No active blockers</p>
            <p className="text-xs text-muted-foreground mt-1">The team is moving at full speed.</p>
          </motion.div>
        ) : activeLevel === "all" ? (
          // Grouped by level with collapsible sections
          <div className="space-y-4">
            {([3, 2, 1] as Level[]).map(lvl => {
              const group = byLevel(lvl);
              if (group.length === 0) return null;
              const cfg = levelConfig[lvl];
              const isCollapsed = collapsed.has(lvl);
              return (
                <div key={lvl} className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
                  <button
                    onClick={() => toggleCollapse(lvl)}
                    className="w-full flex items-center justify-between px-5 py-4 hover:bg-muted/30 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className={cn("h-2.5 w-2.5 rounded-full", cfg.stripe)} />
                      <span className="text-sm font-semibold text-foreground">Level {lvl} — {cfg.label}</span>
                      <span className={cn("rounded-full px-2 py-0.5 text-xs font-bold", cfg.badge)}>
                        {group.length}
                      </span>
                    </div>
                    {isCollapsed ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronUp className="h-4 w-4 text-muted-foreground" />}
                  </button>
                  <AnimatePresence initial={false}>
                    {!isCollapsed && (
                      <motion.div
                        key="content"
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <div className="px-5 pb-5 space-y-3 border-t border-border">
                          <div className="pt-4 space-y-3">
                            {group.map((b, i) => <BlockerCard key={b.id} blocker={b} idx={i} />)}
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((b, i) => <BlockerCard key={b.id} blocker={b} idx={i} />)}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default BlockerDetection;
