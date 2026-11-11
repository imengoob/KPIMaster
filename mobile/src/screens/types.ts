import type { AuthUser, DashboardBundle, Project } from "../domain/types";

export interface ScreenProps {
  user: AuthUser;
  project: Project | null;
  data: DashboardBundle | null;
  isLoading: boolean;
  error: string | null;
  isRefreshing: boolean;
  onRefresh: () => Promise<void>;
}
