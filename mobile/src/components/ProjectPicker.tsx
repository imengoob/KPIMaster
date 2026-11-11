import React from "react";
import { Pressable, ScrollView, StyleSheet, Text } from "react-native";
import type { Project } from "../domain/types";
import { colors, radius, spacing } from "../styles/theme";

interface ProjectPickerProps {
  projects: Project[];
  currentProject: Project | null;
  onSelect: (project: Project) => void;
}

export function ProjectPicker({ projects, currentProject, onSelect }: ProjectPickerProps) {
  if (!projects.length) return null;

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
      {projects.map((project) => {
        const active = project.id === currentProject?.id;
        return (
          <Pressable
            accessibilityRole="button"
            key={project.id}
            onPress={() => onSelect(project)}
            style={[styles.chip, active && styles.activeChip]}
          >
            <Text style={[styles.key, active && styles.activeText]}>{project.key}</Text>
            <Text style={[styles.name, active && styles.activeText]} numberOfLines={1}>
              {project.name}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md
  },
  chip: {
    width: 154,
    minHeight: 56,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.panel,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    justifyContent: "center"
  },
  activeChip: {
    backgroundColor: colors.ink,
    borderColor: colors.ink
  },
  key: {
    color: colors.primary,
    fontWeight: "900",
    fontSize: 12
  },
  name: {
    color: colors.text,
    fontWeight: "700",
    fontSize: 13
  },
  activeText: {
    color: "#FFFFFF"
  }
});
