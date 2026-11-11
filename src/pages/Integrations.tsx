/**
 * Integrations Hub — connect and manage Trello, Jira, Microsoft Planner, and GitHub.
 *
 * Key flows:
 *   Trello:    inline API key + token form → direct connect
 *   Jira:      OAuth 2.0 → backend /oauth/jira/start → Atlassian consent → callback
 *   Microsoft: OAuth 2.0 → backend /oauth/microsoft/start → MS consent → callback
 *
 * After an OAuth callback the backend redirects to:
 *   /integrations?connected=jira|microsoft   (success)
 *   /integrations?error=...&detail=...       (failure)
 *
 * This page reads those params, shows a banner, and refreshes the account list.
 */
import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Link2, Link2Off, RefreshCw, CheckCircle2, XCircle,
  AlertTriangle, Clock, ChevronDown, ChevronUp,
  Plug, Shield, Zap, ExternalLink, Layers, Loader2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import DashboardLayout from "@/components/DashboardLayout";
import LoadingSpinner from "@/components/LoadingSpinner";
import { useProject } from "@/contexts/ProjectContext";
import { ApiError, ApiNetworkError } from "@/services/api/config";
import { integrationApi } from "@/services/api/integrations";
import type {
  IntegrationAccount, NormalizedBoard, SyncLog, ProviderType,
} from "@/services/api/integrations";

// ── Provider config ───────────────────────────────────────────────────────────

