jest.mock("expo-secure-store", () => {
  const memory = new Map<string, string>();
  return {
    getItemAsync: jest.fn((key: string) => Promise.resolve(memory.get(key) ?? null)),
    setItemAsync: jest.fn((key: string, value: string) => {
      memory.set(key, value);
      return Promise.resolve();
    }),
    deleteItemAsync: jest.fn((key: string) => {
      memory.delete(key);
      return Promise.resolve();
    })
  };
});
