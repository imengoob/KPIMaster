import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import StatusBadge from "@/components/StatusBadge";

const statuses = [
  "completed",
  "in-progress",
  "not-started",
  "blocked",
  "overdue",
] as const;

describe("StatusBadge", () => {
  it.each(statuses)("renders label for status '%s'", (status) => {
    render(<StatusBadge status={status} />);
    // Each status maps to a human-readable label
    const labels: Record<string, string> = {
      "completed": "Completed",
      "in-progress": "In Progress",
      "not-started": "Not Started",
      "blocked": "Blocked",
      "overdue": "Overdue",
    };
    expect(screen.getByText(labels[status])).toBeInTheDocument();
  });

  it("defaults to sm size", () => {
    render(<StatusBadge status="completed" />);
    const el = screen.getByText("Completed").closest("span");
    expect(el?.className).toContain("px-2");
  });

  it("applies md size styles", () => {
    render(<StatusBadge status="completed" size="md" />);
    const el = screen.getByText("Completed").closest("span");
    expect(el?.className).toContain("px-3");
  });

  it("renders indicator dot inside the badge", () => {
    const { container } = render(<StatusBadge status="blocked" />);
    // The dot is a nested span with rounded-full
    const dot = container.querySelector(".rounded-full");
    expect(dot).not.toBeNull();
  });
});
