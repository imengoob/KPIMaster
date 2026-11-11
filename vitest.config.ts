import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json", "html", "lcov"],
      include: [
        "src/components/EmptyProjectState.tsx",
        "src/components/ErrorState.tsx",
        "src/components/KpiCard.tsx",
        "src/components/LoadingSpinner.tsx",
        "src/components/StatusBadge.tsx",
        "src/components/ThemeToggle.tsx",
        "src/contexts/**",
      ],
      exclude: [
        "src/**/*.d.ts",
        "src/test/**",
        "src/components/ui/**",        // generated shadcn components
        "src/main.tsx",
        "src/App.tsx",
        "src/vite-env.d.ts",
        "src/services/api/types.ts",   // pure TypeScript interfaces, no runtime code
        "src/services/api/index.ts",   // barrel re-export only
        "src/hooks/use-mobile.tsx",    // shadcn utility hook
        "src/hooks/use-toast.ts",      // shadcn utility hook
        "src/components/AppSidebar.tsx",    // nav shell, requires Router context
        "src/components/NavLink.tsx",       // nav shell, requires Router context
        "src/components/DashboardLayout.tsx", // layout shell
        "src/components/ProjectSwitcher.tsx", // nav shell
        "src/pages/Index.tsx",         // redirect stub
        "src/pages/NotFound.tsx",      // 404 stub
      ],
      thresholds: {
        // Unit gate for deterministic shared UI and context logic.
        // Route-level workflows are covered by Playwright E2E, including demo personas.
        lines: 97,
        functions: 97,
        branches: 97,
        statements: 97,
      },
    },
  },
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
});
