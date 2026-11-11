import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const memory = new Map<string, string>();

function canUseWebStorage(): boolean {
  return Platform.OS === "web" && typeof globalThis.localStorage !== "undefined";
}

export const TOKEN_STORAGE_KEY = "kpimaster.mobile.authToken";
export const PROJECT_STORAGE_KEY = "kpimaster.mobile.currentProjectId";

export const appStorage = {
  async getItem(key: string): Promise<string | null> {
    if (canUseWebStorage()) {
      return globalThis.localStorage.getItem(key);
    }
    try {
      return await SecureStore.getItemAsync(key);
    } catch {
      return memory.get(key) ?? null;
    }
  },

  async setItem(key: string, value: string): Promise<void> {
    if (canUseWebStorage()) {
      globalThis.localStorage.setItem(key, value);
      return;
    }
    try {
      await SecureStore.setItemAsync(key, value);
    } catch {
      memory.set(key, value);
    }
  },

  async removeItem(key: string): Promise<void> {
    if (canUseWebStorage()) {
      globalThis.localStorage.removeItem(key);
      return;
    }
    try {
      await SecureStore.deleteItemAsync(key);
    } catch {
      memory.delete(key);
    }
  }
};
