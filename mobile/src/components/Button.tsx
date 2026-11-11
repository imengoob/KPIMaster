import React from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, ViewStyle } from "react-native";
import { colors, radius, spacing } from "../styles/theme";

interface ButtonProps {
  label: string;
  onPress: () => void;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
  testID?: string;
}

export function Button({ label, onPress, variant = "primary", disabled, loading, style, testID }: ButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled || loading}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [
        styles.base,
        styles[variant],
        (pressed || disabled) && styles.pressed,
        style
      ]}
    >
      {loading ? <ActivityIndicator color={variant === "primary" ? "#FFFFFF" : colors.primary} /> : null}
      <Text style={[styles.label, variant === "primary" || variant === "danger" ? styles.labelOnDark : styles.labelDefault]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 48,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: spacing.sm
  },
  primary: {
    backgroundColor: colors.primary
  },
  secondary: {
    backgroundColor: colors.softBlue,
    borderWidth: 1,
    borderColor: "#BAE6FD"
  },
  danger: {
    backgroundColor: colors.danger
  },
  ghost: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: colors.border
  },
  pressed: {
    opacity: 0.75
  },
  label: {
    fontSize: 15,
    fontWeight: "700"
  },
  labelOnDark: {
    color: "#FFFFFF"
  },
  labelDefault: {
    color: colors.ink
  }
});
