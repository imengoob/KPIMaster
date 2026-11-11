import { FormEvent, useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import DashboardLayout from "@/components/DashboardLayout";
import LoadingSpinner from "@/components/LoadingSpinner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { isDeveloperUser, useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { companyApi } from "@/services/api/companies";
import { trelloApi } from "@/services/api/trello";
import type { BackendAvailableTrelloBoard, BackendImportedTrelloProject } from "@/services/api/types";
import { ApiError } from "@/services/api/config";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { OutsourcingPartners } from "@/components/OutsourcingPartners";
import AssistantStats from "@/components/AssistantStats";

function sanitizeCredential(raw: string): string {
  return raw.trim().replace(/^[:=\s]+/, "").replace(/^["']|["']$/g, "");
}

function normalizeToken(raw: string): string {
  const value = sanitizeCredential(raw);
  if (!value) return "";
  try {
    if (value.startsWith("http://") || value.startsWith("https://")) {
      const url = new URL(value);
      const queryToken = url.searchParams.get("token");
      if (queryToken) return sanitizeCredential(queryToken);
    }
  } catch { /* use raw value */ }
  const tokenParamMatch = value.match(/(?:^|[?&#])token=([^&#\s]+)/i);
  if (tokenParamMatch) return sanitizeCredential(decodeURIComponent(tokenParamMatch[1]));
  return value;
}

function getTrelloErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 404) {
      return "The Trello board endpoint is not available. Restart the backend container so it picks up the latest API routes, then try again.";
    }
    const detail =
      typeof err.body === "object" && err.body !== null && "detail" in err.body
        ? String((err.body as { detail?: unknown }).detail)
        : err.statusText;
    if (detail.includes("Invalid Trello credentials") || detail.includes("Trello authentication failed")) {
      return "Trello rejected these credentials. Use the Trello API key from your Power-Up page and a Trello user token generated from the authorize link below.";
    }
    return detail;
  }
  return "Failed to reach Trello.";
}

const Settings = () => {
  const { user } = useAuth();
  const { refreshProjects } = useProject();
  const queryClient = useQueryClient();
  const isDeveloper = isDeveloperUser(user);
  const [apiKey, setApiKey] = useState("");
  const [apiToken, setApiToken] = useState("");
  const [availableBoards, setAvailableBoards] = useState<BackendAvailableTrelloBoard[]>([]);
  const [selectedBoardIds, setSelectedBoardIds] = useState<string[]>([]);
  const [savedBoardIds, setSavedBoardIds] = useState<string[]>([]);
  const [hasLoadedBoards, setHasLoadedBoards] = useState(false);
  const [isFetchingBoards, setIsFetchingBoards] = useState(false);
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoadingSettings, setIsLoadingSettings] = useState(true);
  const [settingsSaved, setSettingsSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imported, setImported] = useState<BackendImportedTrelloProject[]>([]);
  const [companySaved, setCompanySaved] = useState(false);
  const [companyForm, setCompanyForm] = useState({
    name: "",
    description: "",
    contact_email: "",
  });

  const companyQuery = useQuery({
    queryKey: ["company", "me"],
    queryFn: () => companyApi.getMine(),
    enabled: Boolean(user?.company_id),
    staleTime: 60_000,
  });

  const cleanedApiKey = useMemo(() => sanitizeCredential(apiKey), [apiKey]);
  const cleanedApiToken = useMemo(() => normalizeToken(apiToken), [apiToken]);

  const tokenAuthorizeUrl = useMemo(() => {
    if (!cleanedApiKey) return null;
    const params = new URLSearchParams({
      expiration: "never",
      name: "KPIMaster",
      scope: "read,write",
      response_type: "token",
      key: cleanedApiKey,
    });
    return `https://trello.com/1/authorize?${params.toString()}`;
  }, [cleanedApiKey]);

  useEffect(() => {
    if (companyQuery.data) {
      setCompanyForm({
        name: companyQuery.data.name,
        description: companyQuery.data.description ?? "",
        contact_email: companyQuery.data.contact_email ?? "",
      });
    }
  }, [companyQuery.data]);

  // Load saved settings from DB on mount
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const saved = await trelloApi.getSettings();
        if (cancelled) return;
        if (saved.has_credentials) {
          setApiKey(saved.api_key);
          setApiToken(saved.api_token);
          setSavedBoardIds(saved.selected_board_ids);
          setSettingsSaved(true);
        }
      } catch {
        // No saved settings yet — silently ignore
      } finally {
        if (!cancelled) setIsLoadingSettings(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // When credentials change, clear board list so user re-fetches
  useEffect(() => {
    setAvailableBoards([]);
    setSelectedBoardIds([]);
    setHasLoadedBoards(false);
  }, [cleanedApiKey, cleanedApiToken]);

  const validateToken = (): boolean => {
    if (cleanedApiToken && cleanedApiToken.length < 16) {
      setError("Your Trello token looks incomplete. Paste the full user token from Trello's authorize page.");
      return false;
    }
    return true;
  };

  const handleLoadBoards = async () => {
    if (!validateToken()) return;
    setIsFetchingBoards(true);
    setError(null);
    try {
      const boards = await trelloApi.listAvailableBoards({
        apiKey: cleanedApiKey || undefined,
        apiToken: cleanedApiToken || undefined,
      });
      setAvailableBoards(boards);
      // Pre-check previously saved board IDs (or all open boards if none saved)
      const preChecked =
        savedBoardIds.length > 0
          ? boards.filter((b) => savedBoardIds.includes(b.id)).map((b) => b.id)
          : boards.filter((b) => !b.is_closed).map((b) => b.id);
      setSelectedBoardIds(preChecked);
      setHasLoadedBoards(true);
    } catch (err) {
      setError(getTrelloErrorMessage(err));
    } finally {
      setIsFetchingBoards(false);
    }
  };

  const handleToggleBoard = (boardId: string, checked: boolean) => {
    setSelectedBoardIds((current) =>
      checked ? Array.from(new Set([...current, boardId])) : current.filter((id) => id !== boardId)
    );
  };

  const handleSaveSettings = async () => {
    if (!validateToken()) return;
    if (hasLoadedBoards && selectedBoardIds.length === 0) {
      setError("Select at least one Trello board before saving.");
      return;
    }
    setIsSavingSettings(true);
    setError(null);
    try {
      const result = await trelloApi.saveSettings({
        apiKey: cleanedApiKey || undefined,
        apiToken: cleanedApiToken || undefined,
        selectedBoardIds: hasLoadedBoards ? selectedBoardIds : savedBoardIds,
      });
      setSavedBoardIds(result.selected_board_ids);
      setSettingsSaved(true);
    } catch (err) {
      setError(getTrelloErrorMessage(err));
    } finally {
      setIsSavingSettings(false);
    }
  };

  const handleImport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!validateToken()) return;
    const boardIds = hasLoadedBoards ? selectedBoardIds : savedBoardIds;
    if (boardIds.length === 0) {
      setError("Load boards and select at least one before importing.");
      return;
    }
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await trelloApi.importBoards({
        apiKey: cleanedApiKey || undefined,
        apiToken: cleanedApiToken || undefined,
        boardIds,
      });
      setImported(result);
      if (result[0]) {
        await refreshProjects(result[0].project_id);
      }
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      queryClient.invalidateQueries({ queryKey: ["kpis"] });
      queryClient.invalidateQueries({ queryKey: ["sprint"] });
      queryClient.invalidateQueries({ queryKey: ["blockers"] });
      queryClient.invalidateQueries({ queryKey: ["team-kpis"] });
      queryClient.invalidateQueries({ queryKey: ["client-progress"] });
    } catch (err) {
      setError(getTrelloErrorMessage(err) || "Failed to import Trello boards.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSaveCompany = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCompanySaved(false);
    await companyApi.updateMine(companyForm);
    await companyQuery.refetch();
    setCompanySaved(true);
  };

  if (isLoadingSettings) {
    return <DashboardLayout><LoadingSpinner label="Loading saved settings…" /></DashboardLayout>;
  }

  const boardIdsForImport = hasLoadedBoards ? selectedBoardIds : savedBoardIds;

  if (isDeveloper) {
    return (
      <DashboardLayout>
        <div className="mx-auto max-w-5xl space-y-6">
          {companyQuery.data && (
            <form onSubmit={handleSaveCompany} className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm space-y-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
                  Company Workspace
                </p>
                <h1 className="mt-2 text-2xl font-bold text-foreground">Company profile</h1>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  This information is managed by your company workspace administrators.
                </p>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="company-name">Company name</Label>
                  <Input id="company-name" value={companyForm.name} disabled />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="company-email">Contact email</Label>
                  <Input id="company-email" value={companyForm.contact_email} disabled />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="company-description">Description</Label>
                <Textarea id="company-description" value={companyForm.description} disabled />
              </div>
            </form>
          )}
          <div className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Developer Access
            </p>
            <h1 className="mt-2 text-3xl font-bold text-foreground">Workspace settings are read-only</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Trello connection management is limited to company administrators and managers. Your account can still access personal KPI dashboards.
            </p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="mx-auto max-w-5xl space-y-6">
        <Tabs defaultValue="company" className="w-full">
          <TabsList className="mb-6 grid w-full max-w-2xl grid-cols-2 md:grid-cols-4">
            <TabsTrigger value="company">Workspace Profile</TabsTrigger>
            <TabsTrigger value="trello">Trello Integration</TabsTrigger>
            <TabsTrigger value="assistant">AI Assistant</TabsTrigger>
            {(user?.role === "client_admin" || user?.role === "client_pm") && (
              <TabsTrigger value="outsourcing">Outsourcing</TabsTrigger>
            )}
          </TabsList>

          <TabsContent value="company" className="mt-0 space-y-6">
            {companyQuery.data && (
              <form onSubmit={handleSaveCompany} className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm space-y-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
                Company Workspace
              </p>
              <h1 className="mt-2 text-2xl font-bold text-foreground">Manage company profile</h1>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Keep your workspace details current for company users and developer accounts.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="company-name">Company name</Label>
                <Input
                  id="company-name"
                  value={companyForm.name}
                  onChange={(e) => setCompanyForm((current) => ({ ...current, name: e.target.value }))}
                  disabled={isDeveloper}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="company-email">Contact email</Label>
                <Input
                  id="company-email"
                  value={companyForm.contact_email}
                  onChange={(e) => setCompanyForm((current) => ({ ...current, contact_email: e.target.value }))}
                  disabled={isDeveloper}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="company-description">Description</Label>
              <Textarea
                id="company-description"
                value={companyForm.description}
                onChange={(e) => setCompanyForm((current) => ({ ...current, description: e.target.value }))}
                disabled={isDeveloper}
              />
            </div>
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                Workspace slug: <span className="font-semibold text-foreground">{companyQuery.data.slug}</span>
              </p>
              {!isDeveloper && <Button type="submit" variant="outline">Save company profile</Button>}
            </div>
            {companySaved && (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-4 py-3 text-sm text-emerald-600">
                Company profile updated.
              </div>
            )}
          </form>
        )}
        </TabsContent>

        <TabsContent value="trello" className="mt-0 space-y-6">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            Trello Integration
          </p>
          <h1 className="mt-2 text-3xl font-bold text-foreground">Connect a real Trello board</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Load the boards available to your Trello account, pick only the ones you need, save your
            selection to the database, then import to start syncing live data.
          </p>
        </div>

        {settingsSaved && !hasLoadedBoards && (
          <div className="rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm text-primary">
            Settings loaded from database.
            {savedBoardIds.length > 0 && (
              <> {savedBoardIds.length} board{savedBoardIds.length !== 1 ? "s" : ""} previously selected.</>
            )}
            {" "}Click <strong>Load Available Boards</strong> to see your choices or <strong>Import Selected Boards</strong> to sync now.
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-[1.35fr_0.85fr]">
          <form onSubmit={handleImport} className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm">
            <div className="space-y-5">

              {/* Credentials */}
              <div>
                <Label htmlFor="api-key">Trello API key</Label>
                <Input
                  id="api-key"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Optional if configured in backend env"
                  autoComplete="off"
                />
                {tokenAuthorizeUrl && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Need a token?{" "}
                    <a href={tokenAuthorizeUrl} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">
                      Generate a Trello user token for this API key
                    </a>
                  </p>
                )}
              </div>

              <div>
                <Label htmlFor="api-token">Trello API token</Label>
                <Input
                  id="api-token"
                  type="password"
                  value={apiToken}
                  onChange={(e) => setApiToken(e.target.value)}
                  placeholder="Paste the Trello user token, not the app secret"
                  autoComplete="off"
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  If you paste a full authorize URL, KPIMaster will extract the token automatically.
                </p>
              </div>

              {/* Step 1 — Load boards */}
              <div className="rounded-xl border border-border/80 bg-background/40 p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-sm font-semibold text-foreground">1. Load available boards</h2>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Fetches board names only — fast, no sync yet.
                    </p>
                  </div>
                  <Button type="button" variant="secondary" onClick={handleLoadBoards} disabled={isFetchingBoards}>
                    {isFetchingBoards ? "Loading…" : "Load Available Boards"}
                  </Button>
                </div>

                {isFetchingBoards && <LoadingSpinner className="py-8" label="Fetching Trello boards…" />}

                {hasLoadedBoards && !isFetchingBoards && (
                  <div className="mt-4 space-y-4">
                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <p className="text-sm text-muted-foreground">
                        {availableBoards.length > 0
                          ? `${availableBoards.length} boards found — pick the ones you want.`
                          : "No boards returned for these credentials."}
                      </p>
                      {availableBoards.length > 0 && (
                        <div className="flex flex-wrap gap-2">
                          <Button type="button" variant="outline" size="sm"
                            onClick={() => setSelectedBoardIds(availableBoards.map((b) => b.id))}>
                            Select all
                          </Button>
                          <Button type="button" variant="ghost" size="sm"
                            onClick={() => setSelectedBoardIds([])}>
                            Clear
                          </Button>
                        </div>
                      )}
                    </div>

                    {availableBoards.length > 0 && (
                      <div className="max-h-80 space-y-3 overflow-y-auto pr-1">
                        {availableBoards.map((board) => (
                          <label
                            key={board.id}
                            htmlFor={`board-${board.id}`}
                            className="flex cursor-pointer items-start gap-3 rounded-xl border border-border/80 bg-card/60 p-4"
                          >
                            <Checkbox
                              id={`board-${board.id}`}
                              checked={selectedBoardIds.includes(board.id)}
                              onCheckedChange={(checked) => handleToggleBoard(board.id, checked === true)}
                              className="mt-0.5"
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="text-sm font-semibold text-foreground">{board.name}</p>
                                {board.is_closed && (
                                  <span className="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                                    Closed
                                  </span>
                                )}
                                {savedBoardIds.includes(board.id) && (
                                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.15em] text-primary">
                                    Saved
                                  </span>
                                )}
                              </div>
                              <p className="mt-1 text-xs text-muted-foreground">{board.id}</p>
                              {board.description && (
                                <p className="mt-2 text-xs leading-5 text-muted-foreground">{board.description}</p>
                              )}
                            </div>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {error && (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              )}

              {/* Step 2 — Save settings */}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-xl border border-border/80 bg-background/40 p-4">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">2. Save settings</h2>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Persists your credentials and board selection to the database — no sync yet.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={handleSaveSettings}
                  disabled={isSavingSettings || (!cleanedApiKey && !cleanedApiToken)}
                >
                  {isSavingSettings ? "Saving…" : settingsSaved ? "Update Saved Settings" : "Save Settings"}
                </Button>
              </div>

              {/* Step 3 — Import / sync */}
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-xl border border-border/80 bg-background/40 p-4">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">3. Import selected boards</h2>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {boardIdsForImport.length > 0
                      ? `Syncs ${boardIdsForImport.length} board${boardIdsForImport.length !== 1 ? "s" : ""} into KPIMaster.`
                      : "Load boards above and select the ones you want first."}
                  </p>
                </div>
                <Button type="submit" disabled={isSubmitting || isFetchingBoards || boardIdsForImport.length === 0}>
                  {isSubmitting ? "Importing…" : "Import Selected Boards"}
                </Button>
              </div>

            </div>
          </form>

          <div className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-foreground">How it works</h2>
            <ul className="mt-4 space-y-3 text-sm text-muted-foreground">
              <li><strong className="text-foreground">Load</strong> — fetches board names instantly, no data sync.</li>
              <li><strong className="text-foreground">Select</strong> — pick only the boards you care about.</li>
              <li><strong className="text-foreground">Save</strong> — stores your choice in the database so you never re-enter credentials.</li>
              <li><strong className="text-foreground">Import</strong> — syncs live Trello data for selected boards only.</li>
            </ul>

            {settingsSaved && savedBoardIds.length > 0 && (
              <div className="mt-6">
                <h3 className="text-sm font-semibold text-foreground">Saved board selection</h3>
                <ul className="mt-2 space-y-1">
                  {savedBoardIds.map((id) => {
                    const board = availableBoards.find((b) => b.id === id);
                    return (
                      <li key={id} className="text-xs text-muted-foreground font-mono">
                        {board ? board.name : id}
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </div>
        </div>

        {imported.length > 0 && (
          <div className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-foreground">Imported projects</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Open any imported project directly from the current session.
            </p>
            <div className="mt-4 grid gap-3">
              {imported.map((item) => (
                <div
                  key={item.board_id}
                  className="flex flex-col gap-3 rounded-xl border border-border/80 bg-background/60 p-4 md:flex-row md:items-center md:justify-between"
                >
                  <div>
                    <p className="text-sm font-semibold text-foreground">{item.board_name}</p>
                    <p className="text-xs text-muted-foreground">
                      Project key {item.project_key} · Trello board {item.trello_board_id}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button asChild variant="secondary">
                      <a href={`/?project=${item.project_key}`}>Open Dashboard</a>
                    </Button>
                    {item.short_url && (
                      <Button asChild variant="outline">
                        <a href={item.short_url} target="_blank" rel="noreferrer">Open Trello Board</a>
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        </TabsContent>

        <TabsContent value="assistant" className="mt-0">
          <div className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm">
            <AssistantStats />
          </div>
        </TabsContent>

        <TabsContent value="outsourcing" className="mt-0">
          <OutsourcingPartners />
        </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default Settings;