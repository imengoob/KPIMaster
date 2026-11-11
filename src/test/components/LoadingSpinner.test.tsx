import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import LoadingSpinner from "@/components/LoadingSpinner";

describe("LoadingSpinner", () => {
  it("renders with default label", () => {
    render(<LoadingSpinner />);
    expect(screen.getByTestId("loading-spinner")).toBeInTheDocument();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders with custom label", () => {
    render(<LoadingSpinner label="Fetching data…" />);
    expect(screen.getByText("Fetching data…")).toBeInTheDocument();
  });

  it("applies custom className", () => {
    render(<LoadingSpinner className="custom-class" />);
    const el = screen.getByTestId("loading-spinner");
    expect(el.className).toContain("custom-class");
  });

  it("contains the animated spinner element", () => {
    render(<LoadingSpinner />);
    const spinner = screen.getByTestId("loading-spinner");
    // The inner span has animate-spin
    const spinEl = spinner.querySelector(".animate-spin");
    expect(spinEl).not.toBeNull();
  });
});
