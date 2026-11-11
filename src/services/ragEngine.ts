/**
 * RAG (Retrieval-Augmented Generation) engine.
 *
 * Flow:
 *   user query → intent detection → vector search (top-K) → context assembly
 *   → rule-based response generation from real dashboard data.
 *
 * No external LLM API key required — all responses are generated from the
 * actual records stored in the vector DB at runtime.
 */

import { vectorDb, type SearchResult } from "./vectorDb";
import type { BackendActionItem, UITicket, UIBlocker, UIDeveloper, UISprint, UIKpi } from "./api/types";

// ── Intent patterns ───────────────────────────────────────────────────────────

type Intent =
  | "blockers_list"
  | "blockers_stalled"
  | "ticket_status"
  | "ticket_quality_poor"
  | "ticket_quality_high"
  | "ticket_search"
  | "developer_performance"
  | "developer_list"
  | "sprint_summary"
  | "sprint_velocity"
  | "sprint_progress"
  | "kpi_summary"
  | "action_priority"
  | "action_list"
  | "generic_search";

interface IntentRule {
  intent: Intent;
  patterns: RegExp[];
}

const INTENT_RULES: IntentRule[] = [
  {
    intent: "blockers_list",
    patterns: [/\bblock(er|ed|s)?\b/i, /\bescalat/i, /\bstuck\b/i],
  },
  {
    intent: "blockers_stalled",
    patterns: [/\bstall(ed|ing)?\b/i, /\bover\s*\d+\s*h(our|r)/i, /\binactiv/i, /\bno activity/i],
  },
  {
    intent: "ticket_quality_poor",
    patterns: [/\bpoor\b/i, /\blow.+quality/i, /\bquality.+poor/i, /\bneed.+attention/i, /\bneed.+review/i, /\bneed.+improve/i],
  },
  {
    intent: "ticket_quality_high",
    patterns: [/\bhigh.+quality/i, /\bgood.+quality/i, /\bbest.+ticket/i],
  },
  {
    intent: "ticket_status",
    patterns: [/\bticket(s)?\b.*\b(status|state)\b/i, /\bwhich.+ticket/i, /\blist.+ticket/i, /\bshow.+ticket/i],
  },
  {
    intent: "developer_performance",
    patterns: [/\b(david|alice|bob|carol|eva|frank|grace|hector|iris|james|mike|sarah|anna|john)\b/i, /\bperformance\b.*\b(dev|eng|member)\b/i, /\bdev.+performance\b/i],
  },
  {
    intent: "developer_list",
    patterns: [/\bteam\b/i, /\bdevelope(r|rs)\b/i, /\bmember(s)?\b/i, /\bwho.+(behind|risk|track)\b/i],
  },
  {
    intent: "sprint_velocity",
    patterns: [/\bvelocity\b/i, /\bspeed\b/i, /\bthroughput\b/i],
  },
  {
    intent: "sprint_progress",
    patterns: [/\bprogress\b/i, /\bcompletion\b/i, /\bcomplete(d)?\b/i, /\bhow many.+done\b/i],
  },
  {
    intent: "sprint_summary",
    patterns: [/\bsprint\b/i, /\bburn(down)?\b/i, /\bsprint.+summar/i, /\bsummar.+sprint/i],
  },
  {
    intent: "kpi_summary",
    patterns: [/\bkpi\b/i, /\bcycle.?time\b/i, /\blead.?time\b/i, /\bmetric(s)?\b/i, /\baccura(cy|te)\b/i],
  },
  {
    intent: "action_priority",
    patterns: [/\bwhat should i do first\b/i, /\bpriorit(y|ize)\b/i, /\bnext action\b/i, /\baction.+first\b/i],
  },
  {
    intent: "action_list",
    patterns: [/\baction(s)?\b/i, /\bapproval(s)?\b/i, /\boverdue\b/i],
  },
];

function detectIntent(query: string): Intent {
  for (const rule of INTENT_RULES) {
    if (rule.patterns.some(p => p.test(query))) return rule.intent;
  }
  return "generic_search";
}

// ── Context data types (passed in by the hook) ────────────────────────────────

