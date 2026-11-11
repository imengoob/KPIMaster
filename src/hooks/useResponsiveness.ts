import { useQuery } from '@tanstack/react-query';
import { analyticsApi, ResponsivenessMetrics } from '@/services/api/analytics';
import type { PlatformFilter } from '@/lib/platforms';

export function useResponsivenessAnalytics(
  projectId: number | undefined,
  startDate?: string,
  endDate?: string,
  platform?: PlatformFilter,
) {
  return useQuery<ResponsivenessMetrics>({
    queryKey: ['analytics', 'responsiveness', projectId, startDate, endDate, platform],
    queryFn: () => analyticsApi.getResponsiveness(projectId!, startDate, endDate, platform),
    enabled: !!projectId,
    staleTime: 5 * 60 * 1000,
  });
}
