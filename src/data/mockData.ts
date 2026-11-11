// Mock data for multi-project dashboard

export interface Ticket {
  id: string;
  title: string;
  assignee: string;
  status: "completed" | "in-progress" | "not-started" | "blocked" | "overdue";
  priority: "high" | "medium" | "low";
  storyPoints: number;
  dueDate: string;
  qualityScore: number;
  labels: string[];
  stalledHours?: number;
}

export interface Developer {
  name: string;
  avatar: string;
  role: string;
  completedPoints: number;
  totalPoints: number;
  ticketsCompleted: number;
  ticketsTotal: number;
  avgCycleTime: number;
  estimationAccuracy: number;
  status: "on-track" | "at-risk" | "behind";
  blockers: number;
}

export interface BlockerItem {
  ticketId: string;
  title: string;
  assignee: string;
  stalledHours: number;
  escalationLevel: 1 | 2 | 3;
  reason: string;
  impact: string;
  lastActivity: string;
}

export interface RepoActivity {
  ticket: string;
  branch: string;
  commits: number;
  prs: number;
  prStatus: "merged" | "open" | "review" | "none";
  lastCommit: string;
  mismatch: boolean;
  repo: string;
}

export interface SprintDataType {
  name: string;
  startDate: string;
  endDate: string;
  daysRemaining: number;
  totalTickets: number;
  completedTickets: number;
  inProgressTickets: number;
  notStartedTickets: number;
  blockedTickets: number;
  velocity: number;
  previousVelocity: number;
}

export interface KpiDataType {
  cycleTime: { value: string; change: string; type: "positive" | "negative" | "neutral" };
  leadTime: { value: string; change: string; type: "positive" | "negative" | "neutral" };
  estimationAccuracy: { value: string; change: string; type: "positive" | "negative" | "neutral" };
  blockedCount: { value: number; change: string; type: "positive" | "negative" | "neutral" };
  velocity: { value: string; change: string; type: "positive" | "negative" | "neutral" };
  completionRate: { value: string; change: string; type: "positive" | "negative" | "neutral" };
}

interface ProjectData {
  sprintData: SprintDataType;
  kpiData: KpiDataType;
  tickets: Ticket[];
  developers: Developer[];
  blockers: BlockerItem[];
  sprintBurndown: { day: string; ideal: number; actual: number }[];
  velocityHistory: { sprint: string; points: number }[];
  repoActivity: RepoActivity[];
}

