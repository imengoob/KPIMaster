import DashboardLayout from "@/components/DashboardLayout";
import { Button } from "@/components/ui/button";

interface Props {
  title?: string;
  message?: string;
}

export default function EmptyProjectState({
  title = "Connect a Trello board to get started",
  message = "No live projects are available yet. Open Settings, import one or more Trello boards, and the dashboard will switch from placeholder data to your real board activity.",
}: Props) {
  return (
    <DashboardLayout>
      <div className="flex min-h-[70vh] items-center justify-center">
        <div className="max-w-xl rounded-2xl border border-border bg-card/80 p-8 text-center shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-primary">
            Live Trello Setup
          </p>
          <h1 className="mt-3 text-3xl font-bold text-foreground">{title}</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">{message}</p>
          <div className="mt-6 flex justify-center">
            <Button asChild>
              <a href="/settings">Open Settings</a>
            </Button>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