export interface AssistantContext {
  tickets:    UITicket[];
  blockers:   UIBlocker[];
  developers: UIDeveloper[];
  sprint:     UISprint | null;
  kpis:       UIKpi | null;
  actions:    BackendActionItem[];
  projectName: string;
}

// ── Response generators ───────────────────────────────────────────────────────

function pluralise(n: number, singular: string, plural?: string): string {
  return n === 1 ? `${n} ${singular}` : `${n} ${plural ?? singular + "s"}`;
}

function formatHours(h: number): string {
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  const rem = h % 24;
  return rem > 0 ? `${d}d ${rem}h` : `${d}d`;
}

function generateBlockersList(ctx: AssistantContext): string {
  const { blockers } = ctx;
  if (blockers.length === 0)
    return "✅ Great news — there are **no active blockers** right now. The team is moving smoothly.";

  const byLevel = (lvl: number) => blockers.filter(b => b.escalationLevel === lvl);
  const l3 = byLevel(3), l2 = byLevel(2), l1 = byLevel(1);

  let out = `🚨 There are **${pluralise(blockers.length, "active blocker")}** across ${ctx.projectName}:\n\n`;

  if (l3.length) {
    out += `**Level 3 — Management Escalation (${l3.length}):**\n`;
    l3.forEach(b => { out += `• ${b.ticketId} — _${b.title}_ · stalled **${formatHours(b.stalledHours)}**\n`; });
    out += "\n";
  }
  if (l2.length) {
    out += `**Level 2 — Team Lead Alert (${l2.length}):**\n`;
    l2.forEach(b => { out += `• ${b.ticketId} — _${b.title}_ · stalled **${formatHours(b.stalledHours)}**\n`; });
    out += "\n";
  }
  if (l1.length) {
    out += `**Level 1 — Developer Prompt (${l1.length}):**\n`;
    l1.forEach(b => { out += `• ${b.ticketId} — _${b.title}_ · stalled **${formatHours(b.stalledHours)}**\n`; });
  }

  return out.trimEnd();
}

function generateStalledBlockers(ctx: AssistantContext, query: string): string {
  const hrMatch = query.match(/(\d+)\s*h(our|r)?/i);
  const threshold = hrMatch ? parseInt(hrMatch[1]) : 48;

  const stalled = ctx.blockers.filter(b => b.stalledHours >= threshold);
  if (stalled.length === 0)
    return `✅ No tickets have been stalled for more than **${threshold}h**.`;

  let out = `⏱ **${pluralise(stalled.length, "ticket")}** stalled over **${threshold}h**:\n\n`;
  stalled
    .sort((a, b) => b.stalledHours - a.stalledHours)
    .forEach(b => {
      out += `• ${b.ticketId} _${b.title}_ — **${formatHours(b.stalledHours)}** · Level ${b.escalationLevel} escalation\n`;
    });
  return out.trimEnd();
}

function generateTicketStatus(ctx: AssistantContext): string {
  const { tickets } = ctx;
  if (tickets.length === 0) return "No tickets found for this project.";

  const groups: Record<string, UITicket[]> = {};
  for (const t of tickets) {
    groups[t.status] = groups[t.status] ?? [];
    groups[t.status].push(t);
  }

  const order = ["completed","in-progress","blocked","overdue","not-started"];
  const labels: Record<string, string> = {
    "completed":   "✅ Completed",
    "in-progress": "🔄 In Progress",
    "blocked":     "🔴 Blocked",
    "overdue":     "⏰ Overdue",
    "not-started": "⬜ Not Started",
  };

  let out = `📋 **${pluralise(tickets.length, "ticket")}** in ${ctx.projectName}:\n\n`;
  for (const s of order) {
    const group = groups[s] ?? [];
    if (group.length) out += `${labels[s] ?? s}: **${group.length}**\n`;
  }
  return out.trimEnd();
}

