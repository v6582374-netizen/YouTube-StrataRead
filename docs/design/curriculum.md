# Curriculum

Status: implemented as a local, read-only sidebar module.

## Purpose and agreed scope

Curriculum is a sidebar module for viewing the person's courses by week, combining their timetable, the university calendar, and class period times. Its purpose is to make course commitments and gaps visible for personal planning elsewhere.

Confirmed by the user:

- Default to the current week, in a Monday–Sunday time grid.
- Previous/next week, jump to a date, and return to the current week.
- Show course name, actual time, and classroom directly on each occurrence.
- Personal tasks and task planning are outside the product boundary.
- No editing for temporary cancellations, classroom changes, or rescheduling.

The bounded feature does not require a long-running Wayfinder map. Remaining source reconciliation and implementation validation are engineering work, not additional product decisions.

## Sources and interpretation

- Personal timetable: `/Users/shiwen/Downloads/石文硕(2026-2027-1)课表-3.pdf`, printed 2026-09-20, for autumn 2026–2027.
- User image 1: university autumn calendar, instruction begins 2026-09-14; that Monday starts teaching week 1.
- User image 2: university spring calendar, instruction begins 2027-03-01. No personal spring timetable has been provided.
- User image 3: class period clock times. Its calendar belongs to 2025–2026 and must not supply this year's dates. The clock times agree with the supplied 2026–2027 calendars.

Use Asia/Shanghai for dates, today's marker, and week boundaries. Teaching weeks progress with calendar weeks, including holidays; do not restart or compress them after breaks.

The PDF's explicit weekday, teaching-week set, period range, teacher, and room are the authority for personal course occurrences. Calendar events provide context and a reconciliation check, not an extra recurrence generator. In particular, the PDF explicitly schedules Sunday week 1 (2026-09-20), Saturday week 4 (2026-10-10), and Monday week 18 (2027-01-11). Do not apply calendar make-up rules a second time or silently remove explicit courses because an exam-period banner overlaps.

The autumn calendar specifies 2026-09-25–27 as the Mid-Autumn break, 2026-10-01–07 as the National Day break, 2026-09-20 as Friday make-up instruction, and 2026-10-10 as odd-week Friday make-up instruction. It also identifies 2026-10-30–31 as sports days, 2026-11-09–15 as midterms without suspension, 2027-01-12–20 as final exams, and 2027-01-21 as winter break start. Calendar annotations do not establish personal exam times.

Distinguish a known empty week within imported timetable coverage from a week with no personal timetable. Spring calendar availability must never be presented as evidence of an empty personal spring schedule. Do not invent exams, courses, or unspecified holiday adjustments.

## Class periods

| Period | Time |
| --- | --- |
| 1 | 08:00–08:45 |
| 2 | 08:50–09:35 |
| 3 | 09:50–10:35 |
| 4 | 10:40–11:25 |
| 5 | 11:30–12:15 |
| 6 | 13:30–14:15 |
| 7 | 14:20–15:05 |
| 8 | 15:20–16:05 |
| 9 | 16:10–16:55 |
| 10 | 18:30–19:15 |
| 11 | 19:20–20:05 |
| 12 | 20:10–20:55 |

## Source extraction for implementation

The PDF contains 10 courses and 26 scheduling records; no odd/even-week restriction is explicitly marked. Recheck the PDF when creating the final data fixture. Week sets below abbreviate explicit source lists, not inferred recurrences:

- A: 1–3, 5–17.
- B: 1–2, 4–17.
- C: 1, 4–6, 8–15, 17.

