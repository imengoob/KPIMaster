import "@testing-library/jest-dom";

// ── Web Crypto polyfill for Node 16 (required by Vite 5) ─────────────────────
import { webcrypto } from "node:crypto";
if (!globalThis.crypto) {
  // @ts-expect-error Node 16 webcrypto type mismatch
  globalThis.crypto = webcrypto;
}

// ── matchMedia stub (required for Radix UI + recharts) ────────────────────────
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// ── ResizeObserver stub (required for recharts) ───────────────────────────────
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// ── IntersectionObserver stub ────────────────────────────────────────────────
global.IntersectionObserver = class IntersectionObserver {
  root = null;
  rootMargin = "";
  thresholds = [];
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
} as unknown as typeof IntersectionObserver;
