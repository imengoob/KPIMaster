// Polyfill globalThis.crypto for Node 16 (needed by Vite 5)
if (!globalThis.crypto) {
  const { webcrypto } = require("node:crypto");
  globalThis.crypto = webcrypto;
}