| Day | Periods | Course | Weeks | Teacher | Room |
| --- | --- | --- | --- | --- | --- |
| Mon | 3–4 | 工程数学 | A | 宋胜重 | 教三401 |
| Mon | 3–4 | 物联网技术与原理 | 18 | 张懿 | 理5A-306 |
| Mon | 6–7 | 三维造型与工业设计 | 18 | 张哲硕 | 文3-115 |
| Mon | 8–9 | 物联网技术与原理 | A | 郑腾 | 文1-108 |
| Mon | 8–9 | 三维造型与工业设计 | 18 | 张哲硕 | 理5A-410 |
| Tue | 1–2 | 单片机应用技术 | A | 谢浩 | 文3-115 |
| Tue | 3–4 | 单片机应用技术 | A | 谢浩 | 理5A-302 |
| Tue | 6–7 | C++程序设计及上机 | A | 王媛媛 | 文3-211 |
| Tue | 8–9 | C++程序设计及上机 | A | 王媛媛 | 理5A-310 |
| Tue | 10–11 | 会展设计的艺术性 | A | 周烨 | 教七201 |
| Wed | 3–5 | 计算思维与人工智能 | A | 尹琳 | 理4-526 |
| Wed | 6–7 | 工程数学 | A | 宋胜重 | 教三401 |
| Thu | 1–2 | Python程序设计与应用 | B | 田强兴 | 文1-114 |
| Thu | 3–4 | Python程序设计与应用 | B | 田强兴 | 理5A-410 |
| Thu | 6–7 | 科学计算可视化 | B | 陈忠宝 | 文1-114 |
| Thu | 8–9 | 科学计算可视化 | B | 陈忠宝 | 理5A-306 |
| Thu | 10–12 | 可持续旅游与数字创新 | B | KHAN ASIF | 教七106 |
| Fri | 3–4 | 物联网技术与原理 | C | 张懿 | 理5A-306 |
| Fri | 6–7 | 三维造型与工业设计 | C | 张哲硕 | 文3-115 |
| Fri | 8–9 | 三维造型与工业设计 | C | 张哲硕 | 理5A-410 |
| Sat | 3–4 | 物联网技术与原理 | 4 | 张懿 | 理5A-306 |
| Sat | 6–7 | 三维造型与工业设计 | 4 | 张哲硕 | 文3-115 |
| Sat | 8–9 | 三维造型与工业设计 | 4 | 张哲硕 | 理5A-410 |
| Sun | 3–4 | 物联网技术与原理 | 1 | 张懿 | 理5A-306 |
| Sun | 6–7 | 三维造型与工业设计 | 1 | 张哲硕 | 文3-115 |
| Sun | 8–9 | 三维造型与工业设计 | 1 | 张哲硕 | 理5A-410 |

可持续旅游与数字创新 is explicitly an all-English course taught by a foreign instructor. All personal exam arrangements are marked 未安排.

## Presentation and acceptance

Keep the module consistent with the existing Edison sidebar and visual language. Use actual elapsed clock time vertically, making lunch and evening gaps understandable. Adjacent sessions with different rooms remain distinct. Course details may expose teacher, periods, and source notes without crowding the week overview.

Validate from the user's entry point: open Curriculum from the sidebar, inspect the current week, navigate across weeks and semester boundaries, jump to a date, and return to today. Verify ordinary teaching weeks, the two explicit weekend make-up dates, holiday weeks, the final Monday in week 18, room changes between adjacent sessions, and missing spring timetable state. The original PDF must be the comparison source; tests must not simply compare derived data against itself.

Implementation should use the smallest existing application mechanisms that fit this local, read-only module. A generic importer, calendar synchronization, notifications, task manager, and schedule editor are outside this specification.

## Delivery validation

The module uses bundled timetable and calendar data, without a backend dependency or runtime PDF parser. School dates are evaluated in Asia/Shanghai regardless of the computer's timezone. Course details use a native modal with keyboard focus restoration. Both application languages and themes are supported.

- Frontend unit suite: 193 tests passed.
- Complete frontend end-to-end suite: 241 tests passed, including 6 Curriculum scenarios.
- TypeScript checking and production build passed.
- Light, dark, and narrow-window screenshots inspected.
- Independent specification review checked all 26 schedule records against the original PDF. Standards review prompted a contrast correction for today's date and descriptive week-set names.

Spring calendar annotations are available, but the personal spring timetable and individual exam arrangements were not supplied. They are explicitly shown as unknown rather than as free time.
