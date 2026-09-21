use super::curriculum_notifications::ClassEvent;

#[cfg(target_os = "macos")]
extern "C" {
    fn edison_course_permission() -> i32;
    fn edison_course_request_permission();
    fn edison_course_notify(id: *const std::ffi::c_char, title: *const std::ffi::c_char, body: *const std::ffi::c_char) -> bool;
    fn edison_course_delivered_count() -> i32;
}

pub fn permission() -> &'static str {
    #[cfg(target_os = "macos")]
    { match unsafe { edison_course_permission() } {
        0 => "not_determined", 1 => "denied", 2..=4 => "granted", 10 => "requesting",
        -2 => "unsupported", _ => "unavailable",
    } }
    #[cfg(not(target_os = "macos"))]
    { "unsupported" }
}

pub fn request_permission() {
    #[cfg(target_os = "macos")]
    unsafe { edison_course_request_permission() };
}

pub fn deliver(event: &ClassEvent) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        use std::ffi::CString;
        let title = format!("{}｜{}", if event.boundary == "start" { "上课提醒" } else { "下课提醒" }, event.course);
        let body = format!("第 {} 节 · {} · {}", event.period, event.time, event.room);
        let id = CString::new(event.id.as_str()).map_err(|e| e.to_string())?;
        let title = CString::new(title).map_err(|e| e.to_string())?;
        let body = CString::new(body).map_err(|e| e.to_string())?;
        if unsafe { edison_course_notify(id.as_ptr(), title.as_ptr(), body.as_ptr()) } { Ok(()) }
        else { Err("Native notification delivery failed".into()) }
    }
    #[cfg(not(target_os = "macos"))]
    { let _ = event; Err("Notifications require macOS".into()) }
}

#[allow(dead_code)]
pub fn delivered_count() -> i32 {
    #[cfg(target_os = "macos")]
    { unsafe { edison_course_delivered_count() } }
    #[cfg(not(target_os = "macos"))]
    { -1 }
}
