import { useState } from "react";
import { motion } from "framer-motion";
import DashboardLayout from "@/components/DashboardLayout";
import LoadingSpinner from "@/components/LoadingSpinner";
import ErrorState from "@/components/ErrorState";
import EmptyProjectState from "@/components/EmptyProjectState";
import { GitBranch, GitCommit, GitPullRequest, AlertCircle, ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import { useProject } from "@/contexts/ProjectContext";
import { getApiDateRange } from "@/lib/dateRange";
import { useRepositoryMismatches } from "@/hooks/useSprintData";
import { PLATFORM_LABELS } from "@/lib/platforms";
import type { UIRepoActivity } from "@/services/api/types";

const prStatusStyles: Record<string, string> = {
  merged:  "bg-success/15 text-success",
  open:    "bg-primary/15 text-primary",
  review:  "bg-warning/15 text-warning",
  none:    "bg-muted text-muted-foreground",
};

const RepositoryIntegration = () => {
  const { currentProject, globalDateRange, globalPlatformFilter } = useProject();
  const projectId = currentProject?.id ?? 0;
  const { startDate, endDate } = getApiDateRange(globalDateRange);
  const { data: repoActivity = [], isLoading, isError } = useRepositoryMismatches(
    projectId,
    startDate,
    endDate,
    globalPlatformFilter,
  );
  const [selectedRepo, setSelectedRepo] = useState<string>("all");

  if (!currentProject) return <EmptyProjectState title="Import a Trello board to inspect repository mismatches" />;

  if (isLoading) return <DashboardLayout><LoadingSpinner /></DashboardLayout>;
  if (isError)   return <DashboardLayout><ErrorState /></DashboardLayout>;

  const filtered: UIRepoActivity[] = selectedRepo === "all"
    ? repoActivity
    : selectedRepo === "mismatches"
      ? repoActivity.filter(r => r.mismatch)
      : repoActivity.filter(r => !r.mismatch);

  const mismatches = filtered.filter(r => r.mismatch);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Repository Integration — {currentProject.name}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Bridging project management &amp; code activity · {repoActivity.length} tracked tickets
          </p>
          {globalPlatformFilter !== "all" && (
            <p className="text-xs text-muted-foreground mt-2">
              Filtered by {PLATFORM_LABELS[globalPlatformFilter]}.
            </p>
          )}
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2 flex-wrap">
          {([
            ["all",        `All (${repoActivity.length})`],
            ["ok",         `Clean (${repoActivity.filter(r => !r.mismatch).length})`],
            ["mismatches", `Stalled (${repoActivity.filter(r => r.mismatch).length})`],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setSelectedRepo(key)}
              className={cn(
                "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                selectedRepo === key
                  ? key === "mismatches" ? "bg-warning text-warning-foreground" : "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Mismatch alerts */}
        {mismatches.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card rounded-xl p-5 border-l-4 border-l-warning">
            <h3 className="text-sm font-semibold text-foreground flex items-center gap-2 mb-3">
              <AlertCircle className="h-4 w-4 text-warning" />
              Stalled Tickets Detected ({mismatches.length})
            </h3>
            <div className="space-y-2">
              {mismatches.map(r => (
                <div key={r.ticketId} className="text-xs text-muted-foreground">
                  <span className="font-mono text-primary">{r.ticket}</span>
                  {" — "}
                  {r.mismatchReason ?? "Card stalled with no recent activity."}
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Activity table */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="glass-card rounded-xl overflow-hidden">
          {filtered.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-12">No repository activity found.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {["Ticket", "Branch", "Commits", "PRs", "PR Status", "Last Commit", ""].map(h => (
                      <th key={h} className="text-left py-3 px-4 text-xs font-semibold text-muted-foreground uppercase tracking-wider">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map(r => (
                    <tr key={r.ticketId} className={cn("border-b border-border/50 hover:bg-muted/30 transition-colors", r.mismatch && "bg-warning/5")}>
                      <td className="py-3 px-4 font-mono text-primary text-xs">{r.ticket}</td>
                      <td className="py-3 px-4">
                        {r.branch.startsWith("http") ? (
                          <a
                            href={r.branch}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1.5 text-xs text-primary font-mono hover:underline"
                          >
                            <ExternalLink className="h-3 w-3 shrink-0" />
                            Trello card
                          </a>
                        ) : (
                          <div className="flex items-center gap-1.5 text-xs text-foreground font-mono">
                            <GitBranch className="h-3 w-3 text-muted-foreground" />
                            {r.branch}
                          </div>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1 text-xs text-foreground">
                          <GitCommit className="h-3 w-3 text-muted-foreground" />
                          {r.commits}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1 text-xs text-foreground">
                          <GitPullRequest className="h-3 w-3 text-muted-foreground" />
                          {r.prs}
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className={cn("text-xs font-medium rounded-full px-2 py-0.5", prStatusStyles[r.prStatus] ?? prStatusStyles.none)}>
                          {r.prStatus}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-xs text-muted-foreground">{r.lastCommit}</td>
                      <td className="py-3 px-4">
                        {r.mismatch && (
                          <span className="flex items-center gap-1 text-xs text-warning">
                            <AlertCircle className="h-3 w-3" /> Mismatch
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </motion.div>
      </div>
    </DashboardLayout>
  );
};

export default RepositoryIntegration;
