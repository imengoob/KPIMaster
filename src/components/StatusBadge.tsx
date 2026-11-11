import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: "completed" | "in-progress" | "not-started" | "blocked" | "overdue";
  size?: "sm" | "md";
}

const statusConfig = {
  completed: { label: "Completed", className: "bg-success/15 text-success border-success/20" },
  "in-progress": { label: "In Progress", className: "bg-primary/15 text-primary border-primary/20" },
  "not-started": { label: "Not Started", className: "bg-muted text-muted-foreground border-border" },
  blocked: { label: "Blocked", className: "bg-destructive/15 text-destructive border-destructive/20" },
  overdue: { label: "Overdue", className: "bg-warning/15 text-warning border-warning/20" },
};

const StatusBadge = ({ status, size = "sm" }: StatusBadgeProps) => {
  const config = statusConfig[status];
  return (
    <span className={cn(
      "inline-flex items-center rounded-full border font-medium",
      size === "sm" ? "px-2 py-0.5 text-xs" : "px-3 py-1 text-sm",
      config.className
    )}>
      <span className={cn(
        "mr-1.5 inline-block rounded-full",
        size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2",
        status === "completed" && "bg-success",
        status === "in-progress" && "bg-primary",
        status === "not-started" && "bg-muted-foreground",
        status === "blocked" && "bg-destructive",
        status === "overdue" && "bg-warning",
      )} />
      {config.label}
    </span>
  );
};

export default StatusBadge;
