#[path = "../src/curriculum_notifications.rs"]
mod curriculum_notifications;

use curriculum_notifications::Notifications;

fn timestamp(value: &str) -> i64 {
    chrono::DateTime::parse_from_rfc3339(value).unwrap().timestamp_millis()
}

#[test]
fn each_numbered_period_has_its_own_start_and_end() {
    let path = std::env::temp_dir().join(format!("edison-notification-test-{}.json", uuid::Uuid::new_v4()));
    let mut notifications = Notifications::new(path.clone(), timestamp("2026-09-15T07:59:59+08:00")).unwrap();
    for (time, period, boundary) in [
        ("08:00:00", 1, "start"), ("08:45:00", 1, "end"),
        ("08:50:00", 2, "start"), ("09:35:00", 2, "end"),
    ] {
        let due = timestamp(&format!("2026-09-15T{time}+08:00"));
        // Advance through idle time before crossing this boundary, as an awake app does.
        notifications.advance(due - 1_000, true).unwrap();
        let events = notifications.advance(due, true).unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].course, "单片机应用技术");
        assert_eq!(events[0].period, period);
        assert_eq!(events[0].boundary, boundary);
        assert_eq!(events[0].room, "文3-115");
        assert!(notifications.advance(due + 500, true).unwrap().is_empty());
    }
    let _ = std::fs::remove_file(path);
}

#[test]
fn wake_and_restart_skip_expired_boundaries_and_do_not_repeat_delivered_ones() {
    let path = std::env::temp_dir().join(format!("edison-notification-test-{}.json", uuid::Uuid::new_v4()));
    let before = timestamp("2026-09-15T07:59:59+08:00");
    let mut service = Notifications::new(path.clone(), before).unwrap();
    assert_eq!(service.advance(before + 1_000, true).unwrap().len(), 1);
    // A clock rollback plus restart must not repeat the previously delivered start.
    let mut restarted = Notifications::new(path.clone(), before).unwrap();
    assert!(restarted.advance(before + 1_000, true).unwrap().is_empty());
    // Wake at 08:51: neither the 08:45 end nor the 08:50 start is replayed.
    assert!(restarted.advance(timestamp("2026-09-15T08:51:00+08:00"), true).unwrap().is_empty());
    restarted.advance(timestamp("2026-09-15T09:34:59+08:00"), true).unwrap();
    let next = restarted.advance(timestamp("2026-09-15T09:35:00+08:00"), true).unwrap();
    assert_eq!(next.len(), 1);
    assert_eq!(next[0].period, 2);
    assert_eq!(next[0].boundary, "end");
    let _ = std::fs::remove_file(path);
}

#[test]
fn off_preference_and_permission_prompt_marker_survive_restart() {
    let path = std::env::temp_dir().join(format!("edison-notification-test-{}.json", uuid::Uuid::new_v4()));
    let before = timestamp("2026-09-15T07:59:59+08:00");
    let mut service = Notifications::new(path.clone(), before).unwrap();
    assert!(service.enabled());
    assert!(service.should_request_permission());
    service.mark_permission_requested().unwrap();
    service.set_enabled(false, before).unwrap();
    let mut restarted = Notifications::new(path.clone(), before).unwrap();
    assert!(!restarted.enabled());
    assert!(!restarted.should_request_permission());
    assert!(restarted.advance(before + 1_000, true).unwrap().is_empty());
    restarted.set_enabled(true, before + 2_000).unwrap();
    assert!(!restarted.should_request_permission());
    assert!(restarted.advance(before + 2_500, true).unwrap().is_empty());
    let _ = std::fs::remove_file(path);
}

#[test]
fn missing_permission_suppresses_delivery_without_changing_the_enabled_preference() {
    let path = std::env::temp_dir().join(format!("edison-notification-test-{}.json", uuid::Uuid::new_v4()));
    let before = timestamp("2026-09-15T07:59:59+08:00");
    let mut service = Notifications::new(path.clone(), before).unwrap();
    assert!(service.advance(before + 1_000, false).unwrap().is_empty());
    assert!(service.enabled());
    assert!(service.advance(before + 2_000, true).unwrap().is_empty());
}

#[test]
fn makeups_follow_the_pdf_while_holidays_and_missing_spring_data_are_silent() {
    for (date, expected) in [
        ("2026-09-20", 1), ("2026-09-25", 0), ("2026-10-01", 0),
        ("2026-10-10", 1), ("2026-10-30", 0), ("2027-01-01", 0),
        ("2027-01-11", 1), ("2027-03-01", 0),
    ] {
        let path = std::env::temp_dir().join(format!("edison-notification-test-{}.json", uuid::Uuid::new_v4()));
        let due = timestamp(&format!("{date}T09:50:00+08:00"));
        let mut service = Notifications::new(path.clone(), due - 1_000).unwrap();
        let events = service.advance(due, true).unwrap();
        assert_eq!(events.len(), expected, "{date}");
        if expected > 0 {
            assert_eq!(events[0].course, "物联网技术与原理");
            assert_eq!(events[0].room, "理5A-306");
        }
        let _ = std::fs::remove_file(path);
    }
}
