use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    env,
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::Mutex,
};

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

fn main() {
    let sidecar = SidecarClient::start().expect("Python sidecar startup failed");
    tauri::Builder::default()
        .manage(AppState(Mutex::new(sidecar)))
        .invoke_handler(tauri::generate_handler![
            library_snapshot,
            connection_status,
            subscription_sources,
            configure_connection,
            authorize_connection,
            disconnect_connection,
        ])
        .run(tauri::generate_context!())
        .expect("Tauri application failed");
}
