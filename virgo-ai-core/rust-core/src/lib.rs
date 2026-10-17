//! Minimal Rust/Python boundary verification for Virgo AI.

use pyo3::prelude::*;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::ffi::OsStrExt;

#[cfg(windows)]
#[link(name = "Kernel32")]
unsafe extern "system" {
    fn MoveFileExW(existing_file_name: *const u16, new_file_name: *const u16, flags: u32) -> i32;
}

#[cfg(windows)]
const MOVEFILE_REPLACE_EXISTING: u32 = 0x1;
#[cfg(windows)]
const MOVEFILE_WRITE_THROUGH: u32 = 0x8;

const READY_STATUS: &str = "virgo-rust-core-ready";

/// Return the deterministic Step 3 Rust-core readiness contract.
#[must_use]
pub const fn rust_core_status_value() -> &'static str {
    READY_STATUS
}

/// Expose the deterministic Rust-core readiness contract to Python.
#[pyfunction]
fn rust_core_status() -> &'static str {
    rust_core_status_value()
}

/// Canonicalize an existing workspace-relative path and enforce containment.
#[pyfunction]
fn validate_workspace_path(workspace_root: &str, relative_path: &str) -> PyResult<String> {
    validate_workspace_path_value(workspace_root, relative_path)
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

fn contained_target(
    workspace_root: &str,
    relative_path: &str,
) -> Result<(PathBuf, PathBuf), String> {
    let candidate = Path::new(relative_path);
    if candidate.as_os_str().is_empty()
        || candidate.is_absolute()
        || candidate
            .components()
            .any(|part| matches!(part, Component::ParentDir | Component::Prefix(_)))
    {
        return Err("workspace path must be a contained relative path".to_owned());
    }
    let root = PathBuf::from(workspace_root)
        .canonicalize()
        .map_err(|error| format!("workspace root is unavailable: {error}"))?;
    if !root.is_dir() {
        return Err("workspace root must be a directory".to_owned());
    }
    let target = root.join(candidate);
    let parent = target
        .parent()
        .ok_or_else(|| "workspace target has no parent".to_owned())?;
    let resolved_parent = parent
        .canonicalize()
        .map_err(|error| format!("workspace target parent is unavailable: {error}"))?;
    if !resolved_parent.starts_with(&root) {
        return Err("workspace path escapes the selected root".to_owned());
    }
    if target.exists() {
        let resolved = target
            .canonicalize()
            .map_err(|error| format!("workspace path is unavailable: {error}"))?;
        if !resolved.starts_with(&root) {
            return Err("workspace path escapes the selected root".to_owned());
        }
        Ok((root, resolved))
    } else {
        let name = target
            .file_name()
            .ok_or_else(|| "workspace target must name a file".to_owned())?;
        Ok((root, resolved_parent.join(name)))
    }
}

fn hex_digest(bytes: &[u8]) -> String {
    // FNV-1a is used only as an internal staging check; Python records SHA-256.
    let mut value: u64 = 0xcbf29ce484222325;
    for byte in bytes {
        value ^= u64::from(*byte);
        value = value.wrapping_mul(0x100000001b3);
    }
    format!("{value:016x}")
}

fn backup_target(backup_root: &str, operation_id: &str) -> Result<PathBuf, String> {
    if operation_id.is_empty()
        || !operation_id
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '-')
    {
        return Err("operation identifier is invalid".to_owned());
    }
    let root = PathBuf::from(backup_root)
        .canonicalize()
        .map_err(|error| format!("backup root is unavailable: {error}"))?;
    if !root.is_dir() {
        return Err("backup root must be a directory".to_owned());
    }
    Ok(root.join(format!("{operation_id}.bak")))
}

fn stage_bytes(target: &Path, bytes: &[u8], operation_id: &str) -> Result<PathBuf, String> {
    let name = target
        .file_name()
        .ok_or_else(|| "workspace target must name a file".to_owned())?
        .to_string_lossy();
    let temporary = target.with_file_name(format!(".{name}.virgo-{operation_id}.tmp"));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)
        .map_err(|error| format!("temporary file could not be created: {error}"))?;
    if let Err(error) = file.write_all(bytes).and_then(|()| file.sync_all()) {
        let _ = fs::remove_file(&temporary);
        return Err(format!("temporary file could not be flushed: {error}"));
    }
    Ok(temporary)
}

fn install_staged(target: &Path, temporary: &Path, backup: Option<&Path>) -> Result<(), String> {
    if let Err(error) = atomic_replace(temporary, target) {
        if let Some(backup_path) = backup {
            let _ = fs::copy(backup_path, target);
        }
        let _ = fs::remove_file(temporary);
        return Err(error);
    }
    Ok(())
}

#[cfg(not(windows))]
fn atomic_replace(temporary: &Path, target: &Path) -> Result<(), String> {
    fs::rename(temporary, target)
        .map_err(|error| format!("staged file could not be atomically installed: {error}"))
}