// ─── Project 1: KPIMaster Platform ────────────────────────────────────
const project1: ProjectData = {
  sprintData: {
    name: "Sprint 24",
    startDate: "2026-02-23",
    endDate: "2026-03-08",
    daysRemaining: 0,
    totalTickets: 42,
    completedTickets: 31,
    inProgressTickets: 7,
    notStartedTickets: 2,
    blockedTickets: 2,
    velocity: 68,
    previousVelocity: 62,
  },
  kpiData: {
    cycleTime: { value: "2.4 days", change: "-0.3 days vs last sprint", type: "positive" },
    leadTime: { value: "4.8 days", change: "-0.5 days vs last sprint", type: "positive" },
    estimationAccuracy: { value: "82%", change: "+5% vs last sprint", type: "positive" },
    blockedCount: { value: 2, change: "1 resolved today", type: "neutral" },
    velocity: { value: "68 pts", change: "+6 pts vs last sprint", type: "positive" },
    completionRate: { value: "73.8%", change: "On track for sprint goal", type: "positive" },
  },
  tickets: [
    { id: "TKT-201", title: "Implement OAuth 2.0 login flow", assignee: "Sarah Chen", status: "completed", priority: "high", storyPoints: 8, dueDate: "2026-03-03", qualityScore: 95, labels: ["auth", "backend"] },
    { id: "TKT-202", title: "Design dashboard layout", assignee: "Marcus Rivera", status: "completed", priority: "high", storyPoints: 5, dueDate: "2026-03-02", qualityScore: 88, labels: ["frontend", "design"] },
    { id: "TKT-203", title: "API rate limiting middleware", assignee: "James Park", status: "in-progress", priority: "high", storyPoints: 5, dueDate: "2026-03-07", qualityScore: 72, labels: ["backend", "security"] },
    { id: "TKT-204", title: "User profile settings page", assignee: "Emily Zhang", status: "in-progress", priority: "medium", storyPoints: 3, dueDate: "2026-03-06", qualityScore: 60, labels: ["frontend"] },
    { id: "TKT-205", title: "Database migration scripts", assignee: "Sarah Chen", status: "blocked", priority: "high", storyPoints: 8, dueDate: "2026-03-05", qualityScore: 85, labels: ["backend", "database"], stalledHours: 36 },
    { id: "TKT-206", title: "Email notification service", assignee: "Raj Patel", status: "overdue", priority: "medium", storyPoints: 5, dueDate: "2026-03-04", qualityScore: 45, labels: ["backend", "notifications"] },
    { id: "TKT-207", title: "Unit tests for auth module", assignee: "James Park", status: "in-progress", priority: "medium", storyPoints: 3, dueDate: "2026-03-08", qualityScore: 90, labels: ["testing"] },
    { id: "TKT-208", title: "Mobile responsive navigation", assignee: "Emily Zhang", status: "not-started", priority: "low", storyPoints: 3, dueDate: "2026-03-08", qualityScore: 50, labels: ["frontend", "mobile"] },
    { id: "TKT-209", title: "CI/CD pipeline optimization", assignee: "Marcus Rivera", status: "completed", priority: "medium", storyPoints: 5, dueDate: "2026-03-05", qualityScore: 92, labels: ["devops"] },
    { id: "TKT-210", title: "Search functionality with filters", assignee: "Raj Patel", status: "blocked", priority: "high", storyPoints: 8, dueDate: "2026-03-07", qualityScore: 78, labels: ["frontend", "backend"], stalledHours: 52 },
  ],
  developers: [
    { name: "Sarah Chen", avatar: "SC", role: "Senior Backend", completedPoints: 16, totalPoints: 24, ticketsCompleted: 3, ticketsTotal: 4, avgCycleTime: 2.1, estimationAccuracy: 88, status: "on-track", blockers: 1 },
    { name: "Marcus Rivera", avatar: "MR", role: "Full Stack", completedPoints: 10, totalPoints: 13, ticketsCompleted: 2, ticketsTotal: 3, avgCycleTime: 2.8, estimationAccuracy: 75, status: "on-track", blockers: 0 },
    { name: "James Park", avatar: "JP", role: "Backend Engineer", completedPoints: 5, totalPoints: 13, ticketsCompleted: 1, ticketsTotal: 3, avgCycleTime: 3.2, estimationAccuracy: 70, status: "at-risk", blockers: 0 },
    { name: "Emily Zhang", avatar: "EZ", role: "Frontend Engineer", completedPoints: 0, totalPoints: 6, ticketsCompleted: 0, ticketsTotal: 2, avgCycleTime: 0, estimationAccuracy: 65, status: "behind", blockers: 0 },
    { name: "Raj Patel", avatar: "RP", role: "Backend Engineer", completedPoints: 0, totalPoints: 13, ticketsCompleted: 0, ticketsTotal: 2, avgCycleTime: 4.1, estimationAccuracy: 60, status: "behind", blockers: 1 },
  ],
  blockers: [
    { ticketId: "TKT-205", title: "Database migration scripts", assignee: "Sarah Chen", stalledHours: 36, escalationLevel: 2, reason: "Waiting on DBA approval for schema changes", impact: "Blocks 3 downstream tickets", lastActivity: "2026-03-06 14:30" },
    { ticketId: "TKT-210", title: "Search functionality with filters", assignee: "Raj Patel", stalledHours: 52, escalationLevel: 3, reason: "Elasticsearch cluster configuration issue", impact: "Blocks search feature release", lastActivity: "2026-03-05 09:15" },
  ],
  sprintBurndown: [
    { day: "Day 1", ideal: 42, actual: 42 }, { day: "Day 2", ideal: 39, actual: 40 },
    { day: "Day 3", ideal: 36, actual: 38 }, { day: "Day 4", ideal: 33, actual: 36 },
    { day: "Day 5", ideal: 30, actual: 33 }, { day: "Day 6", ideal: 27, actual: 29 },
    { day: "Day 7", ideal: 24, actual: 25 }, { day: "Day 8", ideal: 21, actual: 22 },
    { day: "Day 9", ideal: 18, actual: 18 }, { day: "Day 10", ideal: 14, actual: 14 },
    { day: "Day 11", ideal: 11, actual: 13 }, { day: "Day 12", ideal: 7, actual: 11 },
    { day: "Day 13", ideal: 4, actual: 9 }, { day: "Day 14", ideal: 0, actual: 4 },
  ],
  velocityHistory: [
    { sprint: "Sprint 20", points: 52 }, { sprint: "Sprint 21", points: 58 },
    { sprint: "Sprint 22", points: 55 }, { sprint: "Sprint 23", points: 62 },
    { sprint: "Sprint 24", points: 68 },
  ],
  repoActivity: [
    { ticket: "TKT-201", branch: "feat/oauth-login", commits: 14, prs: 1, prStatus: "merged", lastCommit: "2h ago", mismatch: false, repo: "sprintpulse-web" },
    { ticket: "TKT-203", branch: "feat/rate-limiting", commits: 8, prs: 1, prStatus: "open", lastCommit: "5h ago", mismatch: false, repo: "sprintpulse-api" },
    { ticket: "TKT-204", branch: "feat/profile-settings", commits: 3, prs: 0, prStatus: "none", lastCommit: "1d ago", mismatch: false, repo: "sprintpulse-web" },
    { ticket: "TKT-205", branch: "fix/db-migration", commits: 2, prs: 0, prStatus: "none", lastCommit: "36h ago", mismatch: true, repo: "sprintpulse-api" },
    { ticket: "TKT-206", branch: "feat/email-notify", commits: 0, prs: 0, prStatus: "none", lastCommit: "never", mismatch: true, repo: "sprintpulse-api" },
    { ticket: "TKT-207", branch: "test/auth-module", commits: 6, prs: 1, prStatus: "review", lastCommit: "3h ago", mismatch: false, repo: "sprintpulse-web" },
    { ticket: "TKT-210", branch: "feat/search-filters", commits: 1, prs: 0, prStatus: "none", lastCommit: "52h ago", mismatch: true, repo: "sprintpulse-web" },
  ],
};

