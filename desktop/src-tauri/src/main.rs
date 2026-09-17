use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    env,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};
use tauri::{Emitter, Manager};

#[derive(Debug, Deserialize, Serialize)]
struct WorkspaceInfo {
    label: String,
    status: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct LibraryCounts {
    inbox: u32,
    to_read: u32,
    reading: u32,
    read: u32,
}

#[derive(Debug, Deserialize, Serialize)]
struct LibrarySnapshot {
    workspace: WorkspaceInfo,
    counts: LibraryCounts,
    inbox: Vec<Value>,
}

#[derive(Debug, Deserialize, Serialize)]
struct ConnectionStatus {
    configured: bool,
    authorized: bool,
    subscription_count: u32,
}

#[derive(Debug, Deserialize, Serialize)]
struct SubscriptionSource {
    channel_id: String,
    title: String,
    description: String,
    thumbnail_url: Option<String>,
    subscribed_at: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
struct SubscriptionSources {
    sources: Vec<SubscriptionSource>,
}

#[derive(Debug, Deserialize, Serialize)]
struct DiscoveryResult {
    discovered: u32,
    scanned_sources: u32,
    truncated: bool,
}

#[derive(Debug, Deserialize, Serialize)]
struct LibraryFilters {
    query: Option<String>,
    include_transcript: Option<bool>,
    reading_state: Option<String>,
    channel_id: Option<String>,
    preparation_state: Option<String>,
    published_after: Option<f64>,
    published_before: Option<f64>,
}

#[derive(Debug, Deserialize, Serialize)]
struct LibraryAsset {
    video_id: String,
    channel_id: String,
    channel_title: String,
    title: String,
    url: String,
    published_at: String,
    preparation_state: String,
    failure_reason: Option<String>,
    reading_state: String,
    manuscript_version: Option<u32>,
    manuscript_path: Option<String>,
    preparation_completed_at: Option<f64>,
    transcript_available: u8,
}

#[derive(Debug, Deserialize, Serialize)]
struct LibraryList {
    assets: Vec<LibraryAsset>,
    total: u32,
}

#[derive(Debug, Deserialize, Serialize)]
struct SourceTrace {
    video_url: String,
    transcript_available: bool,
    transcript_path: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
struct AssetInspection {
    video_id: String,
    channel_id: String,
    channel_title: String,
    title: String,
    url: String,
    published_at: String,
    preparation_state: String,
    failure_reason: Option<String>,
    reading_state: String,
    manuscript_version: Option<u32>,
    manuscript_path: Option<String>,
    preparation_completed_at: Option<f64>,
    transcript_path: Option<String>,
    source_trace: SourceTrace,
}

#[derive(Debug, Deserialize, Serialize)]
struct Document {
    path: String,
    markdown: String,
    version: u32,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct ActivityVolume {
    transcript_characters: u64,
    manuscript_characters: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct ActivityFailure {
    video_id: String,
    title: String,
    state: String,
    reason: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct ActivitySnapshot {
    queued: u32,
    acquiring: u32,
    generating: u32,
    ready: u32,
    unavailable: u32,
    failed: u32,
    drain_paused: bool,
    volume: ActivityVolume,
    cost_estimate: Option<f64>,
    failures: Vec<ActivityFailure>,
}

#[derive(Debug, Deserialize, Serialize)]
struct RetryResult {
    queued: u32,
}

#[derive(Debug, Deserialize, Serialize)]
struct DeletedAsset {
    deleted: String,
}

#[derive(Debug, Deserialize)]
struct SidecarResponse {
    id: u64,
    ok: bool,
    result: Option<Value>,
    error: Option<String>,
}

struct SidecarClient {
    child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
    next_request_id: u64,
}

impl SidecarClient {
    fn start() -> Result<Self, String> {
        let mut child = Command::new(sidecar_binary()?)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .map_err(|error| format!("could not start Python sidecar: {error}"))?;
        let input = child
            .stdin
            .take()
            .ok_or("Python sidecar stdin was unavailable")?;
        let output = child
            .stdout
            .take()
            .ok_or("Python sidecar stdout was unavailable")?;
        Ok(Self {
            child,
            input,
            output: BufReader::new(output),
            next_request_id: 1,
        })
    }

    fn request(&mut self, capability: &str, arguments: Value) -> Result<Value, String> {
        let request_id = self.next_request_id;
        self.next_request_id += 1;
        let request = json!({
            "id": request_id,
            "capability": capability,
            "arguments": arguments,
        });
        writeln!(self.input, "{request}").map_err(|error| error.to_string())?;
        self.input.flush().map_err(|error| error.to_string())?;
        let mut line = String::new();
        self.output
            .read_line(&mut line)
            .map_err(|error| error.to_string())?;
        let response: SidecarResponse =
            serde_json::from_str(&line).map_err(|error| error.to_string())?;
        if response.id != request_id {
            return Err("sidecar response did not match its request".to_owned());
        }
        if !response.ok {
            return Err(response
                .error
                .unwrap_or_else(|| "sidecar request failed".to_owned()));
        }
        response
            .result
            .ok_or_else(|| "sidecar response had no result".to_owned())
    }

    fn library_snapshot(&mut self) -> Result<LibrarySnapshot, String> {
        serde_json::from_value(self.request("library.snapshot", json!({}))?)
            .map_err(|error| error.to_string())
    }

    fn connection_status(&mut self) -> Result<ConnectionStatus, String> {
        serde_json::from_value(self.request("connection.status", json!({}))?)
            .map_err(|error| error.to_string())
    }

    fn subscription_sources(&mut self) -> Result<SubscriptionSources, String> {
        serde_json::from_value(self.request("collection.subscription_sources", json!({}))?)
            .map_err(|error| error.to_string())
    }

    fn refresh_updates(&mut self) -> Result<DiscoveryResult, String> {
        serde_json::from_value(self.request("collection.refresh_updates", json!({}))?)
            .map_err(|error| error.to_string())
    }

    fn backfill_updates(&mut self, days: u32, limit: u32) -> Result<DiscoveryResult, String> {
        serde_json::from_value(self.request(
            "collection.backfill_updates",
            json!({ "days": days, "limit": limit }),
        )?)
        .map_err(|error| error.to_string())
    }

    fn configure_connection(
        &mut self,
        client_id: String,
        client_secret: String,
    ) -> Result<ConnectionStatus, String> {
        serde_json::from_value(self.request(
            "connection.configure",
            json!({ "client_id": client_id, "client_secret": client_secret }),
        )?)
        .map_err(|error| error.to_string())
    }

    fn authorize_connection(&mut self) -> Result<ConnectionStatus, String> {
        serde_json::from_value(self.request("connection.authorize", json!({}))?)
            .map_err(|error| error.to_string())
    }

    fn disconnect_connection(&mut self) -> Result<ConnectionStatus, String> {
        serde_json::from_value(self.request("connection.disconnect", json!({}))?)
            .map_err(|error| error.to_string())
    }

    fn capability<T: DeserializeOwned>(
        &mut self,
        capability: &str,
        arguments: Value,
    ) -> Result<T, String> {
        serde_json::from_value(self.request(capability, arguments)?)
            .map_err(|error| error.to_string())
    }
}

impl Drop for SidecarClient {
    fn drop(&mut self) {
        let _ = self.child.kill();
    }
}

struct AppState(Mutex<SidecarClient>);

fn with_sidecar<T>(
    state: tauri::State<'_, AppState>,
    operation: impl FnOnce(&mut SidecarClient) -> Result<T, String>,
) -> Result<T, String> {
    let mut sidecar = state
        .0
        .lock()
        .map_err(|_| "sidecar lock was poisoned".to_owned())?;
    operation(&mut sidecar)
}

#[tauri::command]
fn library_snapshot(state: tauri::State<'_, AppState>) -> Result<LibrarySnapshot, String> {
    with_sidecar(state, SidecarClient::library_snapshot)
}

#[tauri::command]
fn connection_status(state: tauri::State<'_, AppState>) -> Result<ConnectionStatus, String> {
    with_sidecar(state, SidecarClient::connection_status)
}

#[tauri::command]
fn subscription_sources(state: tauri::State<'_, AppState>) -> Result<SubscriptionSources, String> {
    with_sidecar(state, SidecarClient::subscription_sources)
}

#[tauri::command]
fn collection_refresh_updates(
    state: tauri::State<'_, AppState>,
) -> Result<DiscoveryResult, String> {
    with_sidecar(state, SidecarClient::refresh_updates)
}

#[tauri::command]
fn collection_backfill_updates(
    state: tauri::State<'_, AppState>,
    days: u32,
    limit: u32,
) -> Result<DiscoveryResult, String> {
    with_sidecar(state, |sidecar| sidecar.backfill_updates(days, limit))
}

#[tauri::command]
fn configure_connection(
    state: tauri::State<'_, AppState>,
    client_id: String,
    client_secret: String,
) -> Result<ConnectionStatus, String> {
    with_sidecar(state, |sidecar| {
        sidecar.configure_connection(client_id, client_secret)
    })
}

#[tauri::command]
fn authorize_connection(state: tauri::State<'_, AppState>) -> Result<ConnectionStatus, String> {
    with_sidecar(state, SidecarClient::authorize_connection)
}

#[tauri::command]
fn disconnect_connection(state: tauri::State<'_, AppState>) -> Result<ConnectionStatus, String> {
    with_sidecar(state, SidecarClient::disconnect_connection)
}

#[tauri::command]
fn library_list(
    state: tauri::State<'_, AppState>,
    filters: LibraryFilters,
) -> Result<LibraryList, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability(
            "library.list",
            serde_json::to_value(filters).map_err(|error| error.to_string())?,
        )
    })
}

#[tauri::command]
fn library_inspect(
    state: tauri::State<'_, AppState>,
    video_id: String,
) -> Result<AssetInspection, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability("library.inspect", json!({ "video_id": video_id }))
    })
}