#[cfg(windows)]
fn atomic_replace(temporary: &Path, target: &Path) -> Result<(), String> {
    let source: Vec<u16> = temporary.as_os_str().encode_wide().chain(Some(0)).collect();
    let destination: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
    // SAFETY: both pointers reference live null-terminated UTF-16 buffers for
    // this call. The flags request replacement plus durable write-through only.
    let succeeded = unsafe {
        MoveFileExW(
            source.as_ptr(),
            destination.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if succeeded == 0 {
        return Err(format!(
            "staged file could not be atomically installed: {}",
            std::io::Error::last_os_error()
        ));
    }
    Ok(())
}

/// Stage, flush, install, and verify approved UTF-8 content.
#[pyfunction]
fn atomic_write_text(
    workspace_root: &str,
    relative_path: &str,
    content: &str,
    backup_root: &str,
    operation_id: &str,
) -> PyResult<(bool, Option<String>, String)> {
    let (_, target) = contained_target(workspace_root, relative_path)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    let existed = target.exists();
    let backup = backup_target(backup_root, operation_id)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    let before = if existed {
        let bytes = fs::read(&target).map_err(pyo3::exceptions::PyOSError::new_err)?;
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&backup)
            .map_err(pyo3::exceptions::PyOSError::new_err)?;
        file.write_all(&bytes)
            .and_then(|()| file.sync_all())
            .map_err(pyo3::exceptions::PyOSError::new_err)?;
        Some(hex_digest(&bytes))
    } else {
        None
    };
    let staged = stage_bytes(&target, content.as_bytes(), operation_id)
        .map_err(pyo3::exceptions::PyOSError::new_err)?;
    install_staged(&target, &staged, existed.then_some(backup.as_path()))
        .map_err(pyo3::exceptions::PyOSError::new_err)?;
    let installed = fs::read(&target).map_err(pyo3::exceptions::PyOSError::new_err)?;
    if installed != content.as_bytes() {
        return Err(pyo3::exceptions::PyOSError::new_err(
            "post-write content verification failed",
        ));
    }
    Ok((existed, before, hex_digest(&installed)))
}

/// Delete one approved file only after a flushed backup exists.
#[pyfunction]
fn reversible_delete_file(
    workspace_root: &str,
    relative_path: &str,
    backup_root: &str,
    operation_id: &str,
) -> PyResult<String> {
    let (_, target) = contained_target(workspace_root, relative_path)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    if !target.is_file() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "delete target must be an existing file",
        ));
    }
    let bytes = fs::read(&target).map_err(pyo3::exceptions::PyOSError::new_err)?;
    let backup = backup_target(backup_root, operation_id)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&backup)
        .map_err(pyo3::exceptions::PyOSError::new_err)?;
    file.write_all(&bytes)
        .and_then(|()| file.sync_all())
        .map_err(pyo3::exceptions::PyOSError::new_err)?;
    fs::remove_file(&target).map_err(pyo3::exceptions::PyOSError::new_err)?;
    Ok(hex_digest(&bytes))
}

/// Restore an approved mutation from its task-scoped backup.
#[pyfunction]
fn rollback_file(
    workspace_root: &str,
    relative_path: &str,
    backup_root: &str,
    operation_id: &str,
    existed_before: bool,
) -> PyResult<Option<String>> {
    let (_, target) = contained_target(workspace_root, relative_path)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    if !existed_before {
        if target.exists() {
            fs::remove_file(&target).map_err(pyo3::exceptions::PyOSError::new_err)?;
        }
        return Ok(None);
    }
    let backup = backup_target(backup_root, operation_id)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    let bytes = fs::read(&backup).map_err(pyo3::exceptions::PyOSError::new_err)?;
    let staged =
        stage_bytes(&target, &bytes, operation_id).map_err(pyo3::exceptions::PyOSError::new_err)?;
    install_staged(&target, &staged, Some(&backup))
        .map_err(pyo3::exceptions::PyOSError::new_err)?;
    Ok(Some(hex_digest(&bytes)))
}

/// Remove an internal backup after explicit acceptance.
#[pyfunction]
fn discard_backup(backup_root: &str, operation_id: &str) -> PyResult<()> {
    let backup = backup_target(backup_root, operation_id)
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
    if backup.exists() {
        fs::remove_file(backup).map_err(pyo3::exceptions::PyOSError::new_err)?;
    }
    Ok(())
}

