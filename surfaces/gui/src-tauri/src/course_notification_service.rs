use super::{course_notification_platform as platform, curriculum_notifications::Notifications};
use serde::Serialize;
use std::{path::PathBuf, sync::{atomic::{AtomicBool, Ordering}, Arc, Mutex}, time::{Duration, Instant, SystemTime, UNIX_EPOCH}};

fn now() -> i64 { SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis() as i64 }

#[derive(Clone, Serialize)]
pub struct NotificationStatus {
    enabled: bool,
    permission: String,
    error: Option<String>,
}
struct Inner {
    notifications: Option<Notifications>,
    permission: String,
    error: Option<String>,
}
pub struct CourseNotificationService {
    inner: Mutex<Inner>,
    clock: fn() -> i64,
    stopped: AtomicBool,
    refresh: AtomicBool,
}

impl CourseNotificationService {
    pub fn start(path: PathBuf) -> Arc<Self> {
        Self::start_with_clock(path, now)
    }

    fn start_with_clock(path: PathBuf, clock: fn() -> i64) -> Arc<Self> {
        let result = Notifications::new(path, clock());
        let error = result.as_ref().err().cloned();
        let service = Arc::new(Self {
            inner: Mutex::new(Inner { notifications: result.ok(), permission: "checking".into(), error }),
            clock,
            stopped: AtomicBool::new(false), refresh: AtomicBool::new(true),
        });
        let worker = service.clone();
        std::thread::spawn(move || worker.run());
        service
    }

    pub fn stop(&self) { self.stopped.store(true, Ordering::SeqCst); }

    fn status(&self) -> NotificationStatus {
        let inner = self.inner.lock().unwrap();
        NotificationStatus {
            enabled: inner.notifications.as_ref().map(|n| n.enabled()).unwrap_or(true),
            permission: inner.permission.clone(), error: inner.error.clone(),
        }
    }

    fn set_enabled(&self, enabled: bool) -> Result<NotificationStatus, String> {
        {
            let mut inner = self.inner.lock().unwrap();
            inner.notifications.as_mut().ok_or("Notification preferences unavailable")?.set_enabled(enabled, (self.clock)())?;
            inner.error = None;
        }
        self.refresh.store(true, Ordering::SeqCst);
        Ok(self.status())
    }

    fn run(&self) {
        let mut last_check = Instant::now();
        while !self.stopped.load(Ordering::SeqCst) {
            let requesting = self.inner.lock().unwrap().permission == "requesting";
            if self.refresh.swap(false, Ordering::SeqCst) || last_check.elapsed() >= Duration::from_secs(if requesting { 1 } else { 30 }) {
                let permission = platform::permission();
                let mut inner = self.inner.lock().unwrap();
                inner.permission = permission.into();
                if permission == "not_determined" {
                    if let Some(notifications) = inner.notifications.as_mut() {
                        if notifications.should_request_permission() {
                            match notifications.mark_permission_requested() {
                                Ok(()) => { platform::request_permission(); inner.permission = "requesting".into(); }
                                Err(error) => inner.error = Some(error),
                            }
                        }
                    }
                }
                last_check = Instant::now();
            }
            {
                let mut inner = self.inner.lock().unwrap();
                let permitted = inner.permission == "granted";
                if let Some(notifications) = inner.notifications.as_mut() {
                    match notifications.advance((self.clock)(), permitted) {
                        Ok(events) => for event in events {
                            if self.stopped.load(Ordering::SeqCst) { break; }
                            // Held through immediate delivery: disabling cannot return while
                            // an old enabled snapshot still has an alert waiting to be sent.
                            match platform::deliver(&event) {
                                Ok(()) => inner.error = None,
                                Err(error) => { inner.error = Some(error); self.refresh.store(true, Ordering::SeqCst); }
                            }
                        },
                        Err(error) => inner.error = Some(error),
                    }
                }
            }
            std::thread::sleep(Duration::from_millis(500));
        }
    }
}

#[tauri::command]
pub async fn get_course_notification_status(service: tauri::State<'_, Arc<CourseNotificationService>>) -> Result<NotificationStatus, String> {
    let service = service.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        service.refresh.store(true, Ordering::SeqCst);
        service.status()
    }).await.map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn set_course_notifications_enabled(service: tauri::State<'_, Arc<CourseNotificationService>>, enabled: bool) -> Result<NotificationStatus, String> {
    let service = service.inner().clone();
    tauri::async_runtime::spawn_blocking(move || service.set_enabled(enabled)).await.map_err(|e| e.to_string())?
}