#[tauri::command]
fn library_set_reading_state(
    state: tauri::State<'_, AppState>,
    video_id: String,
    reading_state: String,
) -> Result<AssetInspection, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability(
            "library.set_reading_state",
            json!({ "video_id": video_id, "reading_state": reading_state }),
        )
    })
}

#[tauri::command]
fn library_regenerate(
    state: tauri::State<'_, AppState>,
    video_id: String,
) -> Result<AssetInspection, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability("library.regenerate", json!({ "video_id": video_id }))
    })
}

#[tauri::command]
fn library_delete(
    state: tauri::State<'_, AppState>,
    video_id: String,
) -> Result<DeletedAsset, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability("library.delete", json!({ "video_id": video_id }))
    })
}

#[tauri::command]
fn document_get(state: tauri::State<'_, AppState>, video_id: String) -> Result<Document, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability("documents.get", json!({ "video_id": video_id }))
    })
}

#[tauri::command]
fn document_open(state: tauri::State<'_, AppState>, video_id: String) -> Result<(), String> {
    let document: Document = with_sidecar(state, |sidecar| {
        sidecar.capability("documents.get", json!({ "video_id": video_id }))
    })?;
    Command::new("open")
        .arg(document.path)
        .spawn()
        .map_err(|error| error.to_string())?;
    Ok(())
}

