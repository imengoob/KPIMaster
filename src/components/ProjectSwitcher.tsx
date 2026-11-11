import { useState } from "react";
import { ChevronDown, Check, Loader2 } from "lucide-react";
import { useProject } from "@/contexts/ProjectContext";
import { cn } from "@/lib/utils";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

const ProjectSwitcher = () => {
  const { currentProject, setCurrentProject, allProjects, isLoadingProjects } = useProject();
  const [open, setOpen] = useState(false);
  const hasProjects = currentProject !== null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          data-testid="project-switcher-trigger"
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg bg-sidebar-accent/50 hover:bg-sidebar-accent transition-colors text-left"
        >
          <div
            className="flex h-8 w-8 items-center justify-center rounded-md text-xs font-bold text-primary-foreground shrink-0"
            style={{ backgroundColor: currentProject?.color ?? "hsl(220, 18%, 35%)" }}
          >
            {currentProject?.key.slice(0, 2) ?? "--"}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-sidebar-accent-foreground truncate">
              {currentProject?.name ?? "No live project connected"}
            </p>
            <p className="text-[10px] text-sidebar-foreground truncate">
              {currentProject?.key ?? "Import a Trello board in Integrations"}
            </p>
          </div>
          {isLoadingProjects
            ? <Loader2 className="h-4 w-4 text-sidebar-foreground shrink-0 animate-spin" />
            : <ChevronDown className="h-4 w-4 text-sidebar-foreground shrink-0" />
          }
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-1">
        {!hasProjects && (
          <div className="px-3 py-4 text-sm text-muted-foreground">
            No imported Trello projects yet.
          </div>
        )}
        {allProjects.map(project => (
          <button
            key={project.id}
            data-testid={`project-option-${project.key.toLowerCase()}`}
            onClick={() => { setCurrentProject(project); setOpen(false); }}
            className={cn(
              "flex items-center gap-3 w-full rounded-md px-2 py-2 text-left hover:bg-accent transition-colors",
              project.id === currentProject?.id && "bg-accent"
            )}
          >
            <div
              className="flex h-7 w-7 items-center justify-center rounded-md text-[10px] font-bold text-primary-foreground shrink-0"
              style={{ backgroundColor: project.color }}
            >
              {project.key.slice(0, 2)}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{project.name}</p>
              <p className="text-[10px] text-muted-foreground truncate">{project.key}</p>
            </div>
            {project.id === currentProject?.id && (
              <Check className="h-4 w-4 text-primary shrink-0" />
            )}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
};

export default ProjectSwitcher;
