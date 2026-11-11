import React from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { Card } from "../components/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/StateViews";
import { StatusPill } from "../components/StatusPill";
import { mismatchLabel } from "../services/adapters";
import { colors, spacing } from "../styles/theme";
import type { ScreenProps } from "./types";

export function RepositoryScreen({ project, data, isLoading, error, isRefreshing, onRefresh }: ScreenProps) {
  if (isLoading) return <LoadingState title="Loading repository checks" />;
  if (error) return <ErrorState message={error} onRetry={onRefresh} />;
  if (!project) return <EmptyState title="No project" message="Select a project to review repository mismatch signals." />;

  const mismatches = data?.repositoryMismatches ?? [];
  return (
    <ScrollView
      refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      contentContainerStyle={styles.content}
    >
      <Card style={styles.summary}>
        <Text style={styles.title}>Repository health</Text>
        <Text style={styles.copy}>
          {mismatches.length} mismatch signal(s) are visible for {project.name}. Use this view to reconcile ticket state with code activity.
        </Text>
      </Card>

      {mismatches.length === 0 ? (
        <EmptyState title="No mismatches visible" message="Repository and ticket activity are currently aligned, or no repository provider is connected for this project." />
      ) : null}

      {mismatches.map((mismatch) => (
        <Card key={mismatch.id} style={styles.row}>
          <View style={styles.top}>
            <Text style={styles.ticket}>T-{mismatch.ticket_id}</Text>
            <StatusPill label={mismatch.mismatch_type ?? "Mismatch"} tone="warning" />
          </View>
          <Text style={styles.branch}>{mismatch.branch_name ?? "No branch linked"}</Text>
          <Text style={styles.copy}>{mismatchLabel(mismatch)}</Text>
          <Text style={styles.meta}>
            {mismatch.commit_count} commit(s) · {mismatch.pr_count} PR(s) · {mismatch.pr_merged ? "merged" : "not merged"}
          </Text>
        </Card>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.lg,
    gap: spacing.md,
    paddingBottom: 120
  },
  summary: {
    gap: spacing.sm
  },
  row: {
    gap: spacing.sm
  },
  top: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md,
    alignItems: "center"
  },
  title: {
    color: colors.text,
    fontWeight: "900",
    fontSize: 22
  },
  ticket: {
    color: colors.primary,
    fontWeight: "900",
    fontSize: 13
  },
  branch: {
    color: colors.text,
    fontSize: 17,
    fontWeight: "900"
  },
  copy: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21
  },
  meta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700"
  }
});