/// Execute one allowlisted validation command without a shell.
#[pyfunction]
fn run_validation_process(
    py: Python<'_>,
    executable: &str,
    arguments: Vec<String>,
    working_directory: &str,
    timeout_ms: u64,
    cancellation_marker: &str,
) -> PyResult<(i32, String, String, bool, bool)> {
    py.detach(|| {
        let executable_path = PathBuf::from(executable)
            .canonicalize()
            .map_err(pyo3::exceptions::PyValueError::new_err)?;
        let name = executable_path
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or_default()
            .to_ascii_lowercase();
        let allowed = [
            "python", "python3", "pytest", "cargo", "ruff", "mypy", "black", "git",
        ];
        if !allowed.contains(&name.as_str()) {
            return Err(pyo3::exceptions::PyPermissionError::new_err(
                "validation executable is not allowlisted",
            ));
        }
        if arguments.iter().any(|argument| argument.contains('\0')) {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "process arguments contain an invalid null byte",
            ));
        }
        let cwd = PathBuf::from(working_directory)
            .canonicalize()
            .map_err(pyo3::exceptions::PyValueError::new_err)?;
        if !cwd.is_dir() || timeout_ms == 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "working directory and timeout must be valid",
            ));
        }
        let marker = PathBuf::from(cancellation_marker);
        let mut child = Command::new(executable_path)
            .args(arguments)
            .current_dir(cwd)
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(pyo3::exceptions::PyOSError::new_err)?;
        let started = Instant::now();
        let mut cancelled = false;
        let mut timed_out = false;
        loop {
            if child
                .try_wait()
                .map_err(pyo3::exceptions::PyOSError::new_err)?
                .is_some()
            {
                break;
            }
            if marker.exists() {
                cancelled = true;
            } else if started.elapsed() >= Duration::from_millis(timeout_ms) {
                timed_out = true;
            }
            if cancelled || timed_out {
                child.kill().map_err(pyo3::exceptions::PyOSError::new_err)?;
                break;
            }
            thread::sleep(Duration::from_millis(10));
        }
        let output = child
            .wait_with_output()
            .map_err(pyo3::exceptions::PyOSError::new_err)?;
        Ok((
            output.status.code().unwrap_or(-1),
            String::from_utf8_lossy(&output.stdout).into_owned(),
            String::from_utf8_lossy(&output.stderr).into_owned(),
            timed_out,
            cancelled,
        ))
    })
}

fn validate_workspace_path_value(
    workspace_root: &str,
    relative_path: &str,
) -> Result<String, String> {
    let candidate = Path::new(relative_path);
    if candidate.as_os_str().is_empty() || candidate.is_absolute() {
        return Err("workspace path must be non-empty and relative".to_owned());
    }
    let root = PathBuf::from(workspace_root)
        .canonicalize()
        .map_err(|error| format!("workspace root is unavailable: {error}"))?;
    if !root.is_dir() {
        return Err("workspace root must be a directory".to_owned());
    }
    let resolved = root
        .join(candidate)
        .canonicalize()
        .map_err(|error| format!("workspace path is unavailable: {error}"))?;
    if !resolved.starts_with(&root) {
        return Err("workspace path escapes the selected root".to_owned());
    }
    Ok(resolved.to_string_lossy().into_owned())
}

/// Register the side-effect-free Virgo Rust-core verification module.
#[pymodule]
fn _rust_core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(rust_core_status, module)?)?;
    module.add_function(wrap_pyfunction!(validate_workspace_path, module)?)?;
    module.add_function(wrap_pyfunction!(atomic_write_text, module)?)?;
    module.add_function(wrap_pyfunction!(reversible_delete_file, module)?)?;
    module.add_function(wrap_pyfunction!(rollback_file, module)?)?;
    module.add_function(wrap_pyfunction!(discard_backup, module)?)?;
    module.add_function(wrap_pyfunction!(run_validation_process, module)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        READY_STATUS, install_staged, rust_core_status_value, stage_bytes,
        validate_workspace_path_value,
    };
    use std::fs;
    use std::path::Path;

    #[test]
    fn rust_core_status_reports_ready() {
        assert_eq!(rust_core_status_value(), READY_STATUS);
    }

    #[test]
    fn workspace_path_validation_contains_existing_paths() {
        let root = std::env::current_dir()
            .expect("current directory")
            .canonicalize()
            .expect("canonical current directory");
        let root_text = root.to_string_lossy();
        let resolved = validate_workspace_path_value(&root_text, "Cargo.toml")
            .expect("workspace file must resolve");
        assert!(Path::new(&resolved).starts_with(&root));
        assert!(validate_workspace_path_value(&root_text, "../Cargo.toml").is_err());
    }

    #[test]
    fn staged_install_atomically_replaces_existing_content() {
        let directory =
            std::env::temp_dir().join(format!("virgo-rust-atomic-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir(&directory).expect("temporary test directory");
        let target = directory.join("target.txt");
        let backup = directory.join("backup.txt");
        fs::write(&target, b"before").expect("initial target");
        fs::write(&backup, b"before").expect("backup");
        let staged = stage_bytes(&target, b"after", "atomic-test").expect("staged file");

        install_staged(&target, &staged, Some(&backup)).expect("atomic install");

        assert_eq!(fs::read(&target).expect("installed target"), b"after");
        assert!(!staged.exists());
        fs::remove_dir_all(directory).expect("test cleanup");
    }
}