function generatePoorQuality(ctx: AssistantContext): string {
  const poor = ctx.tickets.filter(t => t.qualityScore < 60).sort((a,b) => a.qualityScore - b.qualityScore);
  if (poor.length === 0) return "✅ No tickets have a poor quality score (< 60%).";

  let out = `⚠️ **${pluralise(poor.length, "ticket")}** with poor quality (< 60%):\n\n`;
  poor.forEach(t => {
    out += `• ${t.id} _${t.title}_ — **${t.qualityScore}%** · ${t.priority} priority · ${t.status}\n`;
  });
  return out.trimEnd();
}

function generateHighQuality(ctx: AssistantContext): string {
  const good = ctx.tickets.filter(t => t.qualityScore >= 80).sort((a,b) => b.qualityScore - a.qualityScore);
  if (good.length === 0)
    return "📊 No tickets currently score 80% or above on quality. Consider reviewing ticket descriptions and acceptance criteria.";

  let out = `⭐ **${pluralise(good.length, "ticket")}** with high quality (≥ 80%):\n\n`;
  good.forEach(t => {
    out += `• ${t.id} _${t.title}_ — **${t.qualityScore}%** · ${t.storyPoints}pts\n`;
  });
  return out.trimEnd();
}

function generateDeveloperPerformance(ctx: AssistantContext, query: string, results: SearchResult[]): string {
  // Try to find a specific developer by name in the query
  const nameMatch = query.match(/\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b/g);
  let found: UIDeveloper | undefined;

  if (nameMatch) {
    for (const nm of nameMatch) {
      found = ctx.developers.find(d => d.name.toLowerCase().includes(nm.toLowerCase()));
      if (found) break;
    }
  }

  // Also try from retrieved records
  if (!found) {
    const devResult = results.find(r => r.record.type === "developer");
    if (devResult) {
      const nm = (devResult.record.metadata as UIDeveloper).name;
      found = ctx.developers.find(d => d.name === nm);
    }
  }

  if (!found && ctx.developers.length > 0) {
    // Fall back to listing all
    return generateDeveloperList(ctx);
  }

  if (!found) return "No developer data available yet.";

  const pct = found.totalPoints > 0 ? Math.round((found.completedPoints / found.totalPoints) * 100) : 0;
  const statusEmoji = found.status === "on-track" ? "✅" : found.status === "at-risk" ? "⚠️" : "🔴";

  return `👤 **${found.name}** (${found.role})\n\n` +
    `${statusEmoji} Status: **${found.status.replace("-"," ").toUpperCase()}**\n` +
    `📊 Points: **${found.completedPoints}/${found.totalPoints}** (${pct}% complete)\n` +
    `🎫 Tickets: **${found.ticketsCompleted}/${found.ticketsTotal}** done\n` +
    `⏱ Avg Cycle Time: **${found.avgCycleTime > 0 ? found.avgCycleTime + "d" : "N/A"}**\n` +
    `🎯 Estimation Accuracy: **${found.estimationAccuracy}%**\n` +
    `🚧 Active Blockers: **${found.blockers}**`;
}

function generateDeveloperList(ctx: AssistantContext): string {
  const { developers } = ctx;
  if (developers.length === 0) return "No developer data available yet.";

  const onTrack = developers.filter(d => d.status === "on-track");
  const atRisk  = developers.filter(d => d.status === "at-risk");
  const behind  = developers.filter(d => d.status === "behind");

  let out = `👥 **Team overview — ${pluralise(developers.length, "developer")}:**\n\n`;

  if (onTrack.length) {
    out += `✅ **On Track (${onTrack.length}):** ${onTrack.map(d => d.name).join(", ")}\n`;
  }
  if (atRisk.length) {
    out += `⚠️ **At Risk (${atRisk.length}):** ${atRisk.map(d => d.name).join(", ")}\n`;
  }
  if (behind.length) {
    out += `🔴 **Behind (${behind.length}):** ${behind.map(d => d.name).join(", ")}\n`;
  }

  // Top performers
  const top = [...developers].sort((a,b) => {
    const pa = a.totalPoints > 0 ? a.completedPoints / a.totalPoints : 0;
    const pb = b.totalPoints > 0 ? b.completedPoints / b.totalPoints : 0;
    return pb - pa;
  })[0];

  if (top && top.totalPoints > 0) {
    const pct = Math.round((top.completedPoints / top.totalPoints) * 100);
    out += `\n🏆 Top performer: **${top.name}** at ${pct}% completion`;
  }

  return out.trimEnd();
}

