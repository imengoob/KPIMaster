import { formatPercent } from "./adapters";
import type { DashboardBundle } from "../domain/types";

export function answerMobileAssistant(question: string, data: DashboardBundle | null): string {
  if (!data) return "Load a project first, then I can summarize delivery health.";

  const q = question.toLowerCase();
  const blockers = data.blockers;
  const tickets = data.tickets;
  const kpis = data.kpis?.current_kpis;
  const sprint = data.sprint;

  if (q.includes("block") || q.includes("risk") || q.includes("stuck")) {
    if (!blockers.length) return "No active blockers are currently visible for this project.";
    const critical = blockers.filter((item) => item.escalation_level >= 3).length;
    return `${blockers.length} active blocker(s). ${critical} are management-level escalations. Highest risk ticket: ${blockers[0]?.ticket_title ?? `Ticket ${blockers[0]?.ticket_id}`}.`;
  }

  if (q.includes("quality")) {
    const lowQuality = tickets.filter((ticket) => (ticket.quality_score ?? 0) < 60);
    return lowQuality.length
      ? `${lowQuality.length} ticket(s) need quality attention. Start with ${lowQuality[0]?.title}.`
      : "Ticket quality looks healthy: no visible tickets are below 60%.";
  }

  if (q.includes("velocity") || q.includes("kpi") || q.includes("sprint")) {
    return `${sprint?.name ?? "Current sprint"} is at ${formatPercent(kpis?.completion_rate)} completion with velocity ${kpis?.velocity?.toFixed(0) ?? sprint?.velocity ?? 0}.`;
  }

  if (q.includes("repo") || q.includes("mismatch")) {
    return data.repositoryMismatches.length
      ? `${data.repositoryMismatches.length} repository mismatch(es) need review.`
      : "No repository mismatches are currently visible.";
  }

  return `I see ${tickets.length} ticket(s), ${blockers.length} blocker(s), and ${data.repositoryMismatches.length} repository mismatch(es) for the selected project.`;
}
