//! Course boundaries and durable preferences shared by the native worker and its tests.
//! The UI never owns the clock. Source data is the same JSON used by Curriculum.
use chrono::{Duration, NaiveDate, NaiveTime};
use serde::{Deserialize, Serialize};
use std::{collections::HashMap, path::PathBuf};

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct Timetable {
    semester_start: String,
    periods: Vec<[String; 2]>,
    courses: HashMap<String, Course>,
    schedule: Vec<Slot>,
}
#[derive(Deserialize)]
struct Course { name: String }
#[derive(Deserialize)]
struct Slot {
    course: String, day: i64, first: usize, last: usize,
    weeks: Vec<i64>, room: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ClassEvent {
    pub id: String,
    pub at: i64,
    pub course: String,
    pub period: usize,
    pub boundary: String,
    pub time: String,
    pub room: String,
}

fn events() -> Result<Vec<ClassEvent>, String> {
    let timetable: Timetable = serde_json::from_str(include_str!("../../src/components/curriculum/timetable-data.json")).map_err(|e| e.to_string())?;
    let start = NaiveDate::parse_from_str(&timetable.semester_start, "%Y-%m-%d").map_err(|e| e.to_string())?;
    let mut events = Vec::new();
    for slot in timetable.schedule {
        if !(1..=7).contains(&slot.day) || slot.first == 0 || slot.last < slot.first || slot.last > timetable.periods.len() {
            return Err("Invalid course period range".into());
        }
        let course = timetable.courses.get(&slot.course).ok_or("Unknown course")?;
        for week in slot.weeks {
            if week < 1 { return Err("Invalid teaching week".into()); }
            let date = start + Duration::days((week - 1) * 7 + slot.day - 1);
            for period in slot.first..=slot.last {
                for (index, boundary) in ["start", "end"].iter().enumerate() {
                    let clock = &timetable.periods[period - 1][index];
                    let time = NaiveTime::parse_from_str(clock, "%H:%M").map_err(|e| e.to_string())?;
                    // These dates are in contemporary Asia/Shanghai (UTC+8, no DST).
                    let at = date.and_time(time).and_utc().timestamp_millis() - 8 * 3_600_000;
                    events.push(ClassEvent {
                        id: format!("curriculum-{date}-{}-{period}-{boundary}", slot.course),
                        at, course: course.name.clone(), period, boundary: boundary.to_string(),
                        time: clock.clone(), room: slot.room.clone(),
                    });
                }
            }
        }
    }
    events.sort_by_key(|event| event.at);
    Ok(events)
}

fn enabled_by_default() -> bool { true }
#[derive(Clone, Serialize, Deserialize)]
struct Preferences {
    #[serde(default = "enabled_by_default")]
    enabled: bool,
    #[serde(default)]
    prompted: bool,
    #[serde(default)]
    last_boundary: i64,
}

pub struct Notifications {
    path: PathBuf,
    preferences: Preferences,
    events: Vec<ClassEvent>,
    last_tick: i64,
}

impl Notifications {
    pub fn new(path: PathBuf, now: i64) -> Result<Self, String> {
        let preferences = match std::fs::read(&path) {
            Ok(bytes) => serde_json::from_slice(&bytes).map_err(|e| e.to_string())?,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Preferences { enabled: true, prompted: false, last_boundary: 0 },
            Err(e) => return Err(e.to_string()),
        };
        Ok(Self { path, preferences, events: events()?, last_tick: now })
    }

    pub fn enabled(&self) -> bool { self.preferences.enabled }
    pub fn should_request_permission(&self) -> bool { self.enabled() && !self.preferences.prompted }

    fn save(&mut self, next: Preferences) -> Result<(), String> {
        if let Some(parent) = self.path.parent() { std::fs::create_dir_all(parent).map_err(|e| e.to_string())?; }
        let temporary = self.path.with_extension("tmp");
        std::fs::write(&temporary, serde_json::to_vec(&next).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        std::fs::rename(&temporary, &self.path).map_err(|e| e.to_string())?;
        self.preferences = next;
        Ok(())
    }

    pub fn mark_permission_requested(&mut self) -> Result<(), String> {
        let mut next = self.preferences.clone(); next.prompted = true; self.save(next)
    }

    pub fn set_enabled(&mut self, enabled: bool, now: i64) -> Result<(), String> {
        let mut next = self.preferences.clone(); next.enabled = enabled; self.save(next)?;
        self.last_tick = now;
        Ok(())
    }

    /// A normal awake tick may cross a boundary by a fraction of a second. A gap
    /// longer than 3s is a suspended/delayed worker, not a queue to replay on wake.
    pub fn advance(&mut self, now: i64, permitted: bool) -> Result<Vec<ClassEvent>, String> {
        let previous = self.last_tick;
        self.last_tick = now;
        if !self.enabled() || !permitted || !(0..=3_000).contains(&(now - previous)) { return Ok(vec![]); }
        let due: Vec<_> = self.events.iter().filter(|event| {
            event.at > previous && event.at <= now && now - event.at <= 1_500 && event.at > self.preferences.last_boundary
        }).cloned().collect();
        if let Some(last) = due.last() {
            // Claim before delivery: a crash or restart must not repeat an alert.
            let mut next = self.preferences.clone(); next.last_boundary = last.at; self.save(next)?;
        }
        Ok(due)
    }
}
