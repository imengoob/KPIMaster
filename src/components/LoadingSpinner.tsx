import { cn } from "@/lib/utils";

interface Props {
  className?: string;
  label?: string;
  title?: string;
}

export default function LoadingSpinner({ className, label, title }: Props) {
  const resolvedLabel = label ?? title ?? "Loading…";
  return (
    <div
      data-testid="loading-spinner"
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground",
        className,
      )}
    >
      <span className="h-8 w-8 rounded-full border-2 border-primary border-t-transparent animate-spin" />
      <p className="text-sm">{resolvedLabel}</p>
    </div>
  );
}
