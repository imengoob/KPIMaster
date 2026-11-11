import React, { useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/StateViews";
import { StatusPill } from "../components/StatusPill";
import { canMutateDelivery } from "../domain/personas";
import type { Blocker } from "../domain/types";
import { kpiApi } from "../services/api";
import { blockerSeverity, formatHours } from "../services/adapters";
import { colors, spacing } from "../styles/theme";
import type { ScreenProps } from "./types";

export function BlockersScreen({ user, project, data, isLoading, error, isRefreshing, onRefresh }: ScreenProps) {
  const [pendingId, setPendingId] = useState<number | null>(null);

  if (isLoading) return <LoadingState title="Loading blocker intelligence" />;
  if (error) return <ErrorState message={error} onRetry={onRefresh} />;
  if (!project) return <EmptyState title="No project" message="Select a project to review blocker escalation." />;

  const blockers = data?.blockers ?? [];
  const canAct = canMutateDelivery(user);

  const runAction = async (blocker: Blocker, type: "prompt_developer" | "alert_lead" | "escalate_management" | "resolve") => {
    setPendingId(blocker.id);
    try {
      if (type === "resolve") await kpiApi.blockers.resolve(blocker.id);
      else await kpiApi.blockers.action(blocker.id, type);
      await onRefresh();
    } finally {
      setPendingId(null);
    }
  };

  return (
    <ScrollView
      refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      contentContainerStyle={styles.content}
    >
      {blockers.length === 0 ? (
        <EmptyState title="No active blockers" message="The selected project has no active blockers visible for this persona." />
      ) : null}

      {blockers.map((blocker) => (
        <Card key={blocker.id} style={styles.blocker}>
          <View style={styles.topRow}>
            <StatusPill label={`Level ${blocker.escalation_level}`} tone={blockerSeverity(blocker) === "critical" ? "danger" : blockerSeverity(blocker) === "warning" ? "warning" : "info"} />
            <Text style={styles.stall}>{formatHours(blocker.stall_hours)} stalled</Text>
          </View>
          <Text style={styles.title}>{blocker.ticket_title ?? `Ticket ${blocker.ticket_id}`}</Text>
          <Text style={styles.copy}>{blocker.description ?? "No activity detected on this ticket."}</Text>
          {canAct ? (
            <View style={styles.actions}>
              <Button label="Prompt" variant="ghost" onPress={() => runAction(blocker, "prompt_developer")} loading={pendingId === blocker.id} style={styles.actionButton} />
              <Button label="Escalate" variant="secondary" onPress={() => runAction(blocker, "escalate_management")} loading={pendingId === blocker.id} style={styles.actionButton} />
              <Button label="Resolve" variant="primary" onPress={() => runAction(blocker, "resolve")} loading={pendingId === blocker.id} style={styles.actionButton} />
            </View>
          ) : (
            <Text style={styles.readOnly}>Read-only for your persona.</Text>
          )}
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
  blocker: {
    gap: spacing.md
  },
  topRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md
  },
  stall: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "800"
  },
  title: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "900",
    lineHeight: 23
  },
  copy: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21
  },
  actions: {
    flexDirection: "row",
    gap: spacing.sm,
    flexWrap: "wrap"
  },
  actionButton: {
    minHeight: 44,
    flexGrow: 1
  },
  readOnly: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "700"
  }
});
