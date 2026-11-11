import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface Props {
  title?: string;
  message?: string;
  error?: string;
  onRetry?: () => void;
  className?: string;
}

export default function ErrorState({
  title,
  message,
  error,
  onRetry,
  className,
}: Props) {
  const resolvedMessage = error ?? message ?? "Failed to load data. Check the backend connection.";

  return (
    <div
      data-testid="error-state"
      className={cn(
        "flex flex-col items-center justify-center gap-3 py-16 text-muted-foreground",
        className,
      )}
    >
      <AlertTriangle className="h-8 w-8 text-destructive" />
      {title && <h3 className="text-base font-semibold text-foreground">{title}</h3>}
      <p className="text-sm text-center max-w-sm">{resolvedMessage}</p>
      {onRetry && (
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
