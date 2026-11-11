import React from "react";
import { StyleSheet, View } from "react-native";
import { Feather } from "@expo/vector-icons";
import { colors, radius, spacing } from "../styles/theme";

export type IconName = React.ComponentProps<typeof Feather>["name"];

export function IconBadge({ name, tone = "primary", size = 18 }: { name: IconName; tone?: "primary" | "success" | "warning" | "danger" | "accent"; size?: number }) {
  const palette = {
    primary: { backgroundColor: colors.softBlue, color: colors.primaryDark },
    success: { backgroundColor: colors.softGreen, color: colors.success },
    warning: { backgroundColor: colors.softAmber, color: colors.warning },
    danger: { backgroundColor: colors.softRed, color: colors.danger },
    accent: { backgroundColor: colors.softViolet, color: colors.accent }
  }[tone];

  return (
    <View style={[styles.wrap, { backgroundColor: palette.backgroundColor }]}>
      <Feather name={name} size={size} color={palette.color} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    width: 38,
    height: 38,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs
  }
});