#[tauri::command]
fn activity_snapshot(state: tauri::State<'_, AppState>) -> Result<ActivitySnapshot, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability("activity.snapshot", json!({}))
    })
}

#[tauri::command]
fn activity_drain_pause(state: tauri::State<'_, AppState>) -> Result<ActivitySnapshot, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability("activity.drain_pause", json!({}))
    })
}

#[tauri::command]
fn activity_resume(state: tauri::State<'_, AppState>) -> Result<ActivitySnapshot, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability("activity.resume", json!({}))
    })
}

#[tauri::command]
fn activity_retry_all_failed(state: tauri::State<'_, AppState>) -> Result<RetryResult, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability("activity.retry_all_failed", json!({}))
    })
}

#[tauri::command]
fn activity_retry(
    state: tauri::State<'_, AppState>,
    video_id: String,
) -> Result<RetryResult, String> {
    with_sidecar(state, |sidecar| {
        sidecar.capability("activity.retry", json!({ "video_id": video_id }))
    })
}

fn sidecar_binary() -> Result<PathBuf, String> {
    let bundled = env::current_exe()
        .map_err(|error| error.to_string())?
        .parent()
        .map(|directory| directory.join("youtube-workbench-sidecar"))
        .ok_or_else(|| "could not locate the bundled Python sidecar".to_owned())?;
    if bundled.exists() {
        return Ok(bundled);
    }

    let development = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("binaries")
        .join("youtube-workbench-sidecar-aarch64-apple-darwin");
    if development.exists() {
        Ok(development)
    } else {
        Err(format!(
            "Python sidecar binary is missing: {}",
            development.display()
        ))
    }
}

fn stream_activity(app: tauri::AppHandle) {
    thread::spawn(move || loop {
        thread::sleep(Duration::from_secs(1));
        let snapshot = {
            let state = app.state::<AppState>();
            let result = match state.0.lock() {
                Ok(mut sidecar) => {
                    sidecar.capability::<ActivitySnapshot>("activity.snapshot", json!({}))
                }
                Err(_) => Err("sidecar lock was poisoned".to_owned()),
            };
            result
        };
        if let Ok(snapshot) = snapshot {
            let _ = app.emit("activity-snapshot", snapshot);
        }
    });
}

fn main() {
    let sidecar = SidecarClient::start().expect("Python sidecar startup failed");
    tauri::Builder::default()
        .manage(AppState(Mutex::new(sidecar)))
        .setup(|app| {
            stream_activity(app.handle().clone());
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            library_snapshot,
            connection_status,
            subscription_sources,
            collection_refresh_updates,
            collection_backfill_updates,
            configure_connection,
            authorize_connection,
            disconnect_connection,
            library_list,
            library_inspect,
            library_set_reading_state,
            library_regenerate,
            library_delete,
            document_get,
            document_open,
            activity_snapshot,
            activity_drain_pause,
            activity_resume,
            activity_retry_all_failed,
            activity_retry,
        ])
        .run(tauri::generate_context!())
        .expect("Tauri application failed");
}