function generateSprintSummary(ctx: AssistantContext): string {
  const { sprint, kpis } = ctx;
  if (!sprint) return "No active sprint data available.";

  const pct = sprint.totalTickets > 0
    ? Math.round((sprint.completedTickets / sprint.totalTickets) * 100) : 0;

  const urgency = sprint.daysRemaining <= 2 ? "🔴" : sprint.daysRemaining <= 5 ? "⚠️" : "✅";

  let out = `🏃 **Sprint: ${sprint.name}**\n\n` +
    `📅 ${sprint.startDate} → ${sprint.endDate}\n` +
    `${urgency} **${sprint.daysRemaining === 0 ? "Ends TODAY" : `${sprint.daysRemaining} days remaining`}**\n\n` +
    `📊 Progress: **${pct}%** (${sprint.completedTickets}/${sprint.totalTickets} tickets)\n` +
    `🔄 In Progress: **${sprint.inProgressTickets}**\n` +
    `⬜ Not Started: **${sprint.notStartedTickets}**\n` +
    `🚧 Blocked: **${sprint.blockedTickets}**\n`;

  if (kpis) {
    out += `\n📈 Velocity: **${kpis.velocity.value}** ${kpis.velocity.change}\n`;
    out += `⏱ Cycle Time: **${kpis.cycleTime.value}** ${kpis.cycleTime.change}\n`;
    out += `🎯 Completion Rate: **${kpis.completionRate.value}** ${kpis.completionRate.change}`;
  }

  return out.trimEnd();
}

function generateVelocity(ctx: AssistantContext): string {
  const { sprint, kpis } = ctx;
  if (!kpis && !sprint) return "No KPI data available yet.";

  let out = `📈 **Sprint Velocity & Performance:**\n\n`;
  if (kpis) {
    out += `⚡ Velocity: **${kpis.velocity.value}** pts/sprint ${kpis.velocity.change}\n`;
    out += `⏱ Avg Cycle Time: **${kpis.cycleTime.value}** ${kpis.cycleTime.change}\n`;
    out += `📬 Lead Time: **${kpis.leadTime.value}** ${kpis.leadTime.change}\n`;
    out += `🎯 Estimation Accuracy: **${kpis.estimationAccuracy.value}** ${kpis.estimationAccuracy.change}\n`;
    out += `✅ Completion Rate: **${kpis.completionRate.value}** ${kpis.completionRate.change}`;
  }
  if (sprint) {
    const pct = sprint.totalTickets > 0 ? Math.round((sprint.completedTickets / sprint.totalTickets) * 100) : 0;
    out += `\n\n📊 Current sprint: **${pct}%** done · ${sprint.daysRemaining} days left`;
  }
  return out.trimEnd();
}

function generateKpiSummary(ctx: AssistantContext): string {
  const { kpis, blockers, tickets } = ctx;
  const poorCount = tickets.filter(t => t.qualityScore < 60).length;
  const avgQ = tickets.length > 0
    ? Math.round(tickets.reduce((s,t) => s + t.qualityScore, 0) / tickets.length) : 0;

  let out = `📊 **Project KPI Dashboard — ${ctx.projectName}:**\n\n`;

  if (kpis) {
    out += `⚡ Velocity: **${kpis.velocity.value}**\n`;
    out += `⏱ Cycle Time: **${kpis.cycleTime.value}**\n`;
    out += `📬 Lead Time: **${kpis.leadTime.value}**\n`;
    out += `🎯 Estimation Accuracy: **${kpis.estimationAccuracy.value}**\n`;
    out += `✅ Completion Rate: **${kpis.completionRate.value}**\n`;
    out += `🚧 Active Blockers: **${kpis.blockedCount.value}**\n`;
  }

  out += `\n🏷 Ticket Quality:\n`;
  out += `  • Average: **${avgQ}%**\n`;
  out += `  • Needs attention: **${poorCount}** tickets below 60%\n`;
  out += `  • Active blockers: **${blockers.length}**`;

  return out.trimEnd();
}