// ─── Project 2: CloudVault Storage ──────────────────────────────────────
const project2: ProjectData = {
  sprintData: {
    name: "Sprint 12",
    startDate: "2026-02-25",
    endDate: "2026-03-11",
    daysRemaining: 3,
    totalTickets: 28,
    completedTickets: 18,
    inProgressTickets: 6,
    notStartedTickets: 3,
    blockedTickets: 1,
    velocity: 45,
    previousVelocity: 42,
  },
  kpiData: {
    cycleTime: { value: "3.1 days", change: "+0.2 days vs last sprint", type: "negative" },
    leadTime: { value: "5.5 days", change: "-0.1 days vs last sprint", type: "positive" },
    estimationAccuracy: { value: "76%", change: "-2% vs last sprint", type: "negative" },
    blockedCount: { value: 1, change: "0 resolved today", type: "neutral" },
    velocity: { value: "45 pts", change: "+3 pts vs last sprint", type: "positive" },
    completionRate: { value: "64.3%", change: "Slightly behind target", type: "negative" },
  },
  tickets: [
    { id: "CVS-101", title: "Implement S3 bucket replication", assignee: "Alex Kim", status: "completed", priority: "high", storyPoints: 8, dueDate: "2026-03-02", qualityScore: 91, labels: ["storage", "infra"] },
    { id: "CVS-102", title: "File versioning API", assignee: "Diana Ross", status: "completed", priority: "high", storyPoints: 5, dueDate: "2026-03-03", qualityScore: 85, labels: ["api", "backend"] },
    { id: "CVS-103", title: "Encryption at rest for blobs", assignee: "Tom Lee", status: "in-progress", priority: "high", storyPoints: 8, dueDate: "2026-03-09", qualityScore: 68, labels: ["security", "storage"] },
    { id: "CVS-104", title: "SDK retry logic", assignee: "Nina Patel", status: "in-progress", priority: "medium", storyPoints: 3, dueDate: "2026-03-08", qualityScore: 74, labels: ["sdk"] },
    { id: "CVS-105", title: "Terraform module for storage cluster", assignee: "Alex Kim", status: "blocked", priority: "high", storyPoints: 5, dueDate: "2026-03-07", qualityScore: 80, labels: ["infra", "devops"], stalledHours: 28 },
    { id: "CVS-106", title: "Usage analytics dashboard", assignee: "Diana Ross", status: "not-started", priority: "low", storyPoints: 3, dueDate: "2026-03-11", qualityScore: 55, labels: ["frontend"] },
    { id: "CVS-107", title: "Multipart upload support", assignee: "Tom Lee", status: "in-progress", priority: "high", storyPoints: 5, dueDate: "2026-03-10", qualityScore: 72, labels: ["api", "storage"] },
    { id: "CVS-108", title: "CDN cache invalidation", assignee: "Nina Patel", status: "completed", priority: "medium", storyPoints: 3, dueDate: "2026-03-04", qualityScore: 88, labels: ["infra"] },
  ],
  developers: [
    { name: "Alex Kim", avatar: "AK", role: "Infra Engineer", completedPoints: 13, totalPoints: 18, ticketsCompleted: 2, ticketsTotal: 3, avgCycleTime: 2.5, estimationAccuracy: 82, status: "on-track", blockers: 1 },
    { name: "Diana Ross", avatar: "DR", role: "Backend Engineer", completedPoints: 8, totalPoints: 11, ticketsCompleted: 2, ticketsTotal: 3, avgCycleTime: 2.9, estimationAccuracy: 78, status: "on-track", blockers: 0 },
    { name: "Tom Lee", avatar: "TL", role: "Storage Specialist", completedPoints: 5, totalPoints: 16, ticketsCompleted: 1, ticketsTotal: 3, avgCycleTime: 3.8, estimationAccuracy: 65, status: "at-risk", blockers: 0 },
    { name: "Nina Patel", avatar: "NP", role: "SDK Engineer", completedPoints: 3, totalPoints: 6, ticketsCompleted: 1, ticketsTotal: 2, avgCycleTime: 2.2, estimationAccuracy: 80, status: "on-track", blockers: 0 },
  ],
  blockers: [
    { ticketId: "CVS-105", title: "Terraform module for storage cluster", assignee: "Alex Kim", stalledHours: 28, escalationLevel: 1, reason: "Waiting on AWS account permissions from platform team", impact: "Delays staging environment setup", lastActivity: "2026-03-07 10:00" },
  ],
  sprintBurndown: [
    { day: "Day 1", ideal: 28, actual: 28 }, { day: "Day 2", ideal: 26, actual: 27 },
    { day: "Day 3", ideal: 24, actual: 25 }, { day: "Day 4", ideal: 22, actual: 23 },
    { day: "Day 5", ideal: 20, actual: 21 }, { day: "Day 6", ideal: 18, actual: 19 },
    { day: "Day 7", ideal: 16, actual: 17 }, { day: "Day 8", ideal: 14, actual: 15 },
    { day: "Day 9", ideal: 12, actual: 13 }, { day: "Day 10", ideal: 10, actual: 10 },
    { day: "Day 11", ideal: 7, actual: 10 }, { day: "Day 12", ideal: 5, actual: 8 },
  ],
  velocityHistory: [
    { sprint: "Sprint 8", points: 35 }, { sprint: "Sprint 9", points: 38 },
    { sprint: "Sprint 10", points: 40 }, { sprint: "Sprint 11", points: 42 },
    { sprint: "Sprint 12", points: 45 },
  ],
  repoActivity: [
    { ticket: "CVS-101", branch: "feat/s3-replication", commits: 12, prs: 1, prStatus: "merged", lastCommit: "1d ago", mismatch: false, repo: "cloudvault-core" },
    { ticket: "CVS-103", branch: "feat/encryption-at-rest", commits: 6, prs: 1, prStatus: "open", lastCommit: "4h ago", mismatch: false, repo: "cloudvault-core" },
    { ticket: "CVS-104", branch: "fix/sdk-retry", commits: 4, prs: 0, prStatus: "none", lastCommit: "8h ago", mismatch: false, repo: "cloudvault-sdk" },
    { ticket: "CVS-105", branch: "feat/terraform-storage", commits: 1, prs: 0, prStatus: "none", lastCommit: "28h ago", mismatch: true, repo: "cloudvault-infra" },
    { ticket: "CVS-107", branch: "feat/multipart-upload", commits: 5, prs: 1, prStatus: "review", lastCommit: "2h ago", mismatch: false, repo: "cloudvault-core" },
  ],
};

