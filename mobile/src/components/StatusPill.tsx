import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, radius, spacing } from "../styles/theme";

type Tone = "success" | "warning" | "danger" | "info" | "neutral";

const toneStyles: Record<Tone, { backgroundColor: string; color: string }> = {
  success: { backgroundColor: colors.softGreen, color: colors.success },
  warning: { backgroundColor: colors.softAmber, color: colors.warning },
  danger: { backgroundColor: colors.softRed, color: colors.danger },
  info: { backgroundColor: colors.softBlue, color: colors.primaryDark },
  neutral: { backgroundColor: "#EEF2F7", color: colors.muted }
};

export function StatusPill({ label, tone = "neutral" }: { label: string; tone?: Tone }) {
  const toneStyle = toneStyles[tone];
  return (
    <View style={[styles.pill, { backgroundColor: toneStyle.backgroundColor }]}>
      <Text style={[styles.label, { color: toneStyle.color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    alignSelf: "flex-start",
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs
  },
  label: {
    fontSize: 12,
    fontWeight: "800"
  }
});