const PROVIDERS: Record<ProviderType, {
  name:   string;
  badge:  string;
  border: string;
  ring:   string;
  icon:   string;
  desc:   string;
  auth:   "apikey" | "oauth";
}> = {
  trello: {
    name:   "Trello",
    badge:  "bg-blue-500/20 text-blue-600 dark:text-blue-400",
    border: "border-blue-500/50",
    ring:   "ring-blue-500/30",
    icon:   "T",
    desc:   "Kanban boards, cards, and lists",
    auth:   "apikey",
  },
  jira: {
    name:   "Jira",
    badge:  "bg-indigo-500/20 text-indigo-600 dark:text-indigo-400",
    border: "border-indigo-500/50",
    ring:   "ring-indigo-500/30",
    icon:   "J",
    desc:   "Issues, sprints, and epics",
    auth:   "oauth",
  },
  microsoft: {
    name:   "Microsoft Planner",
    badge:  "bg-cyan-500/20 text-cyan-600 dark:text-cyan-400",
    border: "border-cyan-500/50",
    ring:   "ring-cyan-500/30",
    icon:   "M",
    desc:   "Plans, tasks, and buckets",
    auth:   "oauth",
  },
  github: {
    name:   "GitHub",
    badge:  "bg-zinc-500/20 text-zinc-700 dark:text-zinc-200",
    border: "border-zinc-500/50",
    ring:   "ring-zinc-500/30",
    icon:   "G",
    desc:   "Repositories, issues, and pull requests",
    auth:   "apikey",
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(s: string | null): string {
  if (!s) return "Never";
  return new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function apiDetailMessage(body: unknown): string | null {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (typeof detail === "object" && detail !== null && "message" in detail) {
      return String((detail as { message?: unknown }).message);
    }
    return JSON.stringify(detail);
  }
  return null;
}

function importErrorMessage(error: unknown): string {
  if (error instanceof ApiNetworkError) return error.message;
  if (error instanceof ApiError) {
    const detail = apiDetailMessage(error.body);
    return detail || `Import failed with ${error.status} ${error.statusText}.`;
  }
  return error instanceof Error ? error.message : "Could not import this board.";
}

// ── Sync log row ──────────────────────────────────────────────────────────────

const SYNC_STATUS_CLS: Record<string, string> = {
  success: "bg-emerald-500/15 text-emerald-600",
  failed:  "bg-destructive/15 text-destructive",
  running: "bg-amber-500/15 text-amber-600",
  partial: "bg-orange-500/15 text-orange-600",
};

function SyncLogRow({ log }: { log: SyncLog }) {
  return (
    <div className="flex items-center gap-3 py-2 border-b border-border last:border-0 text-xs">
      <span className={cn("rounded-full px-2 py-0.5 font-semibold capitalize", SYNC_STATUS_CLS[log.status] ?? "bg-muted text-muted-foreground")}>
        {log.status}
      </span>
      <span className="text-muted-foreground capitalize">{log.sync_type}</span>
      <span className="font-medium text-foreground">{log.items_synced} items</span>
      {log.error_detail && (
        <span className="text-destructive truncate max-w-[160px]" title={log.error_detail}>
          {log.error_detail}
        </span>
      )}
      <span className="ml-auto text-muted-foreground shrink-0">{fmtDate(log.started_at)}</span>
    </div>
  );
}

// ── Board list ────────────────────────────────────────────────────────────────

function BoardList({ accountId, provider }: { accountId: number; provider: ProviderType }) {
  const cfg = PROVIDERS[provider];
  const qc = useQueryClient();
  const { refreshProjects } = useProject();
  const [importingBoardId, setImportingBoardId] = useState<string | null>(null);
  const [importedProjectName, setImportedProjectName] = useState<string | null>(null);
  const boardsQ = useQuery({
    queryKey: ["integration-boards", accountId],
    queryFn:  () => integrationApi.listBoards(accountId),
    staleTime: 60_000,
    retry: 1,
  });
  const importMut = useMutation({
    mutationFn: (boardId: string) => integrationApi.importBoard(accountId, boardId),
    onMutate: (boardId) => setImportingBoardId(boardId),
    onSuccess: async (project) => {
      setImportedProjectName(project.board_name);
      await refreshProjects(project.project_id);
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["integrations"] });
      qc.invalidateQueries({ queryKey: ["integration-logs", accountId] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["kpis"] });
      qc.invalidateQueries({ queryKey: ["sprint"] });
      qc.invalidateQueries({ queryKey: ["blockers"] });
      qc.invalidateQueries({ queryKey: ["team-kpis"] });
      qc.invalidateQueries({ queryKey: ["client-progress"] });
    },
    onSettled: () => setImportingBoardId(null),
  });

  if (boardsQ.isLoading) {
    return (
      <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
        <Loader2 className="h-3 w-3 animate-spin" /> Fetching boards…
      </div>
    );
  }
  if (boardsQ.isError) {
    return (
      <p className="text-xs text-destructive py-2">
        Failed to load boards. Check credentials.
      </p>
    );
  }
  const boards = boardsQ.data ?? [];
  if (boards.length === 0) {
    return <p className="text-xs text-muted-foreground py-2">No boards found.</p>;
  }

  return (
    <div className="space-y-1">
      {boards.map(b => (
        <div
          key={b.id}
          className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs"
        >
          <div className={cn("flex h-6 w-6 items-center justify-center rounded text-[10px] font-bold shrink-0", cfg.badge)}>
            {cfg.icon}
          </div>
          <span className="font-medium text-foreground flex-1 truncate">{b.name}</span>
          <button
            type="button"
            onClick={() => importMut.mutate(b.id)}
            disabled={importMut.isPending}
            title="Import and link this board as a KPIMaster project"
            className="inline-flex h-7 items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-2 text-[11px] font-semibold text-primary hover:bg-primary/15 disabled:opacity-50"
          >
            {importingBoardId === b.id ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <Link2 className="h-3 w-3" />
            )}
            Import / Link Project
          </button>
          {b.url && (
            <a
              href={b.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary hover:text-primary/80 shrink-0"
              onClick={e => e.stopPropagation()}
            >
              <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      ))}
      {importedProjectName && (
        <p className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-600">
          Imported and selected {importedProjectName}. Open the dashboards from the sidebar to view synced {cfg.name} data.
        </p>
      )}
      {importMut.isError && (
        <p className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {importErrorMessage(importMut.error)}
        </p>
      )}
    </div>
  );
}

// ── Account card ──────────────────────────────────────────────────────────────

function AccountCard({ account }: { account: IntegrationAccount }) {
  const cfg = PROVIDERS[account.provider];
  const qc  = useQueryClient();
  const { currentProject } = useProject();
  const [open, setOpen]           = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [activeTab, setActiveTab] = useState<"boards" | "logs">("boards");

  const logsQ = useQuery({
    queryKey: ["integration-logs", account.id],
    queryFn:  () => integrationApi.getSyncLogs(account.id, 5),
    staleTime: 30_000,
    enabled:  open && activeTab === "logs",
    retry: 1,
  });
  const healthQ = useQuery({
    queryKey: ["integration-health", account.id],
    queryFn:  () => integrationApi.getHealth(account.id),
    staleTime: 60_000,
    retry: 1,
  });

  const disconnectMut = useMutation({
    mutationFn: () => integrationApi.disconnect(account.id),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ["integrations"] });
      setConfirmDisconnect(false);
    },
  });

  const syncMut = useMutation({
    mutationFn: async () => {
      const boards = await integrationApi.listBoards(account.id);
      if (!boards.length) throw new Error("No boards found for this account");
      return integrationApi.triggerSync(account.id, boards[0].id, false, currentProject?.id);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integration-logs", account.id] });
      qc.invalidateQueries({ queryKey: ["integrations"] });
    },
  });

  return (
    <motion.div layout className={cn("rounded-xl border bg-card shadow-sm overflow-hidden", cfg.border)}>
      {/* ── Header ── */}
      <div className="flex items-center gap-4 px-5 py-4">
        <div className={cn("flex h-10 w-10 items-center justify-center rounded-xl text-sm font-bold shrink-0", cfg.badge)}>
          {cfg.icon}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-foreground truncate">{account.account_name}</p>
          <p className="text-xs text-muted-foreground">{cfg.desc}</p>
          <div className="mt-1 flex items-center gap-1.5 text-[11px]">
            {healthQ.isLoading ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                <span className="text-muted-foreground">Checking connection</span>
              </>
            ) : healthQ.data?.credentials_ok ? (
              <>
                <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                <span className="font-medium text-emerald-600">Connected</span>
              </>
            ) : (
              <>
                <XCircle className="h-3 w-3 text-rose-500" />
                <span className="font-medium text-rose-600">Needs attention</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="text-right hidden sm:block">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wide">Last sync</p>
            <p className="text-xs font-medium text-foreground">{fmtDate(account.last_sync_at)}</p>
          </div>

          {/* Sync */}
          <button
            onClick={() => syncMut.mutate()}
            disabled={syncMut.isPending}
            title={syncMut.isError ? String(syncMut.error) : "Sync now"}
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-lg transition-colors disabled:opacity-40",
              syncMut.isError
                ? "bg-destructive/10 text-destructive"
                : "bg-primary/10 text-primary hover:bg-primary/20"
            )}
          >
            <RefreshCw className={cn("h-3.5 w-3.5", syncMut.isPending && "animate-spin")} />
          </button>

          {/* Disconnect */}
          <button
            onClick={() => setConfirmDisconnect(true)}
            title="Disconnect"
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors"
          >
            <Link2Off className="h-3.5 w-3.5" />
          </button>

          {/* Expand toggle */}
          <button
            onClick={() => setOpen(o => !o)}
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {/* ── Disconnect confirmation ── */}
      <AnimatePresence>
        {confirmDisconnect && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-t border-destructive/30 bg-destructive/8"
          >
            <div className="flex items-center gap-3 px-5 py-3">
              <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />
              <p className="text-xs text-foreground flex-1">
                Disconnect <strong>{account.account_name}</strong>? Tokens will be deleted. You can reconnect anytime.
              </p>
              <button
                onClick={() => disconnectMut.mutate()}
                disabled={disconnectMut.isPending}
                className="rounded-lg bg-destructive px-3 py-1.5 text-xs font-semibold text-white hover:bg-destructive/90 transition-colors disabled:opacity-50"
              >
                {disconnectMut.isPending ? "Disconnecting…" : "Disconnect"}
              </button>
              <button
                onClick={() => setConfirmDisconnect(false)}
                className="rounded-lg bg-muted px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancel
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Expanded detail ── */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t border-border"
          >
            <div className="px-5 py-4 space-y-3">
              {/* Provider metadata */}
              {Object.keys(account.extra_data).length > 0 && (
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {Object.entries(account.extra_data)
                    .filter(([, v]) => v && String(v).length < 60)
                    .map(([k, v]) => (
                      <span key={k} className="text-[11px] text-muted-foreground">
                        <span className="font-mono">{k}:</span>{" "}
                        <span className="text-foreground/80">{String(v)}</span>
                      </span>
                    ))}
                </div>
              )}

              {/* Token expiry */}
              {account.token_expires_at && (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  Token expires {fmtDate(account.token_expires_at)}
                </div>
              )}

              {/* Tabs: Boards / Logs */}
              <div className="flex gap-1 border-b border-border pb-2">
                {(["boards", "logs"] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors capitalize",
                      activeTab === tab
                        ? "bg-primary/10 text-primary"
                        : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    {tab === "boards" ? <Layers className="h-3 w-3" /> : <RefreshCw className="h-3 w-3" />}
                    {tab}
                  </button>
                ))}
              </div>

              {/* Tab content */}
              {activeTab === "boards" && (
                <BoardList accountId={account.id} provider={account.provider} />
              )}
              {activeTab === "logs" && (
                <div>
                  {logsQ.isLoading
                    ? <p className="text-xs text-muted-foreground">Loading…</p>
                    : logsQ.isError
                      ? <p className="text-xs text-destructive">Failed to load sync logs.</p>
                      : logsQ.data?.length === 0
                        ? <p className="text-xs text-muted-foreground">No sync history yet.</p>
                        : logsQ.data?.map(l => <SyncLogRow key={l.id} log={l} />)
                  }
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── Trello connect form ───────────────────────────────────────────────────────

function TrelloConnectForm({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
  const [key, setKey]     = useState("");
  const [token, setToken] = useState("");
  const [label, setLabel] = useState("My Trello");
  const [err, setErr]     = useState("");
  const qc = useQueryClient();

  const mut = useMutation({
    mutationFn: () => integrationApi.connectTrello(key.trim(), token.trim(), label.trim() || "Trello"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations"] });
      onSuccess();
    },
    onError: (e: Error) => setErr(e.message),
  });

  return (
    <div className="space-y-4 pt-4 border-t border-border">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">Connect Trello</p>
        <a
          href="https://trello.com/app-key"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-primary hover:underline"
        >
          Get API key <ExternalLink className="h-2.5 w-2.5" />
        </a>
      </div>
      <div className="space-y-3">
        <div>
          <label className="text-xs font-medium text-foreground/80 mb-1 block">Label</label>
          <input
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. Work Trello"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-foreground/80 mb-1 block">API Key</label>
          <input
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            value={key} onChange={e => setKey(e.target.value)} placeholder="32-character hex key"
            autoComplete="off"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-foreground/80 mb-1 block">API Token</label>
          <input
            type="password"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            value={token} onChange={e => setToken(e.target.value)} placeholder="64-character token"
            autoComplete="off"
          />
        </div>
      </div>
      {err && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 border border-destructive/30 px-3 py-2 text-xs text-destructive">
          <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          {err}
        </div>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => { setErr(""); mut.mutate(); }}
          disabled={mut.isPending || !key.trim() || !token.trim()}
          className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {mut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {mut.isPending ? "Connecting…" : "Connect Trello"}
        </button>
        <button
          onClick={onCancel}
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Jira connect form ───────────────────────────────────────────────────────

function JiraConnectForm({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
  
  const [jira_client_id , setJiraClientId] = useState("");
  const [jira_client_secret , setJiraClientSecret] = useState("");  
  const [err, setErr]     = useState("");
  const qc = useQueryClient();

  const mut = useMutation({
    
    mutationFn: () => integrationApi.startJiraOAuth(jira_client_id.trim(), jira_client_secret.trim()),// to change to startJiraOAuth
    onSuccess: (data) => {
      
      qc.invalidateQueries({ queryKey: ["integrations"] });
      if (data.authorization_url) {
        window.open(data.authorization_url, "_blank");
      }
      onSuccess();
    },
    onError: (e: Error) => setErr(e.message),
  });

  return (
    <div className="space-y-4 pt-4 border-t border-border">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">Connect Jira</p>
        <a
          href="https://developer.atlassian.com/console/myapps"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-primary hover:underline"
        >
          Create the App, access its settings and get credentials <ExternalLink className="h-2.5 w-2.5" />
        </a>
      </div>
      <div className="space-y-3">
        
        <div>
          <label className="text-xs font-medium text-foreground/80 mb-1 block">Client ID</label>
          <input
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            value={jira_client_id} onChange={e => setJiraClientId(e.target.value)} placeholder="32-character hex key"
            autoComplete="off"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-foreground/80 mb-1 block">Client Secret</label>
          <input
            type="password"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            value={jira_client_secret} onChange={e => setJiraClientSecret(e.target.value)} placeholder="64-character token"
            autoComplete="off"
          />
        </div>
        <div className=" ">
          <p className="text-sm font-semibold text-foreground">Add Scopes</p>
          
          <p className="mt-1 text-[11px] text-muted-foreground">
            Add the following scopes to your Jira app: read:jira-work, read:jira-user, read:jira-devinfo, read:jira-configuration, read:jira-projects, read:jira-issues, read:jira-boards, read:jira-sprints, read:servicemanagement-insight-objects, write:servicedesk-request, manage:servicedesk-customer, read:servicedesk-request.
          </p>
        </div>
      <div className="space-y-3"></div>
      </div>
      {err && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 border border-destructive/30 px-3 py-2 text-xs text-destructive">
          <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          {err}
        </div>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => { setErr(""); mut.mutate(); }}
          disabled={mut.isPending || !jira_client_id.trim() || !jira_client_secret.trim()}
          className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {mut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {mut.isPending ? "Connecting…" : "Connect Jira"}
        </button>
        <button
          onClick={onCancel}
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          Cancel
        </button>
        
      </div>
    </div>
  );
}

function GitHubConnectForm({ onSuccess, onCancel }: { onSuccess: () => void; onCancel: () => void }) {
  const [token, setToken] = useState("");
  const [label, setLabel] = useState("My GitHub");
  const [err, setErr] = useState("");
  const qc = useQueryClient();

  const mut = useMutation({
    mutationFn: () => integrationApi.connectGitHub(token.trim(), label.trim() || "GitHub"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["integrations"] });
      onSuccess();
    },
    onError: (e: Error) => setErr(e.message),
  });

  return (
    <div className="space-y-4 pt-4 border-t border-border">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-foreground">Connect GitHub</p>
        <a
          href="https://github.com/settings/tokens"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-primary hover:underline"
        >
          Create token <ExternalLink className="h-2.5 w-2.5" />
        </a>
      </div>
      <div className="space-y-3">
        <div>
          <label className="text-xs font-medium text-foreground/80 mb-1 block">Label</label>
          <input
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            value={label}
            onChange={e => setLabel(e.target.value)}
            placeholder="e.g. Engineering GitHub"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-foreground/80 mb-1 block">Personal Access Token</label>
          <input
            type="password"
            className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="github_pat_..."
            autoComplete="off"
          />
          <p className="mt-1 text-[11px] text-muted-foreground">
            Use a token that can read repositories, issues, pull requests, and comments.
          </p>
        </div>
      </div>
      {err && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 border border-destructive/30 px-3 py-2 text-xs text-destructive">
          <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          {err}
        </div>
      )}
      <div className="flex gap-2">
        <button
          onClick={() => { setErr(""); mut.mutate(); }}
          disabled={mut.isPending || !token.trim()}
          className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {mut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          {mut.isPending ? "Connecting…" : "Connect GitHub"}
        </button>
        <button
          onClick={onCancel}
          className="rounded-lg border border-border px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// ── Connect panel ─────────────────────────────────────────────────────────────

function ConnectPanel() {
  const [selected, setSelected]   = useState<ProviderType | null>(null);
  const [oauthPending, setOAuthPending] = useState<"jira" | "microsoft" | null>(null);
  const [oauthError, setOAuthError]     = useState<string | null>(null);

  const handleOAuth = useCallback(async (provider: "microsoft") => {
    setOAuthPending(provider);
    setOAuthError(null);
    try {
      const res =  await integrationApi.startMicrosoftOAuth();
      // Redirect the browser to the provider's consent page
      window.location.href = res.authorization_url;
    } catch (e: unknown) {
      let msg = e instanceof Error ? e.message : "OAuth failed";
      // Surface 503 "not configured" errors clearly
      if (msg.includes("503") || msg.toLowerCase().includes("not configured")) {
        const name = "Microsoft";
        msg = `${name} OAuth is not configured on the server. Add ${"MICROSOFT_CLIENT_ID + MICROSOFT_CLIENT_SECRET"} to your backend .env file.`;
      }
      setOAuthError(msg);
      setOAuthPending(null);
      setSelected(null);
    }
  }, []);

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10">
          <Plug className="h-4 w-4 text-primary" />
        </div>
        <h3 className="text-sm font-semibold text-foreground">Add Integration</h3>
      </div>

      {oauthError && (
        <div className="flex items-start gap-2 rounded-lg bg-destructive/10 border border-destructive/30 px-3 py-2 mb-4 text-xs text-destructive">
          <XCircle className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          {oauthError}
          <button onClick={() => setOAuthError(null)} className="ml-auto text-destructive/60 hover:text-destructive">✕</button>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {(Object.entries(PROVIDERS) as [ProviderType, typeof PROVIDERS[ProviderType]][]).map(([key, cfg]) => {
          const isPending = oauthPending === key;
          const isActive  = selected === key;
          return (
            <button
              key={key}
              data-testid={`connect-${key}`}
              onClick={() => {
                setSelected(key);
                setOAuthError(null);
                if (key === "trello" || key === "github" || key === "jira") {
                  // toggle inline form
                  if (selected === key) setSelected(null);
                } else {
                  handleOAuth(key as "microsoft");
                }
              }}
              disabled={isPending}
              className={cn(
                "flex flex-col items-start gap-2.5 rounded-xl border p-4 text-left transition-all",
                isActive
                  ? cn(cfg.border, "bg-card shadow-sm ring-2", cfg.ring)
                  : "border-border bg-muted/30 hover:bg-card hover:shadow-sm",
                isPending && "opacity-70 cursor-not-allowed",
              )}
            >
              <div className="flex w-full items-center justify-between">
                <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg text-sm font-bold", cfg.badge)}>
                  {cfg.icon}
                </div>
                {isPending && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">{cfg.name}</p>
                <p className="text-[11px] text-muted-foreground mt-0.5">{cfg.desc}</p>
              </div>
              {cfg.auth === "oauth" ? (
                <span className="inline-flex items-center gap-1 text-[10px] font-medium text-primary">
                  <Shield className="h-2.5 w-2.5" />
                  {isPending ? "Redirecting…" : "Connect with OAuth 2.0"}
                </span>
              ) : (
                <span className="text-[10px] font-medium text-muted-foreground">
                  API Key + Token
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Trello inline form */}
      <AnimatePresence>
        {}
        {(selected === "trello" || selected === "github" || selected ==="jira") && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            {selected === "trello" ? (
              <TrelloConnectForm
                onSuccess={() => setSelected(null)}
                onCancel={() => setSelected(null)}
              />
            ) : selected === "jira" ? (
              <JiraConnectForm
                onSuccess={() => setSelected(null)}
                onCancel={() => setSelected(null)}
              />
            ) : (
              <GitHubConnectForm
                onSuccess={() => setSelected(null)}
                onCancel={() => setSelected(null)}
              />
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Callback banner ───────────────────────────────────────────────────────────

const PROVIDER_LABELS: Record<string, string> = {
  jira:      "Jira",
  microsoft: "Microsoft Planner",
  github:    "GitHub",
};

function CallbackBanner({
  connected, error, detail, onDismiss,
}: {
  connected: string | null;
  error:     string | null;
  detail:    string | null;
  onDismiss: () => void;
}) {
  if (!connected && !error) return null;
  const isSuccess = !!connected;
  const label = connected ? PROVIDER_LABELS[connected] ?? connected : "";

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      className={cn(
        "flex items-start gap-3 rounded-xl border px-4 py-3 text-sm",
        isSuccess
          ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-700 dark:text-emerald-400"
          : "bg-destructive/10 border-destructive/40 text-destructive"
      )}
    >
      {isSuccess
        ? <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
        : <XCircle className="h-4 w-4 shrink-0 mt-0.5" />
      }
      <div className="flex-1">
        {isSuccess
          ? <><strong>{label}</strong> connected successfully. Your boards are now syncing.</>
          : <><strong>Connection failed.</strong>{detail ? ` ${detail}` : " Please try again."}</>
        }
      </div>
      <button onClick={onDismiss} className="opacity-60 hover:opacity-100 transition-opacity ml-2">
        ✕
      </button>
    </motion.div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const FEATURES = [
  { icon: RefreshCw, title: "Auto Sync",  desc: "Background sync every 5 min" },
  { icon: Shield,    title: "Encrypted",  desc: "AES-128 Fernet token storage" },
  { icon: Zap,       title: "Real-time",  desc: "Webhook-based push updates" },
];

const Integrations = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const qc = useQueryClient();

  // Parse OAuth callback result from URL params
  const connected = searchParams.get("connected");
  const errorParam = searchParams.get("error");
  const detail     = searchParams.get("detail");
  const [banner, setBanner] = useState<{ connected: string | null; error: string | null; detail: string | null }>({
    connected: null, error: null, detail: null,
  });

  // On mount: read and immediately clear the callback params from the URL,
  // then refresh the accounts list so the new account shows up.
  useEffect(() => {
    if (connected || errorParam) {
      setBanner({ connected, error: errorParam, detail });
      setSearchParams({}, { replace: true });
      if (connected) {
        qc.invalidateQueries({ queryKey: ["integrations"] });
      }
    }
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const accountsQ = useQuery({
    queryKey: ["integrations"],
    queryFn:  () => integrationApi.listAccounts(),
    staleTime: 30_000,
    retry: 1,           // only retry once — don't spin forever on 404/500
    refetchOnWindowFocus: false,
  });

  const connected_accounts = accountsQ.data ?? [];

  return (
    <DashboardLayout>
      <div className="space-y-6 max-w-4xl">

        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-foreground">Integrations</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Connect external task management platforms. Data is synced automatically and normalized into a unified model.
          </p>
        </div>

        {/* OAuth callback result banner */}
        <AnimatePresence>
          {(banner.connected || banner.error) && (
            <CallbackBanner
              connected={banner.connected}
              error={banner.error}
              detail={banner.detail}
              onDismiss={() => setBanner({ connected: null, error: null, detail: null })}
            />
          )}
        </AnimatePresence>

        {/* Feature strip */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {FEATURES.map(f => (
            <div
              key={f.title}
              className="flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sm"
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 shrink-0">
                <f.icon className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-xs font-semibold text-foreground">{f.title}</p>
                <p className="text-[11px] text-muted-foreground">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>

        {/* Connected accounts */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
              <Link2 className="h-4 w-4 text-primary" />
              Connected Accounts
              {connected_accounts.length > 0 && (
                <span className="rounded-full bg-primary/15 text-primary text-[11px] font-bold px-2 py-0.5">
                  {connected_accounts.length}
                </span>
              )}
            </h2>
          </div>

          {accountsQ.isLoading ? (
            <div className="flex justify-center py-10">
              <LoadingSpinner />
            </div>
          ) : accountsQ.isError ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-destructive/30 bg-destructive/8 py-10 text-center gap-2">
              <XCircle className="h-8 w-8 text-destructive/50" />
              <p className="text-sm font-semibold text-foreground">Could not load integrations</p>
              <p className="text-xs text-muted-foreground">
                {accountsQ.error instanceof Error ? accountsQ.error.message : "API error"}
              </p>
              <button
                onClick={() => qc.invalidateQueries({ queryKey: ["integrations"] })}
                className="mt-2 rounded-lg bg-muted px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Retry
              </button>
            </div>
          ) : connected_accounts.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-border bg-card py-12 text-center gap-2">
              <Link2Off className="h-10 w-10 text-muted-foreground/30 mb-1" />
              <p className="text-sm font-semibold text-foreground">No integrations yet</p>
              <p className="text-xs text-muted-foreground">Connect a provider below to start syncing tasks.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {connected_accounts.map(acc => (
                <AccountCard key={acc.id} account={acc} />
              ))}
            </div>
          )}
        </div>

        {/* Add integration */}
        <ConnectPanel />

        {/* Security note */}
        <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/8 px-4 py-3">
          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
          <p className="text-xs text-foreground/80">
            <span className="font-semibold text-amber-700 dark:text-amber-500">Security: </span>
            Tokens are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before storage.
            OAuth tokens refresh automatically before expiry.
            Webhook endpoints verify signatures (HMAC or signed state tokens).
          </p>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default Integrations;
