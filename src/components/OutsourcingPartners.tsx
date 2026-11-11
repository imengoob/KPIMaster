import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronsUpDown, Building, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { engagementApi } from "@/services/api/engagements";
import { companyApi } from "@/services/api/companies";
import { developerApi } from "@/services/api/developers";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { BackendTrelloMemberCandidate, BackendCompany } from "@/services/api/types";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem } from "@/components/ui/command";

export function OutsourcingPartners() {
  const { currentProject } = useProject();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const projectId = currentProject?.id;

  const [vendorId, setVendorId] = useState<string>("");
  const [engagementName, setEngagementName] = useState("");
  const [engagementError, setEngagementError] = useState<string | null>(null);

  const vendorsQ = useQuery({
    queryKey: ["companies", "vendor"],
    queryFn: () => companyApi.getAll("vendor"),
    staleTime: 60_000,
  });

  const engagementsQ = useQuery({
    queryKey: ["engagements", projectId],
    queryFn: () => engagementApi.list(projectId),
    staleTime: 60_000,
    enabled: Boolean(projectId),
  });
  
  const engagements = engagementsQ.data ?? [];
  const [activeEngagementId, setActiveEngagementId] = useState<number | null>(null);

  const [vendorOpen, setVendorOpen] = useState(false);
  const [devOpen, setDevOpen] = useState(false);

  const devsQ = useQuery({
    queryKey: ["developers", projectId],
    queryFn: () => developerApi.getAll(projectId),
    staleTime: 60_000,
    enabled: Boolean(projectId),
  });
  const allDevs = devsQ.data ?? [];
  
  // Set default active engagement
  if (engagements.length > 0 && activeEngagementId === null) {
      setActiveEngagementId(engagements[0].id);
  }

  const createEngMut = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No active project");
      if (!vendorId) throw new Error("Select a vendor partner");
      return engagementApi.create({
        name: engagementName || `Integration with Vendor ${vendorId}`,
        status: "active",
        vendor_company_id: Number(vendorId),
        project_id: projectId,
        client_visible: true,
      });
    },
    onSuccess: (eng) => {
      queryClient.invalidateQueries({ queryKey: ["engagements", projectId] });
      setActiveEngagementId(eng.id);
      setEngagementName("");
      setVendorId("");
      setEngagementError(null);
    },
    onError: (err) => setEngagementError(err instanceof Error ? err.message : "Failed to create engagement"),
  });

  // Developer matcher state
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("developer");
  const [team, setTeam] = useState("");
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [candidates, setCandidates] = useState<BackendTrelloMemberCandidate[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const candidateMut = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No active project");
      return developerApi.findTrelloMemberCandidates(projectId, fullName.trim());
    },
    onSuccess: (rows) => {
      setCandidates(rows);
      setSelectedMemberId(rows[0]?.trello_member_id ?? "");
      setMessage(rows.length ? null : "No close Trello member match found. You can still save the developer without a Trello link.");
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Could not load Trello members."),
  });

  const saveMut = useMutation({
    mutationFn: () => {
      if (!activeEngagementId) throw new Error("No active engagement is available for this project.");
      return developerApi.upsertVendorDeveloperProfile({
        fullName: fullName.trim(),
        email: email.trim() || undefined,
        role: role.trim() || "developer",
        team: team.trim() || undefined,
        engagementId: activeEngagementId,
        trelloMemberId: selectedMemberId || undefined,
      });
    },
    onSuccess: async (result) => {
      setMessage(
        result.matched_trello_member_name
          ? `Saved ${result.developer.name} and linked Trello member ${result.matched_trello_member_name}.`
          : `Saved ${result.developer.name}. Add a Trello match later to include board work in KPIs.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["team-kpis", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["client-progress", projectId] });
      await queryClient.invalidateQueries({ queryKey: ["developers", projectId] });
      setFullName("");
      setEmail("");
      setTeam("");
      setSelectedMemberId("");
      setCandidates([]);
    },
    onError: (error) => setMessage(error instanceof Error ? error.message : "Could not save developer profile."),
  });

  if (!projectId) {
    return <div className="p-6 text-sm text-muted-foreground bg-card border rounded-2xl">Please select a project first.</div>;
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm">
         <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
              Outsourcing
            </p>
            <h1 className="mt-2 text-2xl font-bold text-foreground">Manage Outsourcing Partners</h1>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Map vendor companies to your current project. Doing this allows you to see their respective developer contributions in tracking boards.
            </p>
         </div>

         <div className="grid gap-6 mt-6 md:grid-cols-2">
            <div className="space-y-4 p-5 rounded-xl border border-border bg-background/50">
               <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Building className="w-4 h-4 text-emerald-500" />
                  Connect New Vendor
               </h3>
               
               <div className="space-y-2">
                  <Label>Select Vendor Company</Label>
                  <Popover open={vendorOpen} onOpenChange={setVendorOpen}>
                     <PopoverTrigger asChild>
                        <Button
                           variant="outline"
                           role="combobox"
                           aria-expanded={vendorOpen}
                           className="w-full justify-between font-normal"
                           disabled={vendorsQ.isLoading}
                        >
                           {vendorId
                              ? vendorsQ.data?.find((v) => String(v.id) === vendorId)?.name
                              : vendorsQ.isLoading ? "Loading..." : "Select Vendor..."}
                           <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                     </PopoverTrigger>
                     <PopoverContent className="w-[300px] p-0" align="start">
                        <Command>
                           <CommandInput placeholder="Search vendor..." />
                           <CommandList>
                              <CommandEmpty>No vendor found.</CommandEmpty>
                              <CommandGroup>
                                 {vendorsQ.data?.map((v) => (
                                    <CommandItem
                                       key={v.id}
                                       value={v.name}
                                       onSelect={() => {
                                          setVendorId(String(v.id) === vendorId ? "" : String(v.id));
                                          setVendorOpen(false);
                                       }}
                                    >
                                       <Check
                                          className={cn(
                                             "mr-2 h-4 w-4",
                                             vendorId === String(v.id) ? "opacity-100" : "opacity-0"
                                          )}
                                       />
                                       {v.name}
                                    </CommandItem>
                                 ))}
                              </CommandGroup>
                           </CommandList>
                        </Command>
                     </PopoverContent>
                  </Popover>
               </div>

               <div className="space-y-2">
                  <Label>Engagement Name</Label>
                  <Input 
                    placeholder="e.g. Q3 Mobile App Development" 
                    value={engagementName}
                    onChange={(e) => setEngagementName(e.target.value)}
                  />
               </div>

               {engagementError && <p className="text-xs text-rose-500">{engagementError}</p>}
               
               <Button 
                 onClick={() => createEngMut.mutate()} 
                 disabled={!vendorId || createEngMut.isPending}
                 className="w-full"
               >
                 {createEngMut.isPending ? "Creating..." : "Establish Engagement"}
               </Button>
            </div>

            <div className="space-y-4">
               <h3 className="text-sm font-semibold flex items-center gap-2">
                  <Users className="w-4 h-4 text-violet-500" />
                  Active Engagements on Project
               </h3>
               {engagements.length === 0 ? (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-lg">
                     No outsourcing engagements for this project yet.
                  </div>
               ) : (
                  <div className="space-y-3">
                     {engagements.map(eng => (
                        <div key={eng.id} className="p-3 border rounded-lg bg-card flex justify-between items-center">
                           <div>
                              <p className="text-sm font-bold">{eng.name}</p>
                              <p className="text-xs text-muted-foreground">{eng.vendor_company_name}</p>
                           </div>
                           <span className="px-2 py-0.5 text-[10px] font-semibold bg-emerald-500/10 text-emerald-600 rounded-full">
                              Active
                           </span>
                        </div>
                     ))}
                  </div>
               )}
            </div>
         </div>
      </div>

      {engagements.length > 0 && (
        <div className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-600">Vendor Roster Matching</p>
              <h3 className="mt-1 text-base font-bold text-foreground">Add an external developer by full name</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                We match the vendor developer to Trello board members, then KPIs only include their assigned cards.
              </p>
            </div>
            
            <Select
              value={String(activeEngagementId ?? "")}
              onValueChange={(val) => setActiveEngagementId(Number(val))}
            >
              <SelectTrigger className="w-56">
                <SelectValue placeholder="Select Engagement" />
              </SelectTrigger>
              <SelectContent>
                {engagements.map((engagement) => (
                  <SelectItem key={engagement.id} value={String(engagement.id)}>
                    {engagement.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-4">
             <div className="space-y-2 md:col-span-2">
               <Label>Full Name</Label>
               <Popover open={devOpen} onOpenChange={setDevOpen}>
                  <PopoverTrigger asChild>
                     <Button
                        variant="outline"
                        role="combobox"
                        aria-expanded={devOpen}
                        className={cn("w-full justify-between font-normal text-left", !fullName && "text-muted-foreground")}
                     >
                        {fullName || "e.g. Alice Chen (type to search or add)"}
                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                     </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-[400px] p-0" align="start">
                     <Command>
                        <CommandInput
                           placeholder="Search existing developer or type new name..."
                           value={fullName}
                           onValueChange={setFullName}
                        />
                        <CommandList>
                           <CommandEmpty>
                              {fullName ? (
                                 <div className="flex flex-col gap-2">
                                    <span className="text-muted-foreground">No existing matching developer.</span>
                                    <Button
                                       size="sm"
                                       onClick={() => setDevOpen(false)}
                                    >
                                       Use "{fullName}"
                                    </Button>
                                 </div>
                              ) : (
                                 "Type a name..."
                              )}
                           </CommandEmpty>
                           <CommandGroup>
                              {allDevs.filter(d => !fullName || d.name.toLowerCase().includes(fullName.toLowerCase())).map((d) => (
                                 <CommandItem
                                    key={d.id}
                                    value={d.name}
                                    onSelect={(currentValue) => {
                                       setFullName(d.name);
                                       setRole(d.role || "Developer");
                                       setDevOpen(false);
                                    }}
                                 >
                                    <Check
                                       className={cn(
                                          "mr-2 h-4 w-4",
                                          fullName === d.name ? "opacity-100" : "opacity-0"
                                       )}
                                    />
                                    {d.name} <span className="ml-2 text-xs text-muted-foreground">({d.role})</span>
                                 </CommandItem>
                              ))}
                           </CommandGroup>
                        </CommandList>
                     </Command>
                  </PopoverContent>
               </Popover>
            </div>
            <div className="space-y-2">
               <Label>Email (optional)</Label>
               <Input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="alice@vendor.com"
               />
            </div>
            <div className="space-y-2">
               <Label>Role</Label>
               <Input
                  value={role}
                  onChange={(event) => setRole(event.target.value)}
                  placeholder="Developer"
               />
            </div>
            <div className="space-y-2 md:col-span-2">
               <Label>Team (optional)</Label>
               <Input
                  value={team}
                  onChange={(event) => setTeam(event.target.value)}
                  placeholder="Frontend Team"
               />
            </div>

            <div className="md:col-span-4 flex gap-3 mt-2">
               <Button
                  variant="secondary"
                  disabled={!fullName.trim() || candidateMut.isPending}
                  onClick={() => candidateMut.mutate()}
               >
                  {candidateMut.isPending ? "Finding…" : "Find Trello Match"}
               </Button>
               <Button
                  disabled={!fullName.trim() || !activeEngagementId || saveMut.isPending}
                  onClick={() => saveMut.mutate()}
               >
                  {saveMut.isPending ? "Saving…" : "Save Developer"}
               </Button>
            </div>
          </div>
          {candidates.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2 p-3 bg-muted/40 rounded-lg border border-border">
              <p className="w-full text-xs font-semibold text-muted-foreground mb-1">Select Trello Profile Match:</p>
              {candidates.map((candidate) => (
                <button
                  type="button"
                  key={candidate.trello_member_id}
                  onClick={() => setSelectedMemberId(candidate.trello_member_id)}
                  className={cn(
                    "rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                    selectedMemberId === candidate.trello_member_id
                      ? "border-primary bg-primary text-primary-foreground shadow-sm"
                      : "border-border bg-background text-muted-foreground hover:border-primary/50",
                  )}
                >
                  {candidate.full_name}
                  {candidate.username && ` (@${candidate.username})`}
                  {" · "}
                  {Math.round(candidate.match_score * 100)}%
                </button>
              ))}
            </div>
          )}
          {message && (
            <p className="mt-4 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm text-primary font-medium">
              {message}
            </p>
          )}
        </div>
      )}

      {/* Show currently saved developers below */}
      {allDevs.length > 0 && (
        <div className="rounded-2xl border border-border bg-card/80 p-6 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-600">Saved Roster</p>
          <h3 className="mt-1 text-base font-bold text-foreground">Registered Developers</h3>
          <p className="mt-1 text-sm text-muted-foreground mb-4">
            These developers are actively mapped to this project and their KPIs are being tracked.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
             {allDevs.map(dev => (
               <div key={dev.id} className="flex items-center gap-3 p-3 rounded-xl border border-border bg-background shadow-xs">
                 <div className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-white font-bold shrink-0">
                   {dev.avatar}
                 </div>
                 <div className="overflow-hidden">
                   <p className="text-sm font-semibold text-foreground truncate">{dev.name}</p>
                   <p className="text-xs text-muted-foreground truncate">{dev.role}</p>
                 </div>
               </div>
             ))}
          </div>
        </div>
      )}
    </div>
  );
}
