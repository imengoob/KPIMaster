import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Ticket,
  Activity,
  AlertTriangle,
  Users,
  BriefcaseBusiness,
  GitBranch,
  Plug,
  Settings,
  LogOut,
  LineChart,
  Network,
  History,
  ListChecks,
} from "lucide-react";
import { cn } from "@/lib/utils";
import ProjectSwitcher from "@/components/ProjectSwitcher";
import { isDeveloperUser, useAuth } from "@/contexts/AuthContext";

const companyNavItems = [
  { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
  { icon: Activity, label: "Sprint Monitor", path: "/sprint" },
  { icon: Ticket, label: "Ticket Analysis", path: "/tickets" },
  { icon: AlertTriangle, label: "Blockers", path: "/blockers" },
  { icon: ListChecks, label: "Actions", path: "/actions" },
  { icon: Users, label: "Developer Progress", path: "/developers" },
  { icon: LineChart, label: "Responsiveness", path: "/responsiveness" },
  { icon: BriefcaseBusiness, label: "Client Progress", path: "/client-progress" },
  { icon: Network, label: "Recruiting Network", path: "/recruiting-network" },
  { icon: GitBranch, label: "Repository", path: "/repository" },
  { icon: Plug, label: "Integrations", path: "/integrations" },
];

const vendorNavItems = [
  { icon: BriefcaseBusiness, label: "Vendor Dashboard", path: "/vendor-dashboard" },
  { icon: Users, label: "Developer Progress", path: "/developers" },
  { icon: LineChart, label: "Responsiveness", path: "/responsiveness" },
  { icon: AlertTriangle, label: "Blockers", path: "/blockers" },
  { icon: ListChecks, label: "Actions", path: "/actions" },
];

const developerNavItems = [
  { icon: LayoutDashboard, label: "My Dashboard", path: "/developer-dashboard" },
  { icon: ListChecks, label: "My Actions", path: "/my-actions" },
  { icon: Users, label: "Team Developers", path: "/developers" },
  { icon: History, label: "Client History", path: "/developer-history" },
];

/** KPIMaster logo mark — pulse line inside a rounded-square badge */
const KPIMasterLogo = () => (
  <svg viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-9 w-9 shrink-0">
    <rect width="36" height="36" rx="8" fill="url(#sp-grad)" />
    <polyline
      points="3,18 8,18 11,10 15,26 18,14 21,22 24,18 33,18"
      stroke="white"
      strokeWidth="2.4"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <defs>
      <linearGradient id="sp-grad" x1="0" y1="0" x2="36" y2="36">
        <stop offset="0%" stopColor="#06c4e3" />
        <stop offset="100%" stopColor="#0ea5e9" />
      </linearGradient>
    </defs>
  </svg>
);

/** Norma Tunisie wordmark — small decorative badge */
const NormaBadge = () => (
  <div className="flex items-center gap-1.5">
    {/* Mini N icon */}
    <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5 shrink-0">
      <rect width="16" height="16" rx="3.5" fill="url(#nt-grad)" />
      <path d="M4 12V4l8 8V4" stroke="white" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <defs>
        <linearGradient id="nt-grad" x1="0" y1="0" x2="16" y2="16">
          <stop offset="0%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#6366f1" />
        </linearGradient>
      </defs>
    </svg>
    <span className="text-[10px] font-semibold tracking-wide text-sidebar-foreground/70">
      Norma Tunisie
    </span>
  </div>
);

interface AppSidebarProps {
  className?: string;
  onNavigate?: () => void;
}

const AppSidebar = ({ className, onNavigate }: AppSidebarProps) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const navItems = isDeveloperUser(user) 
    ? developerNavItems 
    : (user?.role === "esn_admin" || user?.role === "esn_delivery_manager")
      ? vendorNavItems
      : companyNavItems;

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <aside className={cn("fixed left-0 top-0 z-40 flex h-screen  w-64  overflow-y-auto flex-col bg-sidebar border-r border-sidebar-border scrollbar-hide", className)}>

      {/* ── Brand / Logo ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-5 py-4 border-b border-sidebar-border">
        <KPIMasterLogo />
        <div className="min-w-0">
          <h1 className="text-sm font-bold tracking-tight text-sidebar-accent-foreground leading-none">
            KPIMaster
          </h1>
          <p className="text-[11px] text-sidebar-foreground/70 mt-0.5 leading-none">
            AI Sprint Monitor
          </p>
        </div>
      </div>

      {/* ── Project Switcher ─────────────────────────────────────────────── */}
      <div className="px-3 py-3 border-b border-sidebar-border">
        <ProjectSwitcher />
      </div>

      {/* ── Navigation ───────────────────────────────────────────────────── */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path ||
            (item.path !== "/" && location.pathname.startsWith(item.path));
          return (
            <NavLink
              key={item.path}
              to={item.path}
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
                isActive
                  ? "bg-sidebar-accent text-sidebar-primary"
                  : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              )}
            >
              <item.icon
                className={cn(
                  "h-4 w-4 shrink-0",
                  isActive ? "text-sidebar-primary" : "text-sidebar-foreground/60",
                )}
              />
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <div className="border-t border-sidebar-border">
        {/* Settings link - hidden for vendors & developers */}
        {user && !["esn_admin", "esn_delivery_manager", "developer"].includes(user.role) && (
          <div className="px-3 pt-3 pb-1">
            <NavLink
              to="/settings"
              onClick={onNavigate}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-150",
                location.pathname === "/settings"
                  ? "bg-sidebar-accent text-sidebar-primary"
                  : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              )}
            >
              <Settings
                className={cn(
                  "h-4 w-4 shrink-0",
                  location.pathname === "/settings"
                    ? "text-sidebar-primary"
                    : "text-sidebar-foreground/60",
                )}
              />
              Settings
            </NavLink>
          </div>
        )}

        {user && (
          <div className="px-5 pb-2">
            <div className="rounded-lg border border-sidebar-border bg-sidebar-accent/30 px-3 py-2.5 space-y-1">
              <p className="text-[9px] uppercase tracking-widest text-sidebar-foreground/40 font-medium">
                Workspace
              </p>
              <p className="text-xs font-semibold text-sidebar-accent-foreground">
                {user.company_name ?? user.username}
              </p>
              <p className="text-[10px] capitalize text-sidebar-foreground/60">
                {user.role.replace("_", " ")}
              </p>
            </div>
          </div>
        )}

        {/* Logout */}
        <div className="px-3 pb-2">
          <button
            onClick={handleLogout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-sidebar-foreground transition-all duration-150 hover:bg-destructive/10 hover:text-destructive"
          > 
            <LogOut className="h-4 w-4 shrink-0 text-sidebar-foreground/60" />
            <span className="flex-1 text-left">Sign out</span>
            {user?.username && (
              <span className="truncate max-w-[80px] text-[11px] text-sidebar-foreground/40">
                {user.username}
              </span>
            )}
          </button>
        </div>

        {/* Powered by Norma Tunisie */}
        <div className="px-5 pb-4 pt-1">
          <div className="rounded-lg border border-sidebar-border bg-sidebar-accent/30 px-3 py-2.5 space-y-1">
            <p className="text-[9px] uppercase tracking-widest text-sidebar-foreground/40 font-medium">
              Powered by
            </p>
            <NormaBadge />
          </div> 
        </div>
      </div>

    </aside>
  );
};

export default AppSidebar;
