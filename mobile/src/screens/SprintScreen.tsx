import React from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { Card } from "../components/Card";
import { MetricCard } from "../components/MetricCard";
import { ProgressBar } from "../components/ProgressBar";
import { EmptyState, ErrorState, LoadingState } from "../components/StateViews";
import { formatHours, formatPercent, sprintCompletion } from "../services/adapters";
import { colors, spacing } from "../styles/theme";
import type { ScreenProps } from "./types";

export function SprintScreen({ project, data, isLoading, error, isRefreshing, onRefresh }: ScreenProps) {
  if (isLoading) return <LoadingState title="Loading sprint KPIs" />;
  if (error) return <ErrorState message={error} onRetry={onRefresh} />;
  if (!project || !data?.sprint) {
    return <EmptyState title="No sprint selected" message="Select a project with an active sprint to see burndown and delivery KPIs." />;
  }

  const sprint = data.sprint;
  const kpis = data.kpis?.current_kpis;
  const completion = sprintCompletion(sprint);

  return (
    <ScrollView
      refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      contentContainerStyle={styles.content}
    >
      <Card style={styles.section}>
        <Text style={styles.eyebrow}>{project.key}</Text>
        <Text style={styles.title}>{sprint.name}</Text>
        <Text style={styles.copy}>{sprint.goal ?? "Sprint goal is not documented yet."}</Text>
        <ProgressBar value={completion} tone={completion >= 0.7 ? colors.success : colors.warning} />
        <View style={styles.pointsRow}>
          <Text style={styles.points}>{sprint.completed_points} done</Text>
          <Text style={styles.points}>{sprint.committed_points} committed</Text>
        </View>
      </Card>

      <View style={styles.grid}>
        <MetricCard label="Completion" value={formatPercent(kpis?.completion_rate ?? completion)} helper="Sprint KPI" tone="success" icon="target" />
        <MetricCard label="Velocity" value={kpis?.velocity?.toFixed(0) ?? sprint.velocity} helper="Story points" tone="accent" icon="zap" />
        <MetricCard label="Cycle time" value={formatHours(kpis?.cycle_time_hours)} helper="Average flow time" icon="clock" />
        <MetricCard label="Lead time" value={formatHours(kpis?.lead_time_hours)} helper="Creation to done" icon="trending-up" />
        <MetricCard label="Estimation" value={formatPercent(kpis?.estimation_accuracy)} helper="Accuracy score" tone="warning" icon="crosshair" />
        <MetricCard label="Throughput" value={kpis?.throughput?.toFixed(1) ?? "N/A"} helper="Done per day" icon="check-circle" />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.lg,
    gap: spacing.lg,
    paddingBottom: 120
  },
  section: {
    gap: spacing.md
  },
  eyebrow: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "900"
  },
  title: {
    color: colors.text,
    fontSize: 26,
    fontWeight: "900"
  },
  copy: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21
  },
  pointsRow: {
    flexDirection: "row",
    justifyContent: "space-between"
  },
  points: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700"
  },
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md
  }
});
