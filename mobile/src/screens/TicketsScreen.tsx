import React, { useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState, ErrorState, LoadingState } from "../components/StateViews";
import { StatusPill } from "../components/StatusPill";
import type { Ticket, TicketQualityReport } from "../domain/types";
import { kpiApi } from "../services/api";
import { ticketStatusLabel } from "../services/adapters";
import { colors, spacing } from "../styles/theme";
import type { ScreenProps } from "./types";

export function TicketsScreen({ project, data, isLoading, error, isRefreshing, onRefresh }: ScreenProps) {
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [quality, setQuality] = useState<TicketQualityReport | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityError, setQualityError] = useState<string | null>(null);

  if (isLoading) return <LoadingState title="Loading tickets" />;
  if (error) return <ErrorState message={error} onRetry={onRefresh} />;
  if (!project) return <EmptyState title="No project" message="Select a project to inspect ticket health." />;

  const tickets = data?.tickets ?? [];
  const selectedTicket = selected ?? tickets[0] ?? null;

  const loadQuality = async (ticket: Ticket) => {
    setSelected(ticket);
    setQuality(null);
    setQualityError(null);
    setQualityLoading(true);
    try {
      setQuality(await kpiApi.tickets.quality(ticket.id));
    } catch (err) {
      setQualityError(err instanceof Error ? err.message : "Quality analysis is unavailable for this ticket.");
    } finally {
      setQualityLoading(false);
    }
  };

  return (
    <ScrollView
      refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      contentContainerStyle={styles.content}
    >
      {tickets.length === 0 ? (
        <EmptyState title="No tickets visible" message="This project has no tickets for your current access scope or selected integration data." />
      ) : null}

      {selectedTicket ? (
        <Card style={styles.detail}>
          <View style={styles.detailTop}>
            <Text style={styles.ticketId}>T-{selectedTicket.id}</Text>
            <StatusPill label={ticketStatusLabel(selectedTicket.status)} tone={selectedTicket.status === "blocked" ? "danger" : selectedTicket.status === "done" ? "success" : "info"} />
          </View>
          <Text style={styles.detailTitle}>{selectedTicket.title}</Text>
          <Text style={styles.detailCopy}>{selectedTicket.description || "No description has been provided."}</Text>
          <View style={styles.metaRow}>
            <Text style={styles.meta}>Priority: {selectedTicket.priority}</Text>
            <Text style={styles.meta}>Points: {selectedTicket.story_points ?? 0}</Text>
            <Text style={styles.meta}>Quality: {selectedTicket.quality_score ?? 0}%</Text>
          </View>
          <Button label="Analyze quality" onPress={() => loadQuality(selectedTicket)} variant="secondary" loading={qualityLoading} />
          {qualityLoading ? <ActivityIndicator color={colors.primary} /> : null}
          {qualityError ? <Text style={styles.errorText}>{qualityError}</Text> : null}
          {quality ? (
            <View style={styles.qualityBox}>
              <Text style={styles.qualityTitle}>Quality score: {quality.quality_score}%</Text>
              <Text style={styles.detailCopy}>
                {quality.recommendations.length ? quality.recommendations.join(" ") : "No recommendations were returned."}
              </Text>
            </View>
          ) : null}
        </Card>
      ) : null}

      {tickets.map((ticket) => (
        <Pressable key={ticket.id} onPress={() => setSelected(ticket)} accessibilityRole="button">
          <Card style={[styles.ticketRow, selectedTicket?.id === ticket.id && styles.activeTicket]}>
            <View style={styles.ticketMain}>
              <Text style={styles.ticketTitle} numberOfLines={2}>{ticket.title}</Text>
              <Text style={styles.ticketMeta}>T-{ticket.id} · {ticket.ticket_type} · {ticket.priority}</Text>
            </View>
            <StatusPill label={`${ticket.quality_score ?? 0}%`} tone={(ticket.quality_score ?? 0) < 60 ? "warning" : "success"} />
          </Card>
        </Pressable>
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
  detail: {
    gap: spacing.md
  },
  detailTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.md
  },
  ticketId: {
    color: colors.primary,
    fontWeight: "900",
    fontSize: 13
  },
  detailTitle: {
    color: colors.text,
    fontSize: 22,
    fontWeight: "900",
    lineHeight: 27
  },
  detailCopy: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21
  },
  metaRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm
  },
  meta: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700"
  },
  qualityBox: {
    backgroundColor: colors.softBlue,
    borderRadius: 12,
    padding: spacing.md,
    gap: spacing.xs
  },
  qualityTitle: {
    color: colors.primaryDark,
    fontSize: 14,
    fontWeight: "900"
  },
  errorText: {
    color: colors.danger,
    fontSize: 13,
    lineHeight: 19
  },
  ticketRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: spacing.md,
    paddingVertical: spacing.md
  },
  activeTicket: {
    borderColor: colors.primary,
    backgroundColor: "#F0FDFA"
  },
  ticketMain: {
    flex: 1
  },
  ticketTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "800",
    lineHeight: 20
  },
  ticketMeta: {
    color: colors.muted,
    fontSize: 12,
    marginTop: 4
  }
});
