import { Toaster } from "@/components/ui/toaster";
import { ThemeProvider } from "@/components/ThemeProvider";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import { ProjectProvider } from "@/contexts/ProjectContext";
import { AuthProvider, getDefaultHomePath, isDeveloperUser, useAuth } from "@/contexts/AuthContext";
import SprintAssistant from "@/components/SprintAssistant";
import LoadingSpinner from "@/components/LoadingSpinner";
import Dashboard from "./pages/Dashboard";
import SprintMonitor from "./pages/SprintMonitor";
import TicketAnalysis from "./pages/TicketAnalysis";
import BlockerDetection from "./pages/BlockerDetection";
import DeveloperProgress from "./pages/DeveloperProgress";
import DeveloperDashboard from "./pages/DeveloperDashboard";
import ClientProgress from "./pages/ClientProgress";
import VendorDashboard from "./pages/VendorDashboard";
import RepositoryIntegration from "./pages/RepositoryIntegration";
import Actions from "./pages/Actions";
import Integrations from "./pages/Integrations";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import Register from "./pages/Register";
import NotFound from "./pages/NotFound";
import ResponsivenessAnalytics from "./pages/ResponsivenessAnalytics";
import RecruitingNetwork from "./pages/RecruitingNetwork";
import DeveloperHistory from "./pages/DeveloperHistory";

const queryClient = new QueryClient();

const ProtectedApp = () => {
  const { isAuthenticated, isAuthLoading } = useAuth();
  if (isAuthLoading) return <LoadingSpinner label="Checking session..." />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return (
    <ProjectProvider>
      {/* Floating AI assistant — rendered outside routes so it persists across page navigation */}
      <SprintAssistant />
      <Outlet />
    </ProjectProvider>
  );
};

const CompanyOnly = () => {
  const { user } = useAuth();
  if (isDeveloperUser(user)) {
    return <Navigate to="/developers" replace />;
  }
  return <Outlet />;
};

const DefaultRoute = () => {
  const { user } = useAuth();
  return <Navigate to={getDefaultHomePath(user)} replace />;
};

const App = () => (
  <ThemeProvider defaultTheme="dark" storageKey="kpimaster-theme">
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <AuthProvider>
          <Toaster />
          <Sonner />
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route element={<ProtectedApp />}>
                <Route path="/" element={<DefaultRoute />} />
                <Route element={<CompanyOnly />}>
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/sprint" element={<SprintMonitor />} />
                  <Route path="/sprint-monitor" element={<SprintMonitor />} />
                  <Route path="/tickets" element={<TicketAnalysis />} />
                  <Route path="/ticket-analysis" element={<TicketAnalysis />} />
                  <Route path="/blockers" element={<BlockerDetection />} />
                  <Route path="/blocker-detection" element={<BlockerDetection />} />
                  <Route path="/actions" element={<Actions />} />
                  <Route path="/client-progress" element={<ClientProgress />} />
                  <Route path="/vendor-dashboard" element={<VendorDashboard />} />
                  <Route path="/repository" element={<RepositoryIntegration />} />
                  <Route path="/repository-integration" element={<RepositoryIntegration />} />
                  <Route path="/integrations" element={<Integrations />} />
                  <Route path="/analytics/responsiveness" element={<ResponsivenessAnalytics />} />
                  <Route path="/responsiveness" element={<ResponsivenessAnalytics />} />
                </Route>
                <Route path="/developers" element={<DeveloperProgress />} />
                <Route path="/developer-progress" element={<DeveloperProgress />} />
                <Route path="/developer-dashboard" element={<DeveloperDashboard />} />
                <Route path="/developer-history" element={<DeveloperHistory />} />
                <Route path="/recruiting-network" element={<RecruitingNetwork />} />
                <Route path="/my-actions" element={<Actions />} />
                <Route path="/settings" element={<Settings />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </TooltipProvider>
    </QueryClientProvider>
  </ThemeProvider>
);

export default App;
