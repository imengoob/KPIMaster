import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import ErrorState from "@/components/ErrorState";

describe("ErrorState", () => {
  it("renders with default message", () => {
    render(<ErrorState />);
    expect(screen.getByTestId("error-state")).toBeInTheDocument();
    expect(screen.getByText(/Failed to load data/)).toBeInTheDocument();
  });

  it("renders with custom message", () => {
    render(<ErrorState message="Something went wrong." />);
    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
  });

  it("applies custom className", () => {
    render(<ErrorState className="my-error" />);
    expect(screen.getByTestId("error-state").className).toContain("my-error");
  });

  it("renders the AlertTriangle icon (svg present)", () => {
    render(<ErrorState />);
    const el = screen.getByTestId("error-state");
    expect(el.querySelector("svg")).not.toBeNull();
  });
});
