# Curriculum system notifications

Status: implemented; automated and native service validation passed. Packaged-window interaction validation remains limited by macOS Accessibility access.

## Intent

Notify the person through the operating system at the start and end of scheduled classes. This extends the initial Curriculum release, whose specification explicitly excluded notifications. The earlier exclusions of personal tasks and schedule editing remain in force.

The current deployment is the Edison macOS desktop application. Notifications must refer to real personal course occurrences, including the existing holiday and make-up arrangements. Unknown spring courses and individual exam times are not notification sources.

## Confirmed decisions

The user accepted all four recommendations on 2026-09-21:

- Unit: every numbered class period has its own start and end notification. A periods 1–2 course produces notifications at 08:00, 08:45, 08:50, and 09:35; a combined course card does not collapse these boundaries. Notifications occur at the scheduled times, without advance reminders.
- Runtime: notifications operate while Edison is running, including a hidden window or a different selected module. An explicit Quit stops reminders; delivery after Quit is outside scope.
- Recovery: do not replay expired boundaries after waking the computer or reopening Edison. Resume upcoming reminders only.
- Sound: use the system's standard notification sound and respect OS notification preferences and focus settings. No custom ringtone system.
- Activation: one persistent “Class notifications” toggle in Curriculum, **on by default**. The user's explicit off choice survives restarts. The toggle controls all start/end reminders, without per-course configuration.
- Notification click: no custom navigation or forced activation of Edison. Leave click behavior to the operating system; there is no requirement to open Curriculum or select the notification's date. Merely delivering a notification must never change the person's view.

## Permission and presentation

Default-on expresses the person's reminder preference; it does not bypass macOS permission. Request permission when the notification-enabled application first runs, without requiring a visit to Curriculum. A denied or unavailable permission must be visibly distinguished from working reminders, without repeated permission prompts. Keep the enabled preference separate from permission availability so the toggle never falsely claims that delivery is operational.

Notification text identifies the course, numbered period, start/end event, scheduled time, and classroom using existing timetable data. A combined card is still shown as one occurrence in the weekly view; notification granularity does not change the timetable layout.

## Acceptance scenarios

- With permission granted and the default preference enabled, a periods 1–2 occurrence produces one notification at each of 08:00, 08:45, 08:50, and 09:35 in Asia/Shanghai. Do not also emit duplicate card-level reminders.
- Changing modules or hiding the window does not interrupt upcoming notifications. No notification forcibly changes the active page or activates the app.
- Turning the toggle off stops upcoming reminders. The choice remains off after a restart.
- Denying OS permission produces an accurate unavailable status rather than silently claiming reminders are working, and does not create repeated permission prompts.
- Reopening or waking after past class boundaries produces no catch-up burst. Upcoming boundaries are still delivered once; re-rendering, switching pages, and restarting do not duplicate notifications.
- Notifications use actual personal timetable occurrences, including explicit weekend make-ups. Dates without scheduled personal courses produce no reminders. Missing spring timetable data and unknown personal exams never produce inferred reminders.
- Sound follows OS preferences and focus settings. Clicking the notification has no app-specific navigation requirement.

Validate through the packaged macOS application's notification controls and native delivery, including hidden-window operation; browser-only toast tests are insufficient. Tests may use controlled times around boundaries, with expected events taken from the provided timetable and period clock rather than recomputed from implementation.

## Existing lifecycle fact

The current native shell hides its window on CloseRequested and keeps running. It also exposes a separate Quit menu action. Closing the window and quitting the application therefore need distinct language in the product agreement.

## Implementation and validation (2026-09-21)

The React weekly view and native scheduler consume the same personal timetable JSON. A native worker owns the clock and sends immediate UserNotifications requests; there is no future OS queue to outlive Quit. Preferences and the permission-prompt marker persist separately from OS authorization. Local macOS bundles receive an ad-hoc bundle signature with the Edison identifier.

Validation:

- Frontend unit suite: 206 passed. Full browser E2E: 242 passed, one Board interaction timed out; the complete Board file passed all 7 scenarios on targeted rerun. Curriculum and notification scenarios all passed.
- Native Cargo test suite passed, including five scheduling/persistence tests. Production frontend and signed application bundle built successfully.
- The isolated native smoke bundle ran the production service thread with a controlled clock and real macOS notification APIs. Notification Center confirmed four delivered notifications at the period 1–2 boundaries. Turning off suppressed the next actual boundary, the off preference survived service restart, and stopping the service suppressed a later boundary. The harness has no visible application window.
- Actual Edison was rebuilt with its proper bundle identity and reopened. macOS accepted its identity and presented the startup notification-permission request without visiting Curriculum; the enabled preference was true. System Events UI automation was denied Accessibility access, so the packaged app's switch interaction, hidden-window delivery at an actual boundary, and Quit interaction have not been claimed as fully exercised desktop E2E scenarios. Browser tests verify the switch contract; the native harness verifies the worker and OS delivery separately.

Native smoke reproduction: build `cargo build --manifest-path surfaces/gui/src-tauri/Cargo.toml --example curriculum_notification_smoke`; place the resulting executable in a dedicated macOS app bundle with its own identifier and `CFBundleExecutable`; ad-hoc sign it, register it with LaunchServices, and launch it from `~/Applications`. Running from a temporary directory failed macOS client validation. The harness clears only that dedicated test app's delivered notifications at startup and checks actual Notification Center delivery, not API acceptance alone.
