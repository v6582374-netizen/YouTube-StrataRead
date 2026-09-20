import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Icon } from "../Icon";
import type { Occurrence } from "./timetable";

export function CourseDetails({ course, onClose }: { course: Occurrence; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    dialog.showModal();
    return () => { dialog.close(); previous?.focus(); };
  }, []);
  const date = new Intl.DateTimeFormat(i18n.language.startsWith("zh") ? "zh-CN" : "en-GB", {
    timeZone: "UTC", year: "numeric", month: "long", day: "numeric", weekday: "long",
  }).format(new Date(`${course.date}T00:00:00Z`));

  return (
    <dialog ref={ref} className="curriculum-details" aria-labelledby="curriculum-course-title" onCancel={event => { event.preventDefault(); onClose(); }}>
      <header>
        <span>{t("curriculum.course_details")}</span>
        <button type="button" aria-label={t("curriculum.close")} onClick={onClose}><Icon name="x" size={18} /></button>
      </header>
      <h2 id="curriculum-course-title">{course.name}</h2>
      <p className="curriculum-details-date">{date}</p>
      <dl>
        <dt>{t("curriculum.class_time")}</dt><dd>{course.start}–{course.end}<small>{t("curriculum.period_range", { first: course.first, last: course.last })}</small></dd>
        <dt>{t("curriculum.classroom")}</dt><dd>{course.room}</dd>
        <dt>{t("curriculum.teacher")}</dt><dd>{course.teacher}</dd>
      </dl>
      {course.course === "tourism" && <p className="curriculum-details-note">{t("curriculum.english_instruction")}</p>}
      <footer>{t("curriculum.university")} · {t("curriculum.timezone")}</footer>
    </dialog>
  );
}
