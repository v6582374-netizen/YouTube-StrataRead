// Transcribed from the user's 2026–2027-1 PDF (printed 2026-09-20).
// Weeks are explicit source lists. Weekend make-ups are already present here.
import { CALENDAR } from "./calendar";

export const PERIODS = [
  ["08:00", "08:45"], ["08:50", "09:35"], ["09:50", "10:35"],
  ["10:40", "11:25"], ["11:30", "12:15"], ["13:30", "14:15"],
  ["14:20", "15:05"], ["15:20", "16:05"], ["16:10", "16:55"],
  ["18:30", "19:15"], ["19:20", "20:05"], ["20:10", "20:55"],
] as const;

const COURSES = {
  math: { name: "工程数学", color: "#60816e" },
  microcontroller: { name: "单片机应用技术", color: "#547fa4" },
  ai: { name: "计算思维与人工智能", color: "#927341" },
  python: { name: "Python程序设计与应用", color: "#8372a5" },
  iot: { name: "物联网技术与原理", color: "#4b8986" },
  design: { name: "三维造型与工业设计", color: "#ad735d" },
  cpp: { name: "C++程序设计及上机", color: "#737aab" },
  visualization: { name: "科学计算可视化", color: "#9b7592" },
  exhibition: { name: "会展设计的艺术性", color: "#9a824e" },
  tourism: { name: "可持续旅游与数字创新", color: "#598b78" },
} as const;

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

const MON_TO_WED_WEEKS = [1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17];
const THURSDAY_WEEKS = [1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17];
const FRIDAY_WEEKS = [1, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 17];
const SCHEDULE: readonly Schedule[] = [
  { course: "math", day: 1, first: 3, last: 4, weeks: MON_TO_WED_WEEKS, teacher: "宋胜重", room: "教三401" },
  { course: "iot", day: 1, first: 3, last: 4, weeks: [18], teacher: "张懿", room: "理5A-306" },
  { course: "design", day: 1, first: 6, last: 7, weeks: [18], teacher: "张哲硕", room: "文3-115" },
  { course: "iot", day: 1, first: 8, last: 9, weeks: MON_TO_WED_WEEKS, teacher: "郑腾", room: "文1-108" },
  { course: "design", day: 1, first: 8, last: 9, weeks: [18], teacher: "张哲硕", room: "理5A-410" },
  { course: "microcontroller", day: 2, first: 1, last: 2, weeks: MON_TO_WED_WEEKS, teacher: "谢浩", room: "文3-115" },
  { course: "microcontroller", day: 2, first: 3, last: 4, weeks: MON_TO_WED_WEEKS, teacher: "谢浩", room: "理5A-302" },
  { course: "cpp", day: 2, first: 6, last: 7, weeks: MON_TO_WED_WEEKS, teacher: "王媛媛", room: "文3-211" },
  { course: "cpp", day: 2, first: 8, last: 9, weeks: MON_TO_WED_WEEKS, teacher: "王媛媛", room: "理5A-310" },
  { course: "exhibition", day: 2, first: 10, last: 11, weeks: MON_TO_WED_WEEKS, teacher: "周烨", room: "教七201" },
  { course: "ai", day: 3, first: 3, last: 5, weeks: MON_TO_WED_WEEKS, teacher: "尹琳", room: "理4-526" },
  { course: "math", day: 3, first: 6, last: 7, weeks: MON_TO_WED_WEEKS, teacher: "宋胜重", room: "教三401" },
  { course: "python", day: 4, first: 1, last: 2, weeks: THURSDAY_WEEKS, teacher: "田强兴", room: "文1-114" },
  { course: "python", day: 4, first: 3, last: 4, weeks: THURSDAY_WEEKS, teacher: "田强兴", room: "理5A-410" },
  { course: "visualization", day: 4, first: 6, last: 7, weeks: THURSDAY_WEEKS, teacher: "陈忠宝", room: "文1-114" },
  { course: "visualization", day: 4, first: 8, last: 9, weeks: THURSDAY_WEEKS, teacher: "陈忠宝", room: "理5A-306" },
  { course: "tourism", day: 4, first: 10, last: 12, weeks: THURSDAY_WEEKS, teacher: "KHAN ASIF", room: "教七106" },
  { course: "iot", day: 5, first: 3, last: 4, weeks: FRIDAY_WEEKS, teacher: "张懿", room: "理5A-306" },
  { course: "design", day: 5, first: 6, last: 7, weeks: FRIDAY_WEEKS, teacher: "张哲硕", room: "文3-115" },
  { course: "design", day: 5, first: 8, last: 9, weeks: FRIDAY_WEEKS, teacher: "张哲硕", room: "理5A-410" },
  { course: "iot", day: 6, first: 3, last: 4, weeks: [4], teacher: "张懿", room: "理5A-306" },
  { course: "design", day: 6, first: 6, last: 7, weeks: [4], teacher: "张哲硕", room: "文3-115" },
  { course: "design", day: 6, first: 8, last: 9, weeks: [4], teacher: "张哲硕", room: "理5A-410" },
  { course: "iot", day: 7, first: 3, last: 4, weeks: [1], teacher: "张懿", room: "理5A-306" },
  { course: "design", day: 7, first: 6, last: 7, weeks: [1], teacher: "张哲硕", room: "文3-115" },
  { course: "design", day: 7, first: 8, last: 9, weeks: [1], teacher: "张哲硕", room: "理5A-410" },
];

const DAY_MS = 86_400_000;
const AUTUMN_START = "2026-09-14";
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
