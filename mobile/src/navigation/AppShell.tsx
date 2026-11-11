import React, { useCallback, useMemo, useState } from "react";
import { Pressable, SafeAreaView, ScrollView, StyleSheet, Text, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { ProjectPicker } from "../components/ProjectPicker";
import { LoadingState } from "../components/StateViews";
import { MobileRouteKey, ROUTES, getDefaultRoute, getRoutesForUser, roleTitle } from "../domain/personas";
import { useDashboardData } from "../hooks/useDashboardData";
import { RealtimeStatus, useRealtime } from "../hooks/useRealtime";
import { useAuth } from "../state/AuthContext";
import { useProject } from "../state/ProjectContext";
import { colors, spacing } from "../styles/theme";
import { AssistantScreen } from "../screens/AssistantScreen";
import { BlockersScreen } from "../screens/BlockersScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { IntegrationsScreen } from "../screens/IntegrationsScreen";
import { ProfileScreen } from "../screens/ProfileScreen";
import { RepositoryScreen } from "../screens/RepositoryScreen";
import { SprintScreen } from "../screens/SprintScreen";
import { TicketsScreen } from "../screens/TicketsScreen";

export function AppShell() {
  const { user, token } = useAuth();
  const { projects, currentProject, selectProject, isLoadingProjects } = useProject();
  const [route, setRoute] = useState<MobileRouteKey>(getDefaultRoute(user));
  const [refreshSignal, setRefreshSignal] = useState(0);

  const bumpRefresh = useCallback(() => setRefreshSignal((value) => value + 1), []);
  const realtimeStatus = useRealtime({
    token,
    projectId: currentProject?.id,
    onMessage: bumpRefresh
  });

  const dashboard = useDashboardData(currentProject?.id, user, refreshSignal);
  const routes = useMemo(() => getRoutesForUser(user), [user]);

  if (!user || isLoadingProjects) {
    return <LoadingState title="Preparing mobile workspace" />;
  }

  const screenProps = {
    user,
    project: currentProject,
    data: dashboard.data,
    isLoading: dashboard.isLoading,
    error: dashboard.error,
    isRefreshing: dashboard.isRefreshing,
    onRefresh: dashboard.refresh
  };

  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text style={styles.appName}>KPIMaster</Text>
          <Text style={styles.role} numberOfLines={1}>{roleTitle(user)}</Text>
        </View>
        <RealtimeDot status={realtimeStatus} />
      </View>

      <ProjectPicker projects={projects} currentProject={currentProject} onSelect={(project) => void selectProject(project)} />

      <View style={styles.content}>
        {route === "home" ? <HomeScreen {...screenProps} /> : null}
        {route === "sprint" ? <SprintScreen {...screenProps} /> : null}
        {route === "tickets" ? <TicketsScreen {...screenProps} /> : null}
        {route === "blockers" ? <BlockersScreen {...screenProps} /> : null}
        {route === "repository" ? <RepositoryScreen {...screenProps} /> : null}
        {route === "integrations" ? <IntegrationsScreen {...screenProps} /> : null}
        {route === "assistant" ? <AssistantScreen {...screenProps} /> : null}
        {route === "profile" ? <ProfileScreen {...screenProps} realtimeStatus={realtimeStatus} /> : null}
      </View>

      <View style={styles.navWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.nav}>
          {routes.map((item) => {
            const active = route === item.key;
            return (
              <Pressable
                accessibilityRole="tab"
                key={item.key}
                onPress={() => setRoute(item.key)}
                style={[styles.tab, active && styles.activeTab]}
              >
                <Feather name={routeIcon(item.key)} size={17} color={active ? "#FFFFFF" : colors.muted} />
                <Text style={[styles.tabLabel, active && styles.activeTabLabel]}>{ROUTES[item.key].compactLabel}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

function routeIcon(route: MobileRouteKey): React.ComponentProps<typeof Feather>["name"] {
  const icons: Record<MobileRouteKey, React.ComponentProps<typeof Feather>["name"]> = {
    home: "bar-chart-2",
    sprint: "activity",
    tickets: "check-square",
    blockers: "alert-triangle",
    repository: "git-branch",
    integrations: "refresh-cw",
    assistant: "message-circle",
    profile: "user"
  };
  return icons[route];
}

function RealtimeDot({ status }: { status: RealtimeStatus }) {
  const connected = status === "connected";
  return (
    <View style={styles.realtime}>
      <View style={[styles.dot, { backgroundColor: connected ? colors.success : status === "error" ? colors.danger : colors.warning }]} />
      <Text style={styles.realtimeText}>{connected ? "Live" : status}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.canvas
  },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.md
  },
  headerText: {
    flex: 1
  },
  appName: {
    color: colors.text,
    fontSize: 26,
    fontWeight: "900"
  },
  role: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700",
    marginTop: 2
  },
  realtime: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: 999,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: colors.border
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 999
  },
  realtimeText: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800",
    textTransform: "capitalize"
  },
  content: {
    flex: 1
  },
  navWrap: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    backgroundColor: "rgba(255,255,255,0.96)"
  },
  nav: {
    padding: spacing.md,
    gap: spacing.sm
  },
  tab: {
    minHeight: 46,
    minWidth: 78,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: spacing.xs,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: "#FFFFFF",
    paddingHorizontal: spacing.lg
  },
  activeTab: {
    backgroundColor: colors.ink,
    borderColor: colors.ink
  },
  tabLabel: {
    color: colors.muted,
    fontWeight: "900",
    fontSize: 13
  },
  activeTabLabel: {
    color: "#FFFFFF"
  }
});
