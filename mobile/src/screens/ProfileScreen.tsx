import React from "react";
import { ScrollView, StyleSheet, Text } from "react-native";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { StatusPill } from "../components/StatusPill";
import { getApiBaseUrl } from "../config/env";
import { getPersonaFamily, roleTitle } from "../domain/personas";
import { useAuth } from "../state/AuthContext";
import { colors, spacing } from "../styles/theme";
import type { RealtimeStatus } from "../hooks/useRealtime";
import type { ScreenProps } from "./types";

export function ProfileScreen({ user, project, data }: ScreenProps & { realtimeStatus?: RealtimeStatus }) {
  const { logout } = useAuth();
  const persona = getPersonaFamily(user.role);

  return (
    <ScrollView contentContainerStyle={styles.content}>
      <Card style={styles.card}>
        <StatusPill label={persona} tone="info" />
        <Text style={styles.name}>{user.username}</Text>
        <Text style={styles.meta}>{roleTitle(user)}</Text>
        <Text style={styles.meta}>{user.email}</Text>
      </Card>

      <Card style={styles.card}>
        <Text style={styles.title}>Current workspace</Text>
        <Text style={styles.copy}>{project ? `${project.name} (${project.key})` : "No project selected"}</Text>
        <Text style={styles.copy}>API: {getApiBaseUrl()}</Text>
        <Text style={styles.copy}>Visible integrations: {data?.integrations.length ?? 0}</Text>
      </Card>

      <Button label="Log out" variant="danger" onPress={() => void logout()} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.lg,
    gap: spacing.lg,
    paddingBottom: 120
  },
  card: {
    gap: spacing.sm
  },
  name: {
    color: colors.text,
    fontSize: 25,
    fontWeight: "900"
  },
  title: {
    color: colors.text,
    fontSize: 18,
    fontWeight: "900"
  },
  meta: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21
  },
  copy: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21
  }
});
