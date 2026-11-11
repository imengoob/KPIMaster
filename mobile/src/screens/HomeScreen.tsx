import React from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { Card } from "../components/Card";
import { IconBadge } from "../components/IconBadge";
import { EmptyState, ErrorState, LoadingState } from "../components/StateViews";
import { MetricCard } from "../components/MetricCard";
import { ProgressBar } from "../components/ProgressBar";
import { StatusPill } from "../components/StatusPill";
import { getPersonaFamily, roleTitle } from "../domain/personas";
import { summarizeDashboard } from "../services/adapters";
import { colors, spacing } from "../styles/theme";
import type { ScreenProps } from "./types";
import { LinearGradient } from "expo-linear-gradient";

export function HomeScreen({ user, project, data, isLoading, error, isRefreshing, onRefresh }: ScreenProps) {
  if (isLoading) return <LoadingState title="Loading mobile dashboard" />;
  if (error) return <ErrorState message={error} onRetry={onRefresh} />;
  if (!project) {
    return <EmptyState title="No project available" message="Your account has no visible project yet. Ask an admin to assign project access." />;
  }
  if (!data) return null;

  const summary = summarizeDashboard(data);
  const persona = getPersonaFamily(user.role);
  const topMembers = (
    data.clientProgress?.members.map((member) => ({
      developer_id: member.developer_id,
      developer_name: member.developer_name,
      role: member.role,
      status: member.status
    })) ??
    data.teamReport?.members.map((member) => ({
      developer_id: member.developer_id,
      developer_name: member.developer_name,
      role: member.role,
      status: member.status
    })) ??
    []
  ).slice(0, 3);

  return (
    <ScrollView
      refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      contentContainerStyle={styles.content}
    >
      <LinearGradient colors={["#0F172A", "#164E63", "#312E81"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.hero}>
        <View style={styles.heroTop}>
          <View style={styles.heroText}>
            <Text style={styles.eyebrow}>{roleTitle(user)}</Text>
            <Text style={styles.title}>{project.name}</Text>
          </View>
          <StatusPill label={persona} tone={persona === "Developer" ? "info" : persona === "Executive" ? "warning" : "success"} />
        </View>
        <Text style={styles.description}>
          {summary.sprintName} is at {Math.round(summary.sprintCompletion * 100)}% point completion with {summary.openBlockers} open blocker(s).
        </Text>
        <ProgressBar value={summary.sprintCompletion} tone={summary.openBlockers > 0 ? colors.warning : colors.success} />
      </LinearGradient>

      <View style={styles.metricsGrid}>
        <MetricCard label="Completion" value={summary.completionRate} helper={`${summary.completedPoints}/${summary.committedPoints} points`} tone="success" icon="target" />
        <MetricCard label="Velocity" value={summary.velocity} helper="Current sprint pace" tone="accent" icon="zap" />
        <MetricCard label="Blockers" value={summary.openBlockers} helper={`${summary.blockedTickets} blocked tickets`} tone={summary.openBlockers > 0 ? "danger" : "success"} icon="alert-triangle" />
        <MetricCard label="Quality" value={summary.lowQualityTickets} helper="Tickets below 60%" tone={summary.lowQualityTickets > 0 ? "warning" : "success"} icon="shield" />
      </View>

      <Card style={styles.section}>
        <View style={styles.sectionHeading}>
          <IconBadge name="compass" tone="primary" />
          <Text style={styles.sectionTitle}>Persona focus</Text>
        </View>
        <Text style={styles.sectionCopy}>{personaCopy(persona, summary.openBlockers, summary.repoMismatches)}</Text>
      </Card>

      <Card style={styles.section}>
        <View style={styles.sectionHeading}>
          <IconBadge name="users" tone="accent" />
          <Text style={styles.sectionTitle}>Delivery snapshot</Text>
        </View>
        {topMembers.length ? (
          topMembers.map((member) => (
            <View key={member.developer_id} style={styles.memberRow}>
              <View style={styles.memberInfo}>
                <Text style={styles.memberName}>{member.developer_name}</Text>
                <Text style={styles.memberMeta}>{member.role}</Text>
              </View>
              <StatusPill label={member.status} tone={member.status === "behind" ? "danger" : member.status === "at-risk" ? "warning" : "success"} />
            </View>
          ))
        ) : (
          <Text style={styles.emptyCopy}>No developer delivery rows are visible for this role/project yet.</Text>
        )}
      </Card>
    </ScrollView>
  );
}

function personaCopy(persona: string, blockers: number, mismatches: number): string {
  if (persona === "Developer") return "Start here to check assigned delivery health, blockers, and ticket quality before standup.";
  if (persona === "Vendor") return `Vendor delivery view: ${blockers} blocker(s) and ${mismatches} repository mismatch(es) need operational attention.`;
  if (persona === "Executive") return "Executive view keeps delivery confidence visible without tactical noise.";
  if (persona === "Admin") return "Admin view confirms integrations, data freshness, and project-level health across roles.";
  return "Client view summarizes sprint progress, delivery risk, and vendor execution clarity.";
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.lg,
    gap: spacing.lg,
    paddingBottom: 120
  },
  hero: {
    gap: spacing.lg,
    borderRadius: 24,
    padding: spacing.lg,
    overflow: "hidden"
  },
  heroTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: spacing.md
  },
  heroText: {
    flex: 1
  },
  eyebrow: {
    color: "#A5F3FC",
    fontSize: 12,
    fontWeight: "900",
    textTransform: "uppercase"
  },
  title: {
    color: "#FFFFFF",
    fontSize: 25,
    fontWeight: "900",
    lineHeight: 30
  },
  description: {
    color: "#DBEAFE",
    fontSize: 14,
    lineHeight: 21
  },
  metricsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md
  },
  section: {
    gap: spacing.md
  },
  sectionHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md
  },
  sectionTitle: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "900"
  },
  sectionCopy: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21
  },
  memberRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border
  },
  memberInfo: {
    flex: 1
  },
  memberName: {
    color: colors.text,
    fontWeight: "800",
    fontSize: 15
  },
  memberMeta: {
    color: colors.muted,
    fontSize: 12,
    marginTop: 2
  },
  emptyCopy: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20
  }
});
