import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, spacing } from "../styles/theme";
import { Card } from "./Card";
import { IconBadge, IconName } from "./IconBadge";

interface MetricCardProps {
  label: string;
  value: string | number;
  helper?: string;
  tone?: "default" | "success" | "warning" | "danger" | "accent";
  icon?: IconName;
}

const toneColors = {
  default: colors.primary,
  success: colors.success,
  warning: colors.warning,
  danger: colors.danger,
  accent: colors.accent
};

export function MetricCard({ label, value, helper, tone = "default", icon }: MetricCardProps) {
  const iconTone = tone === "default" ? "primary" : tone;
  return (
    <Card style={styles.card}>
      <View style={styles.topRow}>
        {icon ? <IconBadge name={icon} tone={iconTone} size={16} /> : <View style={[styles.indicator, { backgroundColor: toneColors[tone] }]} />}
      </View>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
      {helper ? <Text style={styles.helper}>{helper}</Text> : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    minWidth: 146,
    gap: spacing.xs
  },
  topRow: {
    minHeight: 42
  },
  indicator: {
    width: 36,
    height: 4,
    borderRadius: 999,
    marginBottom: spacing.xs
  },
  label: {
    color: colors.muted,
    fontSize: 12,
    fontWeight: "700"
  },
  value: {
    color: colors.text,
    fontSize: 26,
    fontWeight: "900"
  },
  helper: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 17
  }
});
