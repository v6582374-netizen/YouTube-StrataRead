fn main() {
    // tauri-build validates every `bundle.resources` path on every build, dev included, but
    // `binaries/sidecar` is only staged by the release scripts and `/binaries` is gitignored —
    // so a fresh checkout died on `resource path 'binaries/sidecar' doesn't exist`. Dev needs no
    // packaged server (`server_bin()` falls back to the venv) and empty resource dirs are
    // skipped, so a placeholder is enough.
    std::fs::create_dir_all("binaries/sidecar").expect("create the sidecar resource dir");

    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        cc::Build::new()
            .file("src/course_notifications.m")
            .flag("-fobjc-arc")
            .flag("-fblocks")
            .compile("edison_course_notifications");
        println!("cargo:rustc-link-lib=framework=Foundation");
        println!("cargo:rustc-link-lib=framework=AppKit");
        println!("cargo:rustc-link-lib=framework=UserNotifications");
        println!("cargo:rerun-if-changed=src/course_notifications.m");
    }
    println!("cargo:rerun-if-changed=../src/components/curriculum/timetable-data.json");
    tauri_build::build()
}