// ─── Project 3: MerchantFlow ────────────────────────────────────────────
const project3: ProjectData = {
  sprintData: {
    name: "Sprint 8",
    startDate: "2026-02-27",
    endDate: "2026-03-13",
    daysRemaining: 5,
    totalTickets: 20,
    completedTickets: 8,
    inProgressTickets: 8,
    notStartedTickets: 1,
    blockedTickets: 3,
    velocity: 32,
    previousVelocity: 30,
  },
  kpiData: {
    cycleTime: { value: "3.8 days", change: "+0.5 days vs last sprint", type: "negative" },
    leadTime: { value: "6.2 days", change: "+0.8 days vs last sprint", type: "negative" },
    estimationAccuracy: { value: "68%", change: "-4% vs last sprint", type: "negative" },
    blockedCount: { value: 3, change: "1 new today", type: "negative" },
    velocity: { value: "32 pts", change: "+2 pts vs last sprint", type: "positive" },
    completionRate: { value: "40%", change: "Behind sprint goal", type: "negative" },
  },
  tickets: [
    { id: "MFL-301", title: "Stripe Connect onboarding", assignee: "Liam Chen", status: "completed", priority: "high", storyPoints: 8, dueDate: "2026-03-04", qualityScore: 90, labels: ["payments", "onboarding"] },
    { id: "MFL-302", title: "Merchant dashboard analytics", assignee: "Priya Sharma", status: "in-progress", priority: "high", storyPoints: 5, dueDate: "2026-03-10", qualityScore: 65, labels: ["frontend", "analytics"] },
    { id: "MFL-303", title: "Refund processing API", assignee: "Liam Chen", status: "blocked", priority: "high", storyPoints: 8, dueDate: "2026-03-09", qualityScore: 78, labels: ["payments", "api"], stalledHours: 44 },
    { id: "MFL-304", title: "Webhook event handler", assignee: "Aisha Omar", status: "in-progress", priority: "medium", storyPoints: 5, dueDate: "2026-03-11", qualityScore: 70, labels: ["backend", "webhooks"] },
    { id: "MFL-305", title: "KYC document upload", assignee: "Ben Torres", status: "blocked", priority: "high", storyPoints: 5, dueDate: "2026-03-08", qualityScore: 58, labels: ["compliance", "frontend"], stalledHours: 60 },
    { id: "MFL-306", title: "Transaction reconciliation", assignee: "Priya Sharma", status: "in-progress", priority: "medium", storyPoints: 3, dueDate: "2026-03-12", qualityScore: 72, labels: ["payments"] },
    { id: "MFL-307", title: "Payout scheduling system", assignee: "Aisha Omar", status: "blocked", priority: "high", storyPoints: 8, dueDate: "2026-03-10", qualityScore: 62, labels: ["payments", "backend"], stalledHours: 32 },
    { id: "MFL-308", title: "Multi-currency support", assignee: "Ben Torres", status: "not-started", priority: "medium", storyPoints: 5, dueDate: "2026-03-13", qualityScore: 50, labels: ["payments"] },
  ],
  developers: [
    { name: "Liam Chen", avatar: "LC", role: "Payments Lead", completedPoints: 8, totalPoints: 16, ticketsCompleted: 1, ticketsTotal: 2, avgCycleTime: 3.5, estimationAccuracy: 72, status: "at-risk", blockers: 1 },
    { name: "Priya Sharma", avatar: "PS", role: "Frontend Engineer", completedPoints: 3, totalPoints: 8, ticketsCompleted: 1, ticketsTotal: 2, avgCycleTime: 4.0, estimationAccuracy: 65, status: "behind", blockers: 0 },
    { name: "Aisha Omar", avatar: "AO", role: "Backend Engineer", completedPoints: 0, totalPoints: 13, ticketsCompleted: 0, ticketsTotal: 2, avgCycleTime: 0, estimationAccuracy: 58, status: "behind", blockers: 1 },
    { name: "Ben Torres", avatar: "BT", role: "Full Stack", completedPoints: 0, totalPoints: 10, ticketsCompleted: 0, ticketsTotal: 2, avgCycleTime: 0, estimationAccuracy: 60, status: "behind", blockers: 1 },
  ],
  blockers: [
    { ticketId: "MFL-303", title: "Refund processing API", assignee: "Liam Chen", stalledHours: 44, escalationLevel: 2, reason: "Stripe sandbox environment is down", impact: "Blocks all payment testing", lastActivity: "2026-03-07 11:00" },
    { ticketId: "MFL-305", title: "KYC document upload", assignee: "Ben Torres", stalledHours: 60, escalationLevel: 3, reason: "Legal review pending on document retention policy", impact: "Blocks merchant onboarding flow", lastActivity: "2026-03-05 16:30" },
    { ticketId: "MFL-307", title: "Payout scheduling system", assignee: "Aisha Omar", stalledHours: 32, escalationLevel: 1, reason: "Dependency on transaction reconciliation module", impact: "Delays payout feature launch", lastActivity: "2026-03-07 09:00" },
  ],
  sprintBurndown: [
    { day: "Day 1", ideal: 20, actual: 20 }, { day: "Day 2", ideal: 18, actual: 19 },
    { day: "Day 3", ideal: 17, actual: 18 }, { day: "Day 4", ideal: 15, actual: 17 },
    { day: "Day 5", ideal: 13, actual: 16 }, { day: "Day 6", ideal: 12, actual: 15 },
    { day: "Day 7", ideal: 10, actual: 14 }, { day: "Day 8", ideal: 8, actual: 12 },
    { day: "Day 9", ideal: 7, actual: 12 },
  ],
  velocityHistory: [
    { sprint: "Sprint 4", points: 22 }, { sprint: "Sprint 5", points: 25 },
    { sprint: "Sprint 6", points: 28 }, { sprint: "Sprint 7", points: 30 },
    { sprint: "Sprint 8", points: 32 },
  ],
  repoActivity: [
    { ticket: "MFL-301", branch: "feat/stripe-connect", commits: 18, prs: 1, prStatus: "merged", lastCommit: "1d ago", mismatch: false, repo: "merchantflow-payments" },
    { ticket: "MFL-302", branch: "feat/merchant-dashboard", commits: 7, prs: 1, prStatus: "open", lastCommit: "3h ago", mismatch: false, repo: "merchantflow-app" },
    { ticket: "MFL-303", branch: "feat/refund-api", commits: 3, prs: 0, prStatus: "none", lastCommit: "44h ago", mismatch: true, repo: "merchantflow-payments" },
    { ticket: "MFL-305", branch: "feat/kyc-upload", commits: 0, prs: 0, prStatus: "none", lastCommit: "never", mismatch: true, repo: "merchantflow-app" },
    { ticket: "MFL-307", branch: "feat/payout-scheduler", commits: 2, prs: 0, prStatus: "none", lastCommit: "32h ago", mismatch: true, repo: "merchantflow-payments" },
  ],
};

// ─── Export by project ID ───────────────────────────────────────────────
const allProjectData: Record<string, ProjectData> = {
  "proj-1": project1,
  "proj-2": project2,
  "proj-3": project3,
};

export const getProjectData = (projectId: string): ProjectData => {
  return allProjectData[projectId] || project1;
};

// Legacy exports for backward compatibility
export const sprintData = project1.sprintData;
export const kpiData = project1.kpiData;
export const tickets = project1.tickets;
export const developers = project1.developers;
export const blockers = project1.blockers;
export const sprintBurndown = project1.sprintBurndown;
export const velocityHistory = project1.velocityHistory;
