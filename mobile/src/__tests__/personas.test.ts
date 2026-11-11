import { canMutateDelivery, getPersonaFamily, getRoutesForUser, roleTitle } from "../domain/personas";
import type { AuthUser } from "../domain/types";

function user(role: AuthUser["role"]): AuthUser {
  return {
    id: 1,
    username: role,
    email: `${role}@example.com`,
    role,
    company_id: 1,
    company_name: "Demo",
    company_slug: "demo",
    developer_id: role === "developer" ? 10 : null,
    kpi_subject_id: role === "developer" ? 10 : null,
    is_active: true,
    is_superuser: role === "super_admin"
  };
}

describe("mobile persona routing", () => {
  it("maps supported roles to persona families", () => {
    expect(getPersonaFamily("client_admin")).toBe("Client");
    expect(getPersonaFamily("client_exec")).toBe("Executive");
    expect(getPersonaFamily("esn_admin")).toBe("Vendor");
    expect(getPersonaFamily("developer")).toBe("Developer");
    expect(getPersonaFamily("super_admin")).toBe("Admin");
  });

  it("hides admin integration surfaces from developers", () => {
    const routeKeys = getRoutesForUser(user("developer")).map((route) => route.key);
    expect(routeKeys).toContain("home");
    expect(routeKeys).toContain("tickets");
    expect(routeKeys).not.toContain("integrations");
    expect(routeKeys).not.toContain("repository");
  });

  it("allows delivery mutation for PM and vendor roles but not executives", () => {
    expect(canMutateDelivery(user("client_pm"))).toBe(true);
    expect(canMutateDelivery(user("esn_delivery_manager"))).toBe(true);
    expect(canMutateDelivery(user("client_exec"))).toBe(false);
  });

  it("exposes readable role titles for mobile headers", () => {
    expect(roleTitle(user("client_exec"))).toBe("Client Executive");
    expect(roleTitle(user("esn_delivery_manager"))).toBe("Vendor Delivery Lead");
  });
});
