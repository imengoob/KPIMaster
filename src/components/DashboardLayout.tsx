import { ReactNode, useState } from "react";
import { useLocation } from "react-router-dom";
import { RefreshCw, Calendar, CheckCircle2, AlertCircle, Menu, X } from "lucide-react";
import AppSidebar from "./AppSidebar";
import { Button } from "@/components/ui/button";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { useProject } from "@/contexts/ProjectContext";
import { trelloApi } from "@/services/api/trello";
import { ThemeToggle } from "@/components/ThemeToggle";
import { DatePickerWithRange } from "@/components/ui/date-range-picker";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PLATFORM_LABELS, PLATFORM_OPTIONS } from "@/lib/platforms";

const PAGE_META: Record<string, { title: string; subtitle: string }> = {
  "/":            { title: "Dashboard",          subtitle: "Sprint overview & KPIs" },
  "/dashboard":   { title: "Dashboard",          subtitle: "Sprint overview & KPIs" },
  "/sprint":      { title: "Sprint Monitor",     subtitle: "Daily burndown & ticket flow" },
  "/sprint-monitor": { title: "Sprint Monitor",  subtitle: "Daily burndown & ticket flow" },
  "/tickets":     { title: "Ticket Analysis",    subtitle: "Automated quality assurance" },
  "/ticket-analysis": { title: "Ticket Analysis", subtitle: "Automated quality assurance" },
  "/blockers":    { title: "Blocker Detection",  subtitle: "Intelligent stalled-ticket detection" },
  "/blocker-detection": { title: "Blocker Detection", subtitle: "Intelligent stalled-ticket detection" },
  "/actions": { title: "Action Center", subtitle: "Operational action queue and approvals" },
  "/my-actions": { title: "My Actions", subtitle: "Personal delivery action queue" },
  "/developers":  { title: "Developer Progress", subtitle: "Continuous monitoring with proactive intervention" },
  "/developer-progress": { title: "Developer Progress", subtitle: "Continuous monitoring with proactive intervention" },
  "/developer-dashboard": { title: "My Dashboard", subtitle: "Personal delivery health and activity" },
  "/developer-history": { title: "Client History", subtitle: "Visibility requests and client delivery record" },
  "/client-progress": { title: "Client Progress", subtitle: "Client-ready delivery tracking across assigned developers" },
  "/vendor-dashboard": { title: "Vendor Dashboard", subtitle: "Vendor delivery health across assigned engagements" },
  "/repository":  { title: "Repository",         subtitle: "Repository integration & mismatch detection" },
  "/repository-integration": { title: "Repository", subtitle: "Repository integration & mismatch detection" },
  "/integrations": { title: "Integrations", subtitle: "Provider connections and sync health" },
  "/analytics/responsiveness": { title: "Responsiveness", subtitle: "Developer response time and activity patterns" },
  "/responsiveness": { title: "Responsiveness", subtitle: "Developer response time and activity patterns" },
  "/recruiting-network": { title: "Recruiting Network", subtitle: "Partner developer discovery and visibility" },
  "/settings":    { title: "Settings",           subtitle: "Trello integration & configuration" },
};

const today = new Date().toLocaleDateString("en-GB", {
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
});

type RefreshState = "idle" | "syncing" | "done" | "error";

const DashboardLayout = ({ children, className }: { children: ReactNode; className?: string }) => {
  const location    = useLocation();
  const queryClient = useQueryClient();
  const {
    currentProject,
    globalDateRange,
    setGlobalDateRange,
    globalPlatformFilter,
    setGlobalPlatformFilter,
  } = useProject();
  const meta = PAGE_META[location.pathname] ?? { title: "KPIMaster", subtitle: "" };

  const [refreshState, setRefreshState] = useState<RefreshState>("idle");
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  const handleRefresh = async () => {
    if (refreshState === "syncing") return;
    setRefreshState("syncing");

    try {
      // 1. Pull latest data from Trello (picks up new assignments, card moves, etc.)
      if (currentProject) {
        await trelloApi.syncProject(currentProject.id);
      }
    } catch {
      // If the project has no Trello boards or the sync fails, still refresh the UI
    }

    // 2. Tell React Query to re-fetch everything from the (now-updated) backend
    await queryClient.invalidateQueries();
    setRefreshState("done");

    // Reset icon after 2 s
    setTimeout(() => setRefreshState("idle"), 2000);
  };

  const refreshLabel =
    refreshState === "syncing" ? "Syncing…" :
    refreshState === "done"    ? "Updated!" :
    refreshState === "error"   ? "Failed"   : "Refresh";

  const RefreshIcon =
    refreshState === "done"  ? CheckCircle2 :
    refreshState === "error" ? AlertCircle  : RefreshCw;

  return (
    <div className="min-h-screen bg-background">
      <AppSidebar className="hidden lg:flex" />
      {isMobileNavOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-background/80 backdrop-blur-sm"
            onClick={() => setIsMobileNavOpen(false)}
          />
          <AppSidebar
            className="relative z-10 flex shadow-2xl"
            onNavigate={() => setIsMobileNavOpen(false)}
          />
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute left-[17rem] top-4 flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-lg"
            onClick={() => setIsMobileNavOpen(false)}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      <div className="flex min-h-screen flex-col lg:ml-64">
        {/* Top header bar */}
        <header className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-3 border-b border-border bg-background/95 px-4 py-3 backdrop-blur-sm sm:px-5 lg:flex-nowrap lg:px-8 lg:py-4">
          <div className="flex min-w-0 items-center gap-3">
            <Button
              type="button"
              variant="outline"
              size="icon"
              aria-label="Open navigation"
              className="h-9 w-9 shrink-0 lg:hidden"
              onClick={() => setIsMobileNavOpen(true)}
            >
              <Menu className="h-4 w-4" />
            </Button>
            <div className="min-w-0">
              <h1 className="truncate text-base font-semibold leading-tight text-foreground sm:text-lg">{meta.title}</h1>
            {meta.subtitle && (
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{meta.subtitle}</p>
            )}
            </div>
          </div>
          <div className="flex min-w-0 items-center gap-2">
            <Select value={globalPlatformFilter} onValueChange={(value) => setGlobalPlatformFilter(value as typeof globalPlatformFilter)}>
              <SelectTrigger data-testid="platform-filter-trigger" className="hidden md:flex w-[170px] text-xs">
                <SelectValue placeholder="Platform" />
              </SelectTrigger>
              <SelectContent>
                {PLATFORM_OPTIONS.map((platform) => (
                  <SelectItem key={platform} value={platform}>
                    {PLATFORM_LABELS[platform]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <DatePickerWithRange date={globalDateRange} setDate={setGlobalDateRange} className="hidden md:flex w-[260px] font-normal" />
            <ThemeToggle />
            <div className="hidden sm:flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
              <Calendar className="h-3.5 w-3.5" />
              {today}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshState === "syncing"}
              className={cn(
                "gap-2 text-xs h-8 transition-colors",
                refreshState === "done"  && "border-emerald-500/40 text-emerald-500",
                refreshState === "error" && "border-rose-500/40 text-rose-500",
              )}
            >
              <RefreshIcon className={cn("h-3.5 w-3.5", refreshState === "syncing" && "animate-spin")} />
              {refreshLabel}
            </Button>
          </div>
        </header>

        {/* Page content */}
        <main className={cn("min-w-0 flex-1 p-4 sm:p-6 lg:p-8", className)}>
          {children}
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