function generateActionList(ctx: AssistantContext): string {
  const open = ctx.actions.filter(a => !["resolved", "dismissed"].includes(a.status));
  if (open.length === 0) return "No open actions are currently visible for this project.";

  const critical = open.filter(a => a.priority === "critical" || a.status === "awaiting_approval");
  const list = (critical.length ? critical : open).slice(0, 6);
  let out = `There are **${pluralise(open.length, "open action")}** in ${ctx.projectName}.\n\n`;
  list.forEach(a => {
    out += `• **${a.title}** — ${a.priority} · ${a.status.replace("_", " ")} · ${a.owner_role ?? "unassigned"}\n`;
  });
  return out.trimEnd();
}

function generateActionPriority(ctx: AssistantContext): string {
  const open = ctx.actions.filter(a => !["resolved", "dismissed"].includes(a.status));
  if (open.length === 0) return "No open actions are currently visible. Generate the Action Center queue if you need a fresh triage pass.";

  const priorityRank: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
  const top = [...open].sort((a, b) => {
    const byPriority = (priorityRank[a.priority] ?? 4) - (priorityRank[b.priority] ?? 4);
    if (byPriority !== 0) return byPriority;
    return (a.due_at ?? "9999").localeCompare(b.due_at ?? "9999");
  })[0];

  return `Start with **${top.title}**.\n\n` +
    `Reason: it is **${top.priority}** priority and currently **${top.status.replace("_", " ")}**.\n` +
    `Next step: ${top.recommended_action}`;
}

function generateGenericSearch(ctx: AssistantContext, results: SearchResult[]): string {
  if (results.length === 0) {
    return `I couldn't find specific data matching your query in the current project. Try asking about:\n\n` +
      `• "Which tickets are blocked?"\n` +
      `• "Show stalled tickets over 48h"\n` +
      `• "What's the sprint velocity?"\n` +
      `• "How many tickets have poor quality?"\n` +
      `• "Summarize the current sprint"`;
  }

  const types = [...new Set(results.map(r => r.record.type))];
  let out = `🔍 Found **${results.length} relevant records** (${types.join(", ")}):\n\n`;

  for (const result of results.slice(0, 5)) {
    const m = result.record.metadata;
    switch (result.record.type) {
      case "ticket": {
        const t = m as UITicket;
        out += `• **${t.id}** _${t.title}_ — ${t.status} · ${t.priority} · ${t.qualityScore}% quality\n`;
        break;
      }
      case "blocker": {
        const b = m as UIBlocker;
        out += `• **${b.ticketId}** _${b.title}_ — stalled ${formatHours(b.stalledHours)} · Level ${b.escalationLevel}\n`;
        break;
      }
      case "developer": {
        const d = m as UIDeveloper;
        const pct = d.totalPoints > 0 ? Math.round((d.completedPoints / d.totalPoints) * 100) : 0;
        out += `• **${d.name}** (${d.role}) — ${pct}% complete · ${d.status}\n`;
        break;
      }
      default:
        out += `• ${result.record.text}\n`;
    }
  }

  return out.trimEnd();
}

// ── Main entry point ──────────────────────────────────────────────────────────

export function generateResponse(query: string, ctx: AssistantContext): string {
  const intent  = detectIntent(query);
  const results = vectorDb.search(query, 7);

  switch (intent) {
    case "blockers_list":        return generateBlockersList(ctx);
    case "blockers_stalled":     return generateStalledBlockers(ctx, query);
    case "ticket_status":        return generateTicketStatus(ctx);
    case "ticket_quality_poor":  return generatePoorQuality(ctx);
    case "ticket_quality_high":  return generateHighQuality(ctx);
    case "developer_performance":return generateDeveloperPerformance(ctx, query, results);
    case "developer_list":       return generateDeveloperList(ctx);
    case "sprint_summary":       return generateSprintSummary(ctx);
    case "sprint_velocity":      return generateVelocity(ctx);
    case "sprint_progress":      return generateSprintSummary(ctx);
    case "kpi_summary":          return generateKpiSummary(ctx);
    case "action_priority":      return generateActionPriority(ctx);
    case "action_list":          return generateActionList(ctx);
    case "ticket_search":        return generateGenericSearch(ctx, results);
    case "generic_search":       return generateGenericSearch(ctx, results);
    default:                     return generateGenericSearch(ctx, results);
  }
}

