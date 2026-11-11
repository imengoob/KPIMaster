import React from "react";
import { DimensionValue, StyleSheet, View } from "react-native";
import { colors, radius } from "../styles/theme";

export function ProgressBar({ value, tone = colors.primary }: { value: number; tone?: string }) {
  const width = `${Math.max(0, Math.min(100, value * 100))}%` as DimensionValue;
  return (
    <View style={styles.track}>
      <View style={[styles.fill, { width, backgroundColor: tone }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  track: {
    height: 10,
    borderRadius: radius.pill,
    backgroundColor: "#E2E8F0",
    overflow: "hidden"
  },
  fill: {
    height: "100%",
    borderRadius: radius.pill
  }
});
