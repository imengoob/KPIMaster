import React, { useEffect, useState } from "react";
import DashboardLayout from "../components/DashboardLayout";
import { History, Briefcase, Calendar, Code, Clock, AlertTriangle } from "lucide-react";
import { BackendDeveloperHistoryEntry, BackendDeveloperVisibilityResponse } from "../services/api/types";
import { developerApi } from "../services/api/developers";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../components/ui/use-toast";

export default function DeveloperHistory() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [history, setHistory] = useState<BackendDeveloperHistoryEntry[]>([]);
  const [requests, setRequests] = useState<BackendDeveloperVisibilityResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      const developerId = user?.developer_id; 
      if (!developerId) {
        setLoading(false);
        return;
      }
      try {
        const [histData, reqData] = await Promise.all([
          developerApi.getClientHistory(developerId),
          developerApi.getVisibilityRequests()
        ]);
        setHistory(histData || []);
        setRequests(reqData || []);
      } catch (err) {
        console.error("Failed to fetch developer data", err);
      } finally {
        setLoading(false);
      }
    };
    if (user) {
        fetchData();
    }
  }, [user]);

  const handleApprove = async (id: number) => {
    try {
      await developerApi.approveVisibilityRequest(id);
      setRequests(prev => prev.filter(r => r.id !== id));
      toast({ title: "Approved", description: "Your profile is now visible to the client." });
    } catch {
      toast({ title: "Error", description: "Failed to approve request.", variant: "destructive" });
    }
  };

  const handleReject = async (id: number) => {
    try {
      await developerApi.rejectVisibilityRequest(id);
      setRequests(prev => prev.filter(r => r.id !== id));
      toast({ title: "Rejected", description: "Profile visibility request rejected." });
    } catch {
      toast({ title: "Error", description: "Failed to reject request.", variant: "destructive" });
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground flex items-center gap-3">
            <History className="h-8 w-8 text-primary" />
            My Client History
          </h1>
          <p className="text-muted-foreground mt-1">Timeline of your past and current client engagements.</p>
        </div>

        {requests.length > 0 && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-5 mb-8">
            <h2 className="text-lg font-bold text-amber-500 flex items-center mb-3">
              <AlertTriangle className="h-5 w-5 mr-2" /> Action Required: Profile Sharing Requests
            </h2>
            <div className="space-y-3">
              {requests.map(req => (
                <div key={req.id} className="flex flex-col md:flex-row md:items-center justify-between bg-card p-4 rounded-lg border border-border">
                  <div>
                    <h3 className="font-medium">Client Request #{req.client_company_id}</h3>
                    <p className="text-sm text-muted-foreground mt-1">Your ESN wants to share your profile card to this client's recruiting pool.</p>
                  </div>
                  <div className="flex gap-2 mt-3 md:mt-0">
                    <button onClick={() => handleApprove(req.id)} className="bg-primary text-primary-foreground px-4 py-2 rounded-md text-sm font-medium hover:bg-primary/90">
                      Approve
                    </button>
                    <button onClick={() => handleReject(req.id)} className="bg-secondary text-secondary-foreground hover:bg-secondary/80 px-4 py-2 rounded-md text-sm font-medium border border-border">
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {loading ? (
          <div className="py-20 text-center animate-pulse text-muted-foreground">
            Loading your timeline...
          </div>
        ) : !user?.developer_id ? (
          <div className="py-16 text-center text-muted-foreground bg-card rounded-xl border border-border shadow-sm">
            <h2 className="text-xl font-medium mb-2">Not a Developer Account</h2>
            <p>This view is reserved for developer accounts to view their engagement history.</p>
          </div>
        ) : history.length === 0 ? (
          <div className="py-16 text-center text-muted-foreground bg-card rounded-xl border border-border shadow-sm">
            <Briefcase className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <h2 className="text-xl font-medium mb-1 text-foreground">No Engagements Yet</h2>
            <p>You have not been assigned to any client engagements.</p>
          </div>
        ) : (
          <div className="relative border-l-2 border-border ml-4 md:ml-6 mt-8 space-y-12">
            {history.map((entry, idx) => {
              const isCurrent = !entry.end_date;
              return (
                <div key={`${entry.engagement_id}-${idx}`} className="relative pl-8">
                  {/* Timeline Dot */}
                  <div className={`absolute -left-[11px] top-1.5 h-5 w-5 rounded-full border-4 border-background ${isCurrent ? 'bg-indigo-500' : 'bg-muted-foreground'}`}/>
                  
                  <div className="bg-card border border-border/60 hover:border-border transition-colors rounded-xl p-5 shadow-sm">
                    <div className="flex flex-col md:flex-row md:justify-between md:items-start gap-4">
                      <div>
                        <div className="flex items-center gap-3 mb-1">
                          <h3 className="text-xl font-bold text-foreground">{entry.client_company_name}</h3>
                          {isCurrent && (
                            <span className="bg-indigo-500/10 text-indigo-500 text-xs font-semibold px-2 py-0.5 rounded-full">
                              Active
                            </span>
                          )}
                        </div>
                        <p className="text-lg font-medium text-muted-foreground">{entry.engagement_name}</p>
                      </div>

                      <div className="flex flex-col gap-2 text-sm text-muted-foreground bg-secondary/30 p-3 rounded-lg border border-border/40">
                        <div className="flex items-center gap-2">
                          <Calendar className="h-4 w-4" />
                          <span>
                            {new Date(entry.start_date).toLocaleDateString(undefined, { year: 'numeric', month: 'short' })}
                            {' - '}
                            {isCurrent ? 'Present' : new Date(entry.end_date!).toLocaleDateString(undefined, { year: 'numeric', month: 'short' })}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Clock className="h-4 w-4" />
                          <span>{entry.allocation_percentage}% Allocation</span>
                        </div>
                      </div>
                    </div>

                    <div className="mt-5 border-t border-border/40 pt-4 flex flex-col gap-4">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <Code className="h-4 w-4 text-primary" />
                        Role: <span className="text-foreground ml-1">{entry.assignment_role}</span>
                      </div>
                      
                      {entry.kpis && (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-secondary/10 p-3 rounded-lg border border-border/30">
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">Completion Rate</p>
                            <p className="font-semibold">{Math.round(entry.kpis.completion_rate * 100)}%</p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">Avg Cycle</p>
                            <p className="font-semibold">{entry.kpis.avg_cycle_time_hours ? `${entry.kpis.avg_cycle_time_hours.toFixed(1)}h` : 'N/A'}</p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">Blocker Rate</p>
                            <p className="font-semibold">{Math.round(entry.kpis.blocker_rate * 100)}%</p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">Tickets Done</p>
                            <p className="font-semibold">{entry.kpis.tickets_done} / {entry.kpis.tickets_total}</p>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
