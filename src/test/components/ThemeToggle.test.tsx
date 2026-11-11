import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const themeMock = vi.hoisted(() => ({
  theme: "light",
  setTheme: vi.fn(),
}));

vi.mock("@/components/ThemeProvider", () => ({
  useTheme: () => ({
    theme: themeMock.theme,
    setTheme: themeMock.setTheme,
  }),
}));

import { ThemeToggle } from "@/components/ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    themeMock.theme = "light";
    themeMock.setTheme.mockClear();
  });

  it("toggles from light to dark", () => {
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: /toggle theme/i }));

    expect(themeMock.setTheme).toHaveBeenCalledWith("dark");
  });

  it("toggles from dark to light", () => {
    themeMock.theme = "dark";
    render(<ThemeToggle />);

    fireEvent.click(screen.getByRole("button", { name: /toggle theme/i }));

    expect(themeMock.setTheme).toHaveBeenCalledWith("light");
  });
});
