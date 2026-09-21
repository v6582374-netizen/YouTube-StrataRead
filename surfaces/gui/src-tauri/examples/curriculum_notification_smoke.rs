//! Run from a temporary .app bundle, not as an unbundled executable.
//! The smoke sends four notifications under the isolated test bundle identity through the real macOS API.
extern crate openworker_desktop_lib; // Carry the host build script's native framework linkage.
#[allow(dead_code)]
#[path = "../src/curriculum_notifications.rs"]
mod curriculum_notifications;
#[allow(dead_code)]
#[path = "../src/course_notification_platform.rs"]
mod course_notification_platform;

#[cfg(target_os = "macos")]
extern "C" { fn edison_course_smoke_pump(); }

fn main() {
    use std::sync::{atomic::{AtomicBool, Ordering}, Arc};
    #[cfg(target_os = "macos")]
    unsafe { edison_course_smoke_pump(); }
    let done = Arc::new(AtomicBool::new(false));
    let finished = done.clone();
    let worker = std::thread::spawn(move || {
        let result = verify();
        match &result {
            Ok(count) => println!("{}", serde_json::json!({"ok": true, "accepted": 4, "delivered": count})),
            Err(error) => println!("{}", serde_json::json!({"ok": false, "error": error})),
        }
        finished.store(true, Ordering::SeqCst);
        result
    });
    while !done.load(Ordering::SeqCst) {
        #[cfg(target_os = "macos")]
        unsafe { edison_course_smoke_pump(); }
        #[cfg(not(target_os = "macos"))]
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    if worker.join().unwrap().is_err() { std::process::exit(1); }
}

// Include the real service so this harness exercises its thread, permission flow,
// persistence, and delivery lock. Only its clock is controlled here.
#[allow(dead_code)]
mod course_notification_service {
    include!("../src/course_notification_service.rs");
    use std::sync::atomic::AtomicI64;
    static CLOCK: AtomicI64 = AtomicI64::new(0);
    fn controlled_now() -> i64 { CLOCK.load(Ordering::SeqCst) }
    pub fn verify() -> Result<i32, String> {
        use std::thread::sleep;
        let timestamp = |s: &str| chrono::DateTime::parse_from_rfc3339(s).unwrap().timestamp_millis();
        let initial_time = timestamp("2026-09-15T07:59:59+08:00");
        CLOCK.store(initial_time, Ordering::SeqCst);
        let path = std::env::temp_dir().join(format!("edison-notification-smoke-{}.json", uuid::Uuid::new_v4()));
        let service = CourseNotificationService::start_with_clock(path.clone(), controlled_now);
        let result = (|| {
            for _ in 0..60 {
                match service.status().permission.as_str() {
                    "granted" => break,
                    "denied" | "unsupported" | "unavailable" => return Err(format!("Permission: {}", service.status().permission)),
                    _ => sleep(Duration::from_secs(1)),
                }
            }
            if service.status().permission != "granted" { return Err("Permission was not granted within 60s".into()); }
            let initial = platform::delivered_count();
            if initial < 0 { return Err("Cannot query Notification Center".into()); }
            for time in ["08:00:00", "08:45:00", "08:50:00", "09:35:00"] {
                let due = timestamp(&format!("2026-09-15T{time}+08:00"));
                CLOCK.store(due - 1_000, Ordering::SeqCst);
                sleep(Duration::from_millis(800));
                CLOCK.store(due, Ordering::SeqCst);
                sleep(Duration::from_millis(1_200));
            }
            let delivered = platform::delivered_count() - initial;
            if delivered != 4 { return Err(format!("Expected four OS deliveries, observed {delivered}")); }
            service.set_enabled(false)?;
            // A future scheduled boundary must not deliver while disabled.
            let next = timestamp("2026-09-15T09:50:00+08:00");
            CLOCK.store(next - 1_000, Ordering::SeqCst);
            sleep(Duration::from_millis(800));
            CLOCK.store(next, Ordering::SeqCst);
            sleep(Duration::from_millis(1_200));
            if platform::delivered_count() - initial != 4 { return Err("Disabled service delivered a notification".into()); }
            service.stop();
            let restarted = CourseNotificationService::start_with_clock(path.clone(), controlled_now);
            if restarted.status().enabled { return Err("Off choice did not survive restart".into()); }
            restarted.set_enabled(true)?;
            restarted.stop();
            CLOCK.store(timestamp("2026-09-15T10:34:59+08:00"), Ordering::SeqCst);
            sleep(Duration::from_millis(800));
            CLOCK.store(timestamp("2026-09-15T10:35:00+08:00"), Ordering::SeqCst);
            sleep(Duration::from_millis(1_200));
            if platform::delivered_count() - initial != 4 { return Err("Stopped service delivered a notification".into()); }
            Ok(delivered)
        })();
        service.stop();
        let _ = std::fs::remove_file(path);
        result
    }
}
fn verify() -> Result<i32, String> { course_notification_service::verify() }