// ── Data indexing helpers ─────────────────────────────────────────────────────

export function indexDashboardData(ctx: AssistantContext): void {
  vectorDb.clear();

  // Tickets
  for (const t of ctx.tickets) {
    vectorDb.add({
      id:   `ticket-${t.id}`,
      type: "ticket",
      text: [
        t.id, t.title, t.status, t.priority,
        `${t.storyPoints} points`,
        `${t.qualityScore} percent quality`,
        t.labels.join(" "),
        t.qualityScore < 60 ? "poor quality needs attention" : "",
        t.qualityScore >= 80 ? "high quality good" : "",
        t.status === "blocked" ? "blocked stalled" : "",
      ].join(" "),
      metadata: t,
    });
  }

  // Blockers
  for (const b of ctx.blockers) {
    vectorDb.add({
      id:   `blocker-${b.id}`,
      type: "blocker",
      text: [
        b.ticketId, b.title, b.reason, b.impact,
        `stalled ${b.stalledHours} hours`,
        `escalation level ${b.escalationLevel}`,
        b.stalledHours >= 72 ? "management escalation critical" : "",
        b.stalledHours >= 48 ? "team lead alert urgent" : "",
        "blocker blocked stalled inactive",
      ].join(" "),
      metadata: b,
    });
  }

  // Developers
  for (const d of ctx.developers) {
    const pct = d.totalPoints > 0 ? Math.round((d.completedPoints / d.totalPoints) * 100) : 0;
    vectorDb.add({
      id:   `dev-${d.id}`,
      type: "developer",
      text: [
        d.name, d.role,
        `${d.completedPoints} completed points`,
        `${d.ticketsCompleted} tickets done`,
        `${pct} percent complete`,
        `${d.estimationAccuracy} accuracy`,
        `${d.avgCycleTime} cycle time`,
        d.status, `${d.blockers} blockers`,
        d.status === "behind"   ? "behind struggling" : "",
        d.status === "at-risk"  ? "at risk warning" : "",
        d.status === "on-track" ? "on track good" : "",
      ].join(" "),
      metadata: d,
    });
  }

  // Sprint
  if (ctx.sprint) {
    const s = ctx.sprint;
    const pct = s.totalTickets > 0 ? Math.round((s.completedTickets / s.totalTickets) * 100) : 0;
    vectorDb.add({
      id:   "sprint-current",
      type: "sprint",
      text: [
        s.name,
        `sprint progress ${pct} percent`,
        `${s.completedTickets} completed tickets`,
        `${s.inProgressTickets} in progress`,
        `${s.blockedTickets} blocked`,
        `${s.daysRemaining} days remaining`,
        `velocity ${s.velocity}`,
        "sprint burndown active current",
      ].join(" "),
      metadata: s,
    });
  }

  // KPIs
  if (ctx.kpis) {
    const k = ctx.kpis;
    vectorDb.add({
      id:   "kpis",
      type: "kpi",
      text: [
        `velocity ${k.velocity.value}`,
        `cycle time ${k.cycleTime.value}`,
        `lead time ${k.leadTime.value}`,
        `estimation accuracy ${k.estimationAccuracy.value}`,
        `completion rate ${k.completionRate.value}`,
        `blockers ${k.blockedCount.value}`,
        "kpi metrics performance dashboard",
      ].join(" "),
      metadata: k,
    });
  }

  // Action Center
  for (const a of ctx.actions) {
    vectorDb.add({
      id:   `action-${a.id}`,
      type: "action",
      text: [
        a.title,
        a.description ?? "",
        a.recommended_action,
        a.source_type,
        a.priority,
        a.status,
        a.owner_role ?? "",
        a.approval_required ? "approval required" : "",
        a.due_at ? `due ${a.due_at}` : "",
      ].join(" "),
      metadata: a,
    });
  }

  vectorDb.buildIndex();
}
