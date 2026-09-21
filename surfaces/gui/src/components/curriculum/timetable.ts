// Shared with the native reminder service; explicit source weeks include make-ups.
import { CALENDAR } from "./calendar";
import data from "./timetable-data.json";

export const PERIODS = data.periods;
const COURSES = data.courses;

type CourseId = keyof typeof COURSES;
type Schedule = {
  course: CourseId;
  day: number; // Monday = 1, Sunday = 7.
  first: number;
  last: number;
  weeks: readonly number[];
  teacher: string;
  room: string;
};

const SCHEDULE = data.schedule as Schedule[];

const DAY_MS = 86_400_000;
const AUTUMN_START = data.semesterStart;
const SPRING_START = "2027-03-01";
export const MIN_DATE = "1900-01-01";
export const MAX_DATE = "2100-12-31";

// Date-only arithmetic stays in UTC. Only the real clock is converted to Shanghai.
export function shanghaiToday(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

export function validDate(date: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date < MIN_DATE || date > MAX_DATE) return false;
  const parsed = new Date(`${date}T00:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === date;
}

export function addDays(date: string, days: number): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

export function mondayOf(date: string): string {
  const day = new Date(`${date}T00:00:00Z`).getUTCDay();
  return addDays(date, -((day + 6) % 7));
}

export function minutes(time: string): number {
  const [hours, mins] = time.split(":").map(Number);
  return hours * 60 + mins;
}

export type Occurrence = Schedule & {
  id: string;
  date: string;
  name: string;
  color: string;
  start: string;
  end: string;
};

export function curriculumWeek(date: string) {
  const monday = mondayOf(date);
  const autumn = monday >= AUTUMN_START && monday <= "2027-01-18";
  const spring = monday >= SPRING_START && monday <= "2027-06-28";
  const semester = autumn ? "autumn" : spring ? "spring" : null;
  const start = autumn ? AUTUMN_START : SPRING_START;
  const week = semester ? Math.round((Date.parse(monday) - Date.parse(start)) / (7 * DAY_MS)) + 1 : null;
  const days = Array.from({ length: 7 }, (_, index) => {
    const dayDate = addDays(monday, index);
    const covered = dayDate >= AUTUMN_START && dayDate <= "2027-01-20";
    const courses: Occurrence[] = covered ? SCHEDULE
      .filter(slot => slot.day === index + 1 && slot.weeks.includes(week!))
      .map(slot => ({
        ...slot, ...COURSES[slot.course], date: dayDate,
        id: `${dayDate}-${slot.course}-${slot.first}`,
        start: PERIODS[slot.first - 1][0], end: PERIODS[slot.last - 1][1],
      })).sort((a, b) => a.first - b.first) : [];
    return { date: dayDate, covered, courses, events: CALENDAR.filter(event => event.start <= dayDate && event.end >= dayDate) };
  });
  const notes = CALENDAR.filter(event => event.note && event.start <= addDays(monday, 6) && event.end >= monday);
  return { monday, semester, week, days, notes, count: days.reduce((total, day) => total + day.courses.length, 0) };
}
