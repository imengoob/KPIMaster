import React, { useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { getApiBaseUrl } from "../config/env";
import { useAuth } from "../state/AuthContext";
import { colors, radius, spacing } from "../styles/theme";
import { LinearGradient } from "expo-linear-gradient";

const demoAccounts = [
  { label: "Client", username: "horizon_admin", password: "ChangeMe123!" },
  { label: "Vendor", username: "hexadev_admin", password: "ChangeMe123!" },
  { label: "Developer", username: "alice_account", password: "ChangeMe123!" },
  { label: "PM", username: "retail_pm", password: "ChangeMe123!" },
  { label: "Executive", username: "horizon_exec", password: "ChangeMe123!" },
  { label: "Admin", username: "e2e", password: "E2ePassword1!" }
];

export function LoginScreen() {
  const { login, error, clearError } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const submit = async (name = username, pass = password) => {
    if (!name.trim() || !pass) return;
    setIsSubmitting(true);
    clearError();
    try {
      await login(name.trim(), pass);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.root}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <LinearGradient colors={["#0F172A", "#155E75", "#7C3AED"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.hero}>
          <View style={styles.logoMark}>
            <Text style={styles.logoText}>K</Text>
          </View>
          <Text style={styles.brand}>KPIMaster</Text>
          <Text style={styles.headline}>Sprint intelligence in your pocket</Text>
          <Text style={styles.copy}>
            Role-aware mobile access for clients, vendors, developers, delivery leads, executives, and admins.
          </Text>
        </LinearGradient>

        <Card style={styles.form}>
          <Text style={styles.formTitle}>Sign in</Text>
          <Text style={styles.apiText}>API: {getApiBaseUrl()}</Text>
          <TextInput
            autoCapitalize="none"
            autoCorrect={false}
            placeholder="Username"
            placeholderTextColor={colors.muted}
            value={username}
            onChangeText={setUsername}
            style={styles.input}
            testID="username-input"
          />
          <TextInput
            placeholder="Password"
            placeholderTextColor={colors.muted}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            style={styles.input}
            testID="password-input"
          />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <Button label="Open dashboard" onPress={() => submit()} loading={isSubmitting} disabled={!username || !password} />
        </Card>

        <View style={styles.demoBlock}>
          <Text style={styles.demoTitle}>Demo shortcuts</Text>
          <View style={styles.demoGrid}>
            {demoAccounts.map((account) => (
              <Pressable
                key={account.username}
                accessibilityRole="button"
                style={styles.demoButton}
                onPress={() => {
                  setUsername(account.username);
                  setPassword(account.password);
                  submit(account.username, account.password);
                }}
              >
                {isSubmitting ? <ActivityIndicator size="small" color={colors.primary} /> : null}
                <Text style={styles.demoLabel}>{account.label}</Text>
                <Text style={styles.demoUser}>{account.username}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.canvas
  },
  content: {
    flexGrow: 1,
    padding: spacing.xl,
    justifyContent: "center",
    gap: spacing.xl
  },
  hero: {
    gap: spacing.sm,
    borderRadius: 28,
    padding: spacing.xl,
    overflow: "hidden"
  },
  logoMark: {
    width: 54,
    height: 54,
    borderRadius: 18,
    backgroundColor: "rgba(255,255,255,0.16)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.24)",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm
  },
  logoText: {
    color: "#FFFFFF",
    fontWeight: "900",
    fontSize: 25
  },
  brand: {
    color: "#A5F3FC",
    fontWeight: "900",
    fontSize: 18,
    letterSpacing: 0
  },
  headline: {
    color: "#FFFFFF",
    fontWeight: "900",
    fontSize: 34,
    lineHeight: 39,
    letterSpacing: 0
  },
  copy: {
    color: "#DBEAFE",
    fontSize: 16,
    lineHeight: 24
  },
  form: {
    gap: spacing.md
  },
  formTitle: {
    color: colors.text,
    fontWeight: "900",
    fontSize: 22
  },
  apiText: {
    color: colors.muted,
    fontSize: 12
  },
  input: {
    minHeight: 52,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: "#FFFFFF",
    color: colors.text,
    paddingHorizontal: spacing.lg,
    fontSize: 16
  },
  error: {
    color: colors.danger,
    fontSize: 13,
    lineHeight: 19
  },
  demoBlock: {
    gap: spacing.md
  },
  demoTitle: {
    color: colors.text,
    fontWeight: "800",
    fontSize: 15
  },
  demoGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm
  },
  demoButton: {
    width: "48%",
    minHeight: 72,
    borderRadius: radius.md,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    justifyContent: "center"
  },
  demoLabel: {
    color: colors.text,
    fontWeight: "800",
    fontSize: 14
  },
  demoUser: {
    color: colors.muted,
    fontSize: 12,
    marginTop: 2
  }
});
