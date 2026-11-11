import type { AuthUser, PersonaFamily, UserRole } from "./types";

export type MobileRouteKey =
  | "home"
  | "sprint"
  | "tickets"
  | "blockers"
  | "repository"
  | "integrations"
  | "assistant"
  | "profile";

export interface MobileRouteConfig {
  key: MobileRouteKey;
  label: string;
  compactLabel: string;
}

export const ROUTES: Record<MobileRouteKey, MobileRouteConfig> = {
  home: { key: "home", label: "Overview", compactLabel: "Home" },
  sprint: { key: "sprint", label: "Sprint", compactLabel: "Sprint" },
  tickets: { key: "tickets", label: "Tickets", compactLabel: "Tickets" },
  blockers: { key: "blockers", label: "Blockers", compactLabel: "Risk" },
  repository: { key: "repository", label: "Repository", compactLabel: "Repo" },
  integrations: { key: "integrations", label: "Integrations", compactLabel: "Sync" },
  assistant: { key: "assistant", label: "Assistant", compactLabel: "Ask" },
  profile: { key: "profile", label: "Profile", compactLabel: "Me" }
};

export const CLIENT_ROLES: UserRole[] = ["company_admin", "company_manager", "client_admin", "client_pm"];
export const EXECUTIVE_ROLES: UserRole[] = ["client_exec"];
export const VENDOR_ROLES: UserRole[] = ["esn_admin", "esn_delivery_manager"];
export const ADMIN_ROLES: UserRole[] = ["super_admin"];

export function getPersonaFamily(role: UserRole): PersonaFamily {
  if (ADMIN_ROLES.includes(role)) return "Admin";
  if (role === "developer") return "Developer";
  if (EXECUTIVE_ROLES.includes(role)) return "Executive";
  if (VENDOR_ROLES.includes(role)) return "Vendor";
  if (role === "auditor_readonly") return "Auditor";
  return "Client";
}

export function isDeveloper(user: AuthUser | null): boolean {
  return user?.role === "developer";
}

export function isVendor(user: AuthUser | null): boolean {
  return Boolean(user && VENDOR_ROLES.includes(user.role));
}

export function isExecutive(user: AuthUser | null): boolean {
  return user?.role === "client_exec";
}

export function getDefaultRoute(user: AuthUser | null): MobileRouteKey {
  if (!user) return "home";
  if (isDeveloper(user)) return "home";
  if (isVendor(user)) return "home";
  return "home";
}

export function getRoutesForUser(user: AuthUser | null): MobileRouteConfig[] {
  if (!user) return [];
  const base: MobileRouteKey[] = ["home", "sprint", "tickets", "blockers", "assistant", "profile"];

  if (!isDeveloper(user)) {
    base.splice(4, 0, "repository");
  }

  if (ADMIN_ROLES.includes(user.role) || CLIENT_ROLES.includes(user.role) || VENDOR_ROLES.includes(user.role)) {
    base.splice(base.length - 2, 0, "integrations");
  }

  if (isExecutive(user)) {
    const executiveRoutes: MobileRouteKey[] = ["home", "sprint", "tickets", "blockers", "repository", "assistant", "profile"];
    return executiveRoutes.map((key) => ROUTES[key]);
  }

  return base.map((key) => ROUTES[key]);
}

export function canMutateDelivery(user: AuthUser | null): boolean {
  if (!user) return false;
  return [
    "super_admin",
    "company_admin",
    "company_manager",
    "client_admin",
    "client_pm",
    "esn_admin",
    "esn_delivery_manager"
  ].includes(user.role);
}

export function roleTitle(user: AuthUser | null): string {
  if (!user) return "Signed out";
  const family = getPersonaFamily(user.role);
  if (family === "Executive") return "Client Executive";
  if (family === "Vendor") return user.role === "esn_delivery_manager" ? "Vendor Delivery Lead" : "Vendor Admin";
  if (family === "Developer") return "Developer";
  if (family === "Admin") return "Platform Admin";
  if (family === "Auditor") return "Auditor";
  return user.role === "client_pm" || user.role === "company_manager" ? "Client PM" : "Client Admin";
}
