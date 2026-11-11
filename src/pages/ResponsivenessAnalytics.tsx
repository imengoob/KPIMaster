import React from 'react';
import { useProject } from '@/contexts/ProjectContext';
import { useResponsivenessAnalytics } from '@/hooks/useResponsiveness';
import DashboardLayout from '@/components/DashboardLayout';
import ErrorState from '@/components/ErrorState';
import LoadingSpinner from '@/components/LoadingSpinner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Clock, MessageSquare, Activity, AlertTriangle, UserCheck, UserMinus } from 'lucide-react';
import { getApiDateRange } from '@/lib/dateRange';
import { isTrelloCompatiblePlatform, PLATFORM_LABELS } from '@/lib/platforms';
import { cn } from '@/lib/utils';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const ResponsivenessAnalytics = () => {
  const { currentProject, globalDateRange, globalPlatformFilter } = useProject();
  const { startDate, endDate } = getApiDateRange(globalDateRange);
  const { data, isLoading, isError, error, refetch } = useResponsivenessAnalytics(
    currentProject?.id,
    startDate,
    endDate,
    globalPlatformFilter,
  );

  if (!currentProject) {
    return (
      <DashboardLayout>
        <ErrorState
          title="No Workspace Selected"
          message="Please select a workspace from the sidebar to view developer responsiveness analytics."
          onRetry={() => {}}
        />
      </DashboardLayout>
    );
  }

  if (!isTrelloCompatiblePlatform(globalPlatformFilter)) {
    return (
      <DashboardLayout>
        <ErrorState
          message={`Responsiveness analytics currently use Trello activity. Switch the platform filter from ${PLATFORM_LABELS[globalPlatformFilter]} to Trello or All Platforms.`}
        />
      </DashboardLayout>
    );
  }

  if (isLoading) {
    return (
      <DashboardLayout>
        <div className="flex h-full items-center justify-center">
          <LoadingSpinner label="Computing responsiveness SLA metrics..." />
        </div>
      </DashboardLayout>
    );
  }

  if (isError || !data) {
    return (
      <DashboardLayout>
        <ErrorState
          title="Failed to Load Analytics"
          message={error?.message || "We encountered an error while aggregating responsiveness data."}
          onRetry={() => refetch()}
        />
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="flex flex-col space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">Responsiveness Analytics</h1>
          <p className="text-muted-foreground mt-2">
            Monitor developer engagement, ticket reaction times, and communication SLAs.
          </p>
        </div>

        {/* Global KPIs */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <Card className="bg-card/50 backdrop-blur-sm border-white/10 hover:border-white/20 transition-all duration-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Avg First Reaction</CardTitle>
              <Activity className="h-4 w-4 text-emerald-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-foreground">
                {data.global_avg_reaction_hours !== null ? `${data.global_avg_reaction_hours}h` : 'N/A'}
              </div>
              <p className="text-xs text-muted-foreground mt-1">Time to first card action</p>
            </CardContent>
          </Card>

          <Card className="bg-card/50 backdrop-blur-sm border-white/10 hover:border-white/20 transition-all duration-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Avg First Response</CardTitle>
              <MessageSquare className="h-4 w-4 text-blue-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-foreground">
                {data.global_avg_response_hours !== null ? `${data.global_avg_response_hours}h` : 'N/A'}
              </div>
              <p className="text-xs text-muted-foreground mt-1">Time to first comment</p>
            </CardContent>
          </Card>

          <Card className="bg-card/50 backdrop-blur-sm border-white/10 hover:border-white/20 transition-all duration-300">
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">Active Engagement</CardTitle>
              <UserCheck className="h-4 w-4 text-indigo-500" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold text-foreground">
                {data.active_developers} <span className="text-sm text-muted-foreground font-normal">Active</span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {data.dormant_developers} dormant developers
              </p>
            </CardContent>
          </Card>

          <Card className={cn(
            "bg-card/50 backdrop-blur-sm border-white/10 transition-all duration-300",
            data.total_sla_breaches > 0 ? "border-rose-500/50 hover:border-rose-500/80" : "hover:border-white/20"
          )}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">SLA Breaches</CardTitle>
              <AlertTriangle className={cn("h-4 w-4", data.total_sla_breaches > 0 ? "text-rose-500" : "text-emerald-500")} />
            </CardHeader>
            <CardContent>
              <div className={cn("text-2xl font-bold", data.total_sla_breaches > 0 ? "text-rose-500" : "text-emerald-500")}>
                {data.total_sla_breaches}
              </div>
              <p className="text-xs text-muted-foreground mt-1">Inactivity &gt; 24h</p>
            </CardContent>
          </Card>
        </div>

        <div className="grid gap-6 grid-cols-1 lg:grid-cols-7">
          {/* Detailed Table */}
          <Card className="lg:col-span-4 bg-card/40 backdrop-blur-sm border-white/10 overflow-hidden flex flex-col">
            <CardHeader>
              <CardTitle>Developer Engagement</CardTitle>
              <CardDescription>Individual metrics for communication and responsiveness.</CardDescription>
            </CardHeader>
            <CardContent className="p-0 overflow-auto flex-1">
              <Table>
                <TableHeader>
                  <TableRow className="border-white/10 hover:bg-white/5">
                    <TableHead className="w-[200px]">Developer</TableHead>
                    <TableHead className="text-center">Vol (R/C)</TableHead>
                    <TableHead className="text-center">First Reaction</TableHead>
                    <TableHead className="text-center">First Response</TableHead>
                    <TableHead className="text-right">SLA Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.developers.map((dev) => (
                    <TableRow key={dev.developer_id} className="border-white/5 hover:bg-white/5">
                      <TableCell className="font-medium">
                        <div className="flex items-center space-x-2">
                          <div className={cn(
                            "h-2 w-2 rounded-full",
                            dev.total_reactions > 0 ? "bg-emerald-500" : "bg-neutral-600"
                          )} />
                          <span>{dev.developer_name}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-center">
                        <span className="text-muted-foreground text-xs">
                          {dev.total_reactions} / {dev.total_comments}
                        </span>
                      </TableCell>
                      <TableCell className="text-center">
                        {dev.avg_first_reaction_hours !== null ? `${dev.avg_first_reaction_hours}h` : '-'}
                      </TableCell>
                      <TableCell className="text-center">
                        {dev.avg_first_response_hours !== null ? `${dev.avg_first_response_hours}h` : '-'}
                      </TableCell>
                      <TableCell className="text-right">
                        {dev.sla_breaching_tickets > 0 ? (
                          <Badge variant="destructive" className="bg-rose-500/20 text-rose-300 hover:bg-rose-500/30 border-rose-500/30">
                            {dev.sla_breaching_tickets} Breach
                          </Badge>
                        ) : dev.inactivity_duration_hours !== null ? (
                          <span className="text-xs text-muted-foreground flex items-center justify-end">
                            <Clock className="w-3 h-3 mr-1" />
                            {dev.inactivity_duration_hours}h ago
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">No Active Work</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                  {data.developers.length === 0 && (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center h-24 text-muted-foreground">
                        No developers tracked for this project's responsiveness.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Volume Chart */}
          <Card className="lg:col-span-3 bg-card/40 backdrop-blur-sm border-white/10 flex flex-col pt-4">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Engagement Volume Distribution</CardTitle>
            </CardHeader>
            <CardContent className="flex-1 min-h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.developers} layout="vertical" margin={{ top: 0, right: 30, left: 40, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="rgba(255,255,255,0.05)" />
                  <XAxis type="number" stroke="rgba(255,255,255,0.5)" fontSize={12} />
                  <YAxis type="category" dataKey="developer_name" stroke="rgba(255,255,255,0.5)" fontSize={12} hide />
                  <Tooltip
                    contentStyle={{ backgroundColor: 'rgba(10, 10, 10, 0.95)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px' }}
                    itemStyle={{ color: '#fff' }}
                  />
                  <Bar dataKey="total_reactions" name="Reactions" fill="#10b981" radius={[0, 4, 4, 0]} />
                  <Bar dataKey="total_comments" name="Comments" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
};

export default ResponsivenessAnalytics;
