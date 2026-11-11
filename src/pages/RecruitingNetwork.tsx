import React, { useEffect, useState } from "react";
import DashboardLayout from "../components/DashboardLayout";
import { Users, Briefcase, Code, Link, GitBranch } from "lucide-react";
import { BackendDeveloperRecruitingProfile, BackendCompanyPartnershipResponse } from "../services/api/types";
import { developerApi } from "../services/api/developers";
import { companyApi } from "../services/api/companies";

export default function RecruitingNetwork() {
  const [profiles, setProfiles] = useState<BackendDeveloperRecruitingProfile[]>([]);
  const [partners, setPartners] = useState<BackendCompanyPartnershipResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [poolRes, partnerRes] = await Promise.all([
          developerApi.getRecruitingPool(),
          companyApi.getPartnerships()
        ]);
        setProfiles(poolRes || []);
        setPartners(partnerRes || []);
      } catch (err) {
        console.error("Failed to load recruiting network", err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">B2B Recruiting Network</h1>
          <p className="text-muted-foreground">Discover and recruit developers from your partnered outsourcing companies.</p>
        </div>

        {/* Partners Section */}
        <section>
          <h2 className="text-xl font-semibold mb-3 flex items-center space-x-2">
            <Link className="h-5 w-5 text-primary" />
            <span>Active ESN Partnerships</span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {partners.map(p => (
              <div key={p.id} className="bg-card border border-border/50 rounded-xl p-4 flex justify-between items-center shadow-sm">
                <div>
                  <h3 className="font-medium">{p.vendor_company?.name || `Vendor #${p.vendor_company_id}`}</h3>
                  <span className="text-xs text-muted-foreground bg-secondary px-2 rounded-full mt-1 inline-block">
                    {p.status}
                  </span>
                </div>
                <Briefcase className="h-8 w-8 text-primary/30" />
              </div>
            ))}
            {partners.length === 0 && !loading && (
              <div className="col-span-full py-8 text-center bg-card border border-border/50 rounded-xl shadow-sm text-muted-foreground">
                <Link className="h-10 w-10 mx-auto mb-2 opacity-50" />
                <p>No active partnerships yet.</p>
              </div>
            )}
          </div>
        </section>

        {/* Developer Pool Section */}
        <section>
          <h2 className="text-xl font-semibold mb-3 flex items-center space-x-2 mt-8">
            <Users className="h-5 w-5 text-primary" />
            <span>Available Developers</span>
          </h2>
          {loading ? (
             <div className="p-12 text-center text-muted-foreground animate-pulse">Loading profiles...</div>
          ) : (
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              {profiles.map(({ developer, vendor_company_name, kpis }) => (
                <div key={developer.id} className="bg-card border border-border shadow-sm rounded-xl overflow-hidden hover:shadow-md transition-shadow">
                  <div className="p-5 border-b border-border/50 flex items-start justify-between bg-secondary/20">
                    <div>
                      <h3 className="text-lg font-bold flex items-center space-x-2">
                        <span>{developer.name}</span>
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                          {developer.role}
                        </span>
                      </h3>
                      <p className="text-sm text-muted-foreground flex items-center mt-1">
                        <Briefcase className="h-3 w-3 mr-1" /> from {vendor_company_name}
                      </p>
                    </div>
                    {/* Avatar Initials */}
                    <div className="h-12 w-12 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 text-white flex items-center justify-center font-bold text-lg shadow-inner">
                      {developer.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase()}
                    </div>
                  </div>
                  
                  <div className="p-5">
                    <div className="mb-4">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2 flex items-center">
                        <Code className="h-3 w-3 mr-1" /> Skills
                      </h4>
                      <div className="flex flex-wrap gap-1.5">
                        {developer.skills && developer.skills.length > 0 ? developer.skills.map((skill, idx) => (
                           <span key={idx} className="bg-secondary text-secondary-foreground text-xs px-2 py-1 rounded-md border border-border/60">
                             {skill}
                           </span>
                        )) : (
                          <span className="text-sm text-muted-foreground italic">No skills listed</span>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-3 gap-3 bg-secondary/10 p-3 rounded-lg border border-border/30">
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Completion Rate</p>
                        <p className="font-semibold">{kpis ? `${(kpis.completion_rate * 100).toFixed(0)}%` : 'N/A'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Avg Cycle</p>
                        <p className="font-semibold">{kpis && kpis.avg_cycle_time_hours ? `${kpis.avg_cycle_time_hours.toFixed(1)}h` : 'N/A'}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground mb-1">Status</p>
                        <p className="font-semibold text-green-500">Available</p>
                      </div>
                    </div>

                    <div className="mt-5 flex gap-3">
                      <button className="flex-1 bg-primary text-primary-foreground hover:bg-primary/90 py-2 rounded-lg text-sm font-medium transition-colors shadow-sm">
                        Request Engagement
                      </button>
                      <button className="flex-1 bg-secondary text-secondary-foreground hover:bg-secondary/80 py-2 rounded-lg text-sm font-medium transition-colors border border-border shadow-sm">
                        View History
                      </button>
                    </div>
                  </div>
                </div>
              ))}

              {profiles.length === 0 && !loading && (
                <div className="col-span-full py-16 text-center bg-card border border-border rounded-xl text-muted-foreground shadow-sm">
                  <Users className="h-12 w-12 mx-auto mb-3 opacity-30" />
                  <h3 className="text-lg font-medium text-foreground">No Recruitable Profiles</h3>
                  <p className="mt-1 max-w-sm mx-auto">Your active ESN partners have not granted visibility to any developer profiles yet.</p>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </DashboardLayout>
  );
}
