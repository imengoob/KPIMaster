import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import KpiCard from "@/components/KpiCard";
import { Gauge } from "lucide-react";

describe("KpiCard", () => {
  it("renders title and value", () => {
    render(<KpiCard title="Velocity" value={42} icon={Gauge} />);
    expect(screen.getByText("Velocity")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders string value", () => {
    render(<KpiCard title="Cycle Time" value="3.5d" icon={Gauge} />);
    expect(screen.getByText("3.5d")).toBeInTheDocument();
  });

  it("renders change text when provided", () => {
    render(<KpiCard title="Velocity" value={38} icon={Gauge} change="+12%" changeType="positive" />);
    expect(screen.getByText("+12%")).toBeInTheDocument();
  });

  it("does not render change when omitted", () => {
    render(<KpiCard title="Velocity" value={38} icon={Gauge} />);
    // No change text means no extra paragraph beyond the value
    expect(screen.queryByText(/[+-]\d+%/)).toBeNull();
  });

  it("renders description when provided", () => {
    render(<KpiCard title="KPI" value="X" icon={Gauge} description="Helpful context" />);
    expect(screen.getByText("Helpful context")).toBeInTheDocument();
  });

  it("renders the icon (svg)", () => {
    const { container } = render(<KpiCard title="KPI" value="X" icon={Gauge} />);
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("applies positive style class for positive changeType", () => {
    render(<KpiCard title="V" value={1} icon={Gauge} change="+5%" changeType="positive" />);
    const changeEl = screen.getByText("+5%");
    expect(changeEl.className).toContain("success");
  });

  it("applies negative style class for negative changeType", () => {
    render(<KpiCard title="V" value={1} icon={Gauge} change="-5%" changeType="negative" />);
    const changeEl = screen.getByText("-5%");
    expect(changeEl.className).toContain("destructive");
  });
});
