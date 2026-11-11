import React, { useState } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { answerMobileAssistant } from "../services/assistant";
import { colors, radius, spacing } from "../styles/theme";
import type { ScreenProps } from "./types";

const suggestions = [
  "Which tickets are blocked?",
  "Summarize sprint KPIs",
  "Any repository mismatches?",
  "How is ticket quality?"
];

interface Message {
  role: "user" | "assistant";
  text: string;
}

export function AssistantScreen({ data }: ScreenProps) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", text: "Ask about blockers, ticket quality, sprint KPIs, or repository mismatch risk." }
  ]);

  const send = (text = input) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const answer = answerMobileAssistant(trimmed, data);
    setMessages((prev) => [...prev, { role: "user", text: trimmed }, { role: "assistant", text: answer }]);
    setInput("");
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.root}>
      <ScrollView contentContainerStyle={styles.content}>
        <Card style={styles.hero}>
          <Text style={styles.title}>Mobile Assistant</Text>
          <Text style={styles.copy}>Private, rule-based answers from the data already loaded on your device.</Text>
        </Card>

        <View style={styles.suggestions}>
          {suggestions.map((question) => (
            <Button key={question} label={question} variant="ghost" onPress={() => send(question)} style={styles.suggestionButton} />
          ))}
        </View>

        {messages.map((message, index) => (
          <View key={`${message.role}-${index}`} style={[styles.bubble, message.role === "user" ? styles.userBubble : styles.assistantBubble]}>
            <Text style={[styles.bubbleText, message.role === "user" && styles.userText]}>{message.text}</Text>
          </View>
        ))}
      </ScrollView>
      <View style={styles.inputBar}>
        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="Ask about the sprint"
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
        <Button label="Send" onPress={() => send()} style={styles.sendButton} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1
  },
  content: {
    padding: spacing.lg,
    gap: spacing.md,
    paddingBottom: 120
  },
  hero: {
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
  suggestions: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm
  },
  suggestionButton: {
    minHeight: 42
  },
  bubble: {
    borderRadius: radius.lg,
    padding: spacing.md,
    maxWidth: "88%"
  },
  assistantBubble: {
    alignSelf: "flex-start",
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.border
  },
  userBubble: {
    alignSelf: "flex-end",
    backgroundColor: colors.primary
  },
  bubbleText: {
    color: colors.text,
    fontSize: 14,
    lineHeight: 21
  },
  userText: {
    color: "#FFFFFF"
  },
  inputBar: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: "row",
    gap: spacing.sm,
    padding: spacing.lg,
    backgroundColor: "#FFFFFF",
    borderTopWidth: 1,
    borderTopColor: colors.border
  },
  input: {
    flex: 1,
    minHeight: 48,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    color: colors.text,
    fontSize: 15
  },
  sendButton: {
    minWidth: 86
  }
});
