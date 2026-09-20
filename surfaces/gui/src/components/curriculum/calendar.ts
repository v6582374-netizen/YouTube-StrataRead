// University calendars supplied by the user. These annotations never generate
// or cancel personal course occurrences. 2027 holiday adjustments are provisional.
export type CalendarEvent = { start: string; end: string; key: string; note?: string };
export const CALENDAR: readonly CalendarEvent[] = [
  { start: "2026-08-28", end: "2026-08-28", key: "new_registration" },
  { start: "2026-08-29", end: "2026-09-13", key: "orientation" },
  { start: "2026-09-11", end: "2026-09-11", key: "registration" },
  { start: "2026-09-14", end: "2026-09-14", key: "teaching_starts" },
  { start: "2026-09-20", end: "2026-09-20", key: "makeup", note: "friday_makeup" },
  { start: "2026-09-25", end: "2026-09-27", key: "mid_autumn" },
  { start: "2026-10-01", end: "2026-10-07", key: "national_day" },
  { start: "2026-10-10", end: "2026-10-10", key: "makeup", note: "odd_friday_makeup" },
  { start: "2026-10-30", end: "2026-10-31", key: "sports" },
  { start: "2026-11-09", end: "2026-11-15", key: "midterms", note: "classes_continue" },
  { start: "2027-01-01", end: "2027-01-01", key: "new_year", note: "adjustments_pending" },
  { start: "2027-01-12", end: "2027-01-20", key: "finals", note: "exams_unknown" },
  { start: "2027-01-21", end: "2027-01-21", key: "winter_break" },
  { start: "2027-02-26", end: "2027-02-26", key: "registration" },
  { start: "2027-03-01", end: "2027-03-01", key: "teaching_starts" },
  { start: "2027-04-05", end: "2027-04-05", key: "qingming", note: "adjustments_pending" },
  { start: "2027-04-19", end: "2027-04-25", key: "midterms", note: "classes_continue" },
  { start: "2027-05-01", end: "2027-05-01", key: "labour_day", note: "adjustments_pending" },
  { start: "2027-06-09", end: "2027-06-09", key: "dragon_boat", note: "adjustments_pending" },
  { start: "2027-06-25", end: "2027-06-25", key: "graduates_leave" },
  { start: "2027-06-26", end: "2027-07-04", key: "finals", note: "exams_unknown" },
  { start: "2027-07-05", end: "2027-07-05", key: "summer_break" },
];
