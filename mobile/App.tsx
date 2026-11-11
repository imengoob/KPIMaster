import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatusBar } from "expo-status-bar";
import { AppShell } from "./src/navigation/AppShell";
import { LoginScreen } from "./src/screens/LoginScreen";
import { AuthProvider, useAuth } from "./src/state/AuthContext";
import { ProjectProvider } from "./src/state/ProjectContext";
import { LoadingState } from "./src/components/StateViews";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 60_000
    }
  }
});

function Root() {
  const { isAuthenticated, isRestoring } = useAuth();

  if (isRestoring) return <LoadingState title="Restoring secure session" />;
  if (!isAuthenticated) return <LoginScreen />;

  return (
    <ProjectProvider>
      <AppShell />
    </ProjectProvider>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <StatusBar style="dark" />
        <Root />
      </AuthProvider>
    </QueryClientProvider>
  );
}
