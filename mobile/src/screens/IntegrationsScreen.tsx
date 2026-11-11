import React from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { Card } from "../components/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/StateViews";
import { StatusPill } from "../components/StatusPill";
import { colors, spacing } from "../styles/theme";
import type { ScreenProps } from "./types";

const providers = ["trello", "jira", "microsoft", "github"] as const;

export function IntegrationsScreen({ data, isLoading, error, isRefreshing, onRefresh }: ScreenProps) {
  if (isLoading) return <LoadingState title="Loading integration state" />;
  if (error) return <ErrorState message={error} onRetry={onRefresh} />;

  const accounts = data?.integrations ?? [];

  return (
    <ScrollView
      refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      contentContainerStyle={styles.content}
    >
      <Card style={styles.summary}>
        <Text style={styles.title}>Integration status</Text>
        <Text style={styles.copy}>
          Provider connections control whether mobile dashboards show live data or graceful empty states.
        </Text>
      </Card>

      {accounts.length === 0 ? (
        <EmptyState title="No connected accounts" message="Connect Trello, Jira, Microsoft Planner, or GitHub from the web integrations hub. Mobile will reflect synced state immediately." />
      ) : null}

      {providers.map((provider) => {
        const providerAccounts = accounts.filter((account) => account.provider === provider);
        return (
          <Card key={provider} style={styles.provider}>
            <View style={styles.top}>
              <Text style={styles.providerName}>{providerLabel(provider)}</Text>
              <StatusPill label={providerAccounts.length ? "Connected" : "Not connected"} tone={providerAccounts.length ? "success" : "neutral"} />
            </View>
            {providerAccounts.map((account) => (
              <View key={account.id} style={styles.accountRow}>
                <Text style={styles.account}>{account.account_name}</Text>
                <Text style={styles.meta}>Last sync: {account.last_sync_at ? new Date(account.last_sync_at).toLocaleString() : "Not synced yet"}</Text>
              </View>
            ))}
          </Card>
        );
      })}
    </ScrollView>
  );
}

function providerLabel(provider: string): string {
  if (provider === "microsoft") return "Microsoft Planner";
  return provider[0]?.toUpperCase() + provider.slice(1);
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
  title: {
    color: colors.text,
    fontSize: 22,
    fontWeight: "900"
  },
  copy: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21
  },
  provider: {
    gap: spacing.md
  },
  top: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md
  },
  providerName: {
    color: colors.text,
    fontWeight: "900",
    fontSize: 17
  },
  accountRow: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.md,
    gap: spacing.xs
  },
  account: {
    color: colors.text,
    fontWeight: "800",
    fontSize: 14
  },
  meta: {
    color: colors.muted,
    fontSize: 12
  }
});
