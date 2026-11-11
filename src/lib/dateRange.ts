import { endOfDay, startOfDay } from "date-fns";
import type { DateRange } from "react-day-picker";

export function getApiDateRange(range: DateRange | undefined) {
  return {
    startDate: range?.from ? startOfDay(range.from).toISOString() : undefined,
    endDate: range?.to ? endOfDay(range.to).toISOString() : undefined,
  };
}
