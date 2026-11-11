import React from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { colors, spacing } from "../styles/theme";
import { Button } from "./Button";
import { Card } from "./Card";

export function LoadingState({ title = "Loading KPIMaster" }: { title?: string }) {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.primary} size="large" />
      <Text style={styles.title}>{title}</Text>
    </View>
  );
}

export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <Card style={styles.box}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
    </Card>
  );
}

export function ErrorState({ title = "Something went wrong", message, onRetry }: { title?: string; message: string; onRetry?: () => void }) {
  return (
    <Card style={styles.box}>
      <Text style={[styles.title, styles.error]}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
      {onRetry ? <Button label="Try again" onPress={onRetry} variant="secondary" /> : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    minHeight: 260,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.md
  },
  box: {
    gap: spacing.md
  },
  title: {
    color: colors.text,
    fontWeight: "900",
    fontSize: 18
  },
  message: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21
  },
  error: {
    color: colors.danger
  }
});
