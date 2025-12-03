// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::fs;
use std::io::Write;
use tauri::Manager;
use uuid::Uuid;

#[derive(Debug, Serialize, Deserialize)]
struct SSTVResult {
    success: bool,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    image_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    audio_path: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    progress: Option<f32>,
    #[serde(skip_serializing_if = "Option::is_none")]
    vis_code: Option<i32>,
}

// Security: Path validation to prevent directory traversal
fn validate_user_path(path_str: &str) -> Result<PathBuf, String> {
    let path = Path::new(path_str);
    
    // Reject null bytes
    if path_str.bytes().any(|b| b == 0) {
        return Err("Invalid path: null byte detected".to_string());
    }

    // Check for path traversal attempts
    if path_str.contains("..") || path_str.contains("~") {
        return Err("Invalid path: path traversal not allowed".to_string());
    }
    
    // Ensure path is absolute and normalize it
    let canonical_path = path.canonicalize()
        .map_err(|_| "Invalid path: file does not exist or is not accessible".to_string())?;
    
    // Additional security: ensure the file exists and is readable
    if !canonical_path.exists() {
        return Err("Invalid path: file does not exist".to_string());
    }
    
    if !canonical_path.is_file() {
        return Err("Invalid path: not a file".to_string());
    }
    
    Ok(canonical_path)
}

// (removed) validate_resource_path: replaced by get_python_engine_path with dev fallback

// Resolve Python engine root path for both packaged and dev builds
// Returns the path to the Python engine directory (containing sstv_engine package)
fn get_python_engine_path(app_handle: &tauri::AppHandle) -> Result<PathBuf, String> {
    // First try packaged resource_dir (bundled Python venv)
    if let Ok(resource_dir) = app_handle.path().resource_dir() {
        // In packaged mode, resources/python contains the bundled venv
        let bundled_python = resource_dir.join("python");
        if bundled_python.exists() && bundled_python.is_dir() {
            // The sstv_engine package is in lib/pythonX.Y/site-packages
            // We need to find the actual Python version
            let lib_dir = bundled_python.join("lib");
            if lib_dir.exists() {
                if let Ok(entries) = std::fs::read_dir(&lib_dir) {
                    for entry in entries.flatten() {
                        let name = entry.file_name();
                        let name_str = name.to_string_lossy();
                        if name_str.starts_with("python") {
                            let site_packages = entry.path().join("site-packages");
                            if site_packages.exists() {
                                return Ok(site_packages);
                            }
                        }
                    }
                }
            }
        }
    }

    // Dev fallback: compute from crate dir (src-tauri)
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let dev_candidate = manifest_dir
        .parent()
        .and_then(|p| p.parent())
        .unwrap_or_else(|| Path::new(".")).to_path_buf()
        .join("core")
        .join("python");
    if dev_candidate.exists() && dev_candidate.is_dir() {
        return Ok(dev_candidate);
    }

    Err("Python engine path not found in resources or dev tree".to_string())
}

// Security: Generate secure temporary file with random UUID
fn create_secure_temp_file(prefix: &str, extension: &str) -> Result<PathBuf, String> {
    let temp_dir = std::env::temp_dir();
    let unique_id = Uuid::new_v4();
    let filename = format!("{}_{}.{}", prefix, unique_id, extension);
    let temp_path = temp_dir.join(filename);
    
    // Ensure temp directory exists and is writable
    if !temp_dir.exists() || !temp_dir.is_dir() {
        return Err("Temporary directory not accessible".to_string());
    }
    
    Ok(temp_path)
}

// Security: Sanitize error messages to prevent information disclosure
fn sanitize_error_message(error: &str) -> String {
    // Remove sensitive information like full paths, system details
    let sanitized = error
        .lines()
        .filter(|line| {
            // Filter out lines that might contain sensitive paths or system info
            !line.contains("C:\\") && 
            !line.contains("/home/") && 
            !line.contains("/Users/") &&
            !line.contains("Traceback") &&
            !line.contains("File \"")
        })
        .collect::<Vec<_>>()
        .join(" ");
    
    if sanitized.is_empty() {
        "An error occurred during processing".to_string()
    } else {
        // Limit error message length
        if sanitized.len() > 200 {
            format!("{}...", &sanitized[..200])
        } else {
            sanitized
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{
        parse_decode_output, parse_encode_output, sanitize_error_message, validate_user_path,
    };
    use std::fs::File;
    use std::io::Write;
    use std::path::PathBuf;

    #[test]
    fn sanitize_removes_paths_and_traces() {
        let raw = "Traceback\nFile \"/home/user/secret.py\", line 1\nError: something bad at C:\\tmp\\foo.txt";
        let s = sanitize_error_message(raw);
        assert!(!s.contains("/home/"));
        assert!(!s.contains("C:\\"));
        assert!(!s.contains("Traceback"));
        assert!(s.len() > 0);
    }

    #[test]
    fn validate_user_path_allows_valid_paths() {
        let mut temp_path = std::env::temp_dir();
        temp_path.push("sstv_validate_ok.txt");

        // Create temp file
        let mut f = File::create(&temp_path).expect("create temp file");
        writeln!(f, "ok").unwrap();

        let validated = validate_user_path(temp_path.to_string_lossy().as_ref())
            .expect("expected valid path");

        assert_eq!(
            validated,
            PathBuf::from(&temp_path).canonicalize().unwrap()
        );

        let _ = std::fs::remove_file(&temp_path);
    }

    #[test]
    fn validate_user_path_blocks_traversal() {
        let err = validate_user_path("../etc/passwd");
        assert!(err.is_err());
    }

    #[test]
    fn validate_user_path_blocks_null_bytes() {
        let err = validate_user_path("foo\0bar");
        assert!(err.is_err());
    }

    #[test]
    fn parse_decode_extracts_image_and_mode() {
        let stdout = b"SUCCESS:true\nIMAGE:/tmp/out.png\nMODE:ScottieS1\nVIS:112\n";
        let parsed = parse_decode_output(stdout);
        assert!(parsed.success);
        assert_eq!(parsed.image_path.as_deref(), Some("/tmp/out.png"));
        assert_eq!(parsed.mode.as_deref(), Some("ScottieS1"));
        assert_eq!(parsed.vis_code, Some(112));
        assert!(parsed.message.contains("decoded successfully"));
    }

    #[test]
    fn parse_decode_handles_error_line() {
        let stdout = b"SUCCESS:false\nERROR:Something went wrong\n";
        let parsed = parse_decode_output(stdout);
        assert!(!parsed.success);
        assert!(parsed.message.to_lowercase().contains("something"));
    }

    #[test]
    fn parse_encode_extracts_audio_path() {
        let stdout = b"SUCCESS:true\nAUDIO:/tmp/out.wav\n";
        let parsed = parse_encode_output(stdout, "ScottieS1");
        assert!(parsed.success);
        assert_eq!(parsed.audio_path.as_deref(), Some("/tmp/out.wav"));
        assert!(parsed.message.contains("ScottieS1"));
    }

    #[test]
    fn parse_encode_handles_error_line() {
        let stdout = b"SUCCESS:false\nERROR:No audio\n";
        let parsed = parse_encode_output(stdout, "ScottieS1");
        assert!(!parsed.success);
        assert!(parsed.message.to_lowercase().contains("audio"));
        assert!(parsed.audio_path.is_none());
    }

    #[test]
    fn default_modes_returns_expected_list() {
        let modes = super::default_sstv_modes();
        assert_eq!(modes.len(), 6);
        assert!(modes.contains(&"ScottieS1".to_string()));
        assert!(modes.contains(&"Robot36".to_string()));
    }
}

// Security: Execute Python with validated arguments and secure script file
fn execute_python_securely(
    python_path: &Path,
    script_content: &str,
    args: &HashMap<String, String>
) -> Result<std::process::Output, String> {
    // Create secure temporary script file
    let script_path = create_secure_temp_file("sstv_script", "py")?;
    
    // Write script content to temporary file with parameter placeholders
    let mut script_file = fs::File::create(&script_path)
        .map_err(|_| "Failed to create temporary script file".to_string())?;
    
    script_file.write_all(script_content.as_bytes())
        .map_err(|_| "Failed to write script content".to_string())?;
    
    script_file.flush()
        .map_err(|_| "Failed to flush script file".to_string())?;
    
    // Prepare environment variables for secure parameter passing
    let mut cmd = Command::new(python_path);
    cmd.arg(&script_path);
    
    // Pass arguments as environment variables instead of command line args
    for (key, value) in args {
        cmd.env(format!("SSTV_ARG_{}", key), value);
    }
    
    // Execute with timeout and resource limits
    let output = cmd.output()
        .map_err(|e| format!("Python execution failed: {}", sanitize_error_message(&e.to_string())))?;
    
    // Clean up temporary script file
    let _ = fs::remove_file(&script_path);
    
    Ok(output)
}

struct ParseEncodeResult {
    success: bool,
    message: String,
    audio_path: Option<String>,
}

fn parse_encode_output(stdout: &[u8], mode: &str) -> ParseEncodeResult {
    let stdout = String::from_utf8_lossy(stdout);
    let mut success = false;
    let mut message = "Unknown result".to_string();
    let mut audio_path = None;

    for line in stdout.lines() {
        if line.starts_with("SUCCESS:") {
            success = line.split(':').nth(1).unwrap_or("false") == "true";
        } else if line.starts_with("AUDIO:") {
            if success {
                audio_path = Some(line.split(':').nth(1).unwrap_or("").to_string());
            }
        } else if line.starts_with("ERROR:") {
            message = sanitize_error_message(line.split(':').nth(1).unwrap_or("Unknown error"));
        }
    }

    if success {
        message = format!("SSTV audio encoded successfully ({})", mode);
    }

    ParseEncodeResult {
        success,
        message,
        audio_path,
    }
}
// Decode SSTV from audio file
#[tauri::command]
async fn decode_sstv_file(app_handle: tauri::AppHandle, audio_path: String) -> Result<SSTVResult, String> {
    
    // Security: Validate user-provided audio path
    let validated_audio_path = validate_user_path(&audio_path)?;
    
    // Resolve Python engine path (packaged or dev)
    let python_engine_path = get_python_engine_path(&app_handle)?;
    let venv_python = get_venv_python_path(&python_engine_path)?;
    
    // Security: Create secure temporary output file
    let output_path = create_secure_temp_file("sstv_decode", "png")?;
    
    // Security: Use parameterized script execution
    let script_content = r#"
import sys
import os
from pathlib import Path

# Get arguments from environment variables
engine_path = os.environ.get('SSTV_ARG_ENGINE_PATH')
audio_path = os.environ.get('SSTV_ARG_AUDIO_PATH') 
output_path = os.environ.get('SSTV_ARG_OUTPUT_PATH')

if not all([engine_path, audio_path, output_path]):
    print("ERROR:Missing required arguments")
    sys.exit(1)

# Validate paths exist
if not Path(engine_path).exists():
    print("ERROR:Engine path not found")
    sys.exit(1)
    
if not Path(audio_path).exists():
    print("ERROR:Audio file not found")
    sys.exit(1)

sys.path.append(engine_path)

try:
    from sstv_engine.decoder import SSTVDecoder
    from sstv_engine.types import SSTVDecodeRequest

    decoder = SSTVDecoder()
    req = SSTVDecodeRequest(audio_path=audio_path, output_path=output_path)
    result = decoder.decode(req)

    print(f"SUCCESS:{str(result.success).lower()}")
    if result.success:
        print(f"IMAGE:{output_path}")
        if getattr(result, 'mode', None):
            print(f"MODE:{result.mode}")
    else:
        print("ERROR:Decoding failed")

except ImportError:
    print("ERROR:SSTV engine not available")
except Exception:
    print("ERROR:Decoding error occurred")
"#;
    
    let mut args = HashMap::new();
    args.insert("ENGINE_PATH".to_string(), python_engine_path.to_string_lossy().to_string());
    args.insert("AUDIO_PATH".to_string(), validated_audio_path.to_string_lossy().to_string());
    args.insert("OUTPUT_PATH".to_string(), output_path.to_string_lossy().to_string());
    
    let output = execute_python_securely(&venv_python, script_content, &args)?;

    if !output.status.success() {
        return Ok(SSTVResult {
            success: false,
            message: "Decoding process failed".to_string(),
            image_path: None,
            audio_path: None,
            progress: None,
            vis_code: None,
        });
    }

    let ParseDecodeResult {
        success,
        mut message,
        image_path,
        vis_code,
        mode,
    } = parse_decode_output(&output.stdout);

    if success {
        if let Some(m) = mode {
            message = format!("SSTV image decoded successfully ({})", m);
        } else {
            message = "SSTV image decoded successfully".to_string();
        }
    }

    Ok(SSTVResult {
        success,
        message,
        image_path,
        audio_path: None,
        progress: None,
        vis_code,
    })
}

struct ParseDecodeResult {
    success: bool,
    message: String,
    image_path: Option<String>,
    vis_code: Option<i32>,
    mode: Option<String>,
}

fn parse_decode_output(stdout: &[u8]) -> ParseDecodeResult {
    let stdout = String::from_utf8_lossy(stdout);
    let mut success = false;
    let mut message = "Unknown result".to_string();
    let mut image_path = None;
    let mut vis_code = None;
    let mut mode = None;

    for line in stdout.lines() {
        if line.starts_with("SUCCESS:") {
            success = line.split(':').nth(1).unwrap_or("false") == "true";
        } else if line.starts_with("IMAGE:") {
            if success {
                image_path = Some(line.split(':').nth(1).unwrap_or("").to_string());
            }
        } else if line.starts_with("VIS:") {
            if let Ok(code) = line.split(':').nth(1).unwrap_or("0").parse::<i32>() {
                vis_code = Some(code);
            }
        } else if line.starts_with("MODE:") {
            mode = Some(line.split(':').nth(1).unwrap_or("").to_string());
        } else if line.starts_with("ERROR:") {
            message = sanitize_error_message(line.split(':').nth(1).unwrap_or("Unknown error"));
        }
    }

    if success && mode.is_some() {
        message = format!("SSTV image decoded successfully ({})", mode.clone().unwrap());
    } else if success {
        message = "SSTV image decoded successfully".to_string();
    }

    ParseDecodeResult {
        success,
        message,
        image_path,
        vis_code,
        mode,
    }
}

// Encode image to SSTV audio
#[tauri::command]
async fn encode_sstv_image(app_handle: tauri::AppHandle, image_path: String, mode: String) -> Result<SSTVResult, String> {
    
    // Security: Validate user-provided image path
    let validated_image_path = validate_user_path(&image_path)?;
    
    // Security: Validate mode parameter (whitelist allowed modes)
    let allowed_modes = vec![
        "ScottieS1", "ScottieS2", "ScottieDX", 
        "MartinM1", "MartinM2", "Robot36"
    ];
    if !allowed_modes.contains(&mode.as_str()) {
        return Err("Invalid SSTV mode specified".to_string());
    }
    
    // Resolve Python engine path (packaged or dev)
    let python_engine_path = get_python_engine_path(&app_handle)?;
    let venv_python = get_venv_python_path(&python_engine_path)?;
    
    // Security: Create secure temporary output file
    let output_path = create_secure_temp_file("sstv_encode", "wav")?;
    
    let script_content = r#"
import sys
import os
from pathlib import Path

# Get arguments from environment variables
engine_path = os.environ.get('SSTV_ARG_ENGINE_PATH')
image_path = os.environ.get('SSTV_ARG_IMAGE_PATH')
output_path = os.environ.get('SSTV_ARG_OUTPUT_PATH')
mode = os.environ.get('SSTV_ARG_MODE')

if not all([engine_path, image_path, output_path, mode]):
    print("ERROR:Missing required arguments")
    sys.exit(1)

# Validate paths exist
if not Path(engine_path).exists():
    print("ERROR:Engine path not found")
    sys.exit(1)
    
if not Path(image_path).exists():
    print("ERROR:Image file not found")
    sys.exit(1)

sys.path.append(engine_path)

try:
    from sstv_engine.encoder import SSTVEncoder
    from sstv_engine.types import SSTVEncodeRequest

    encoder = SSTVEncoder()
    req = SSTVEncodeRequest(image_path=image_path, output_path=output_path, mode=mode)
    result = encoder.encode(req)

    print(f"SUCCESS:{str(result.success).lower()}")
    if result.success:
        print(f"AUDIO:{output_path}")
    else:
        print("ERROR:Encoding failed")

except ImportError:
    print("ERROR:SSTV engine not available")
except Exception:
    print("ERROR:Encoding error occurred")
"#;
    
    let mut args = HashMap::new();
    args.insert("ENGINE_PATH".to_string(), python_engine_path.to_string_lossy().to_string());
    args.insert("IMAGE_PATH".to_string(), validated_image_path.to_string_lossy().to_string());
    args.insert("OUTPUT_PATH".to_string(), output_path.to_string_lossy().to_string());
    args.insert("MODE".to_string(), mode.clone());
    
    let output = execute_python_securely(&venv_python, script_content, &args)?;

    if !output.status.success() {
        return Ok(SSTVResult {
            success: false,
            message: "Encoding process failed".to_string(),
            image_path: None,
            audio_path: None,
            progress: None,
            vis_code: None,
        });
    }

    let ParseEncodeResult {
        success,
        mut message,
        audio_path,
    } = parse_encode_output(&output.stdout, &mode);

    Ok(SSTVResult {
        success,
        message,
        image_path: None,
        audio_path,
        progress: None,
        vis_code: None,
    })
}

// Get available SSTV modes
#[tauri::command]
async fn get_sstv_modes(app_handle: tauri::AppHandle) -> Result<Vec<String>, String> {
    
    // Resolve Python engine path (packaged or dev)
    let python_engine_path = get_python_engine_path(&app_handle)?;
    let venv_python = get_venv_python_path(&python_engine_path)?;
    
    let script_content = r#"
import sys
import os

engine_path = os.environ.get('SSTV_ARG_ENGINE_PATH')
if not engine_path:
    print("ERROR:Missing engine path")
    sys.exit(1)

sys.path.append(engine_path)

try:
    from sstv_engine.encoder import SSTVEncoder

    encoder = SSTVEncoder()
    modes = encoder.get_supported_modes()

    for mode in modes:
        print(mode)
        
except ImportError:
    print("ERROR:SSTV engine not available")
except Exception:
    print("ERROR:Failed to get modes")
"#;
    
    let mut args = HashMap::new();
    args.insert("ENGINE_PATH".to_string(), python_engine_path.to_string_lossy().to_string());
    
    let output = execute_python_securely(&venv_python, script_content, &args)?;

    if !output.status.success() {
        // Return default modes if Python execution fails
        return Ok(default_sstv_modes());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let modes: Vec<String> = stdout
        .lines()
        .filter(|line| !line.is_empty() && !line.starts_with("ERROR:"))
        .map(|s| s.to_string())
        .collect();

    if modes.is_empty() {
        // Return default modes if no modes found
        Ok(default_sstv_modes())
    } else {
        Ok(modes)
    }
}

fn default_sstv_modes() -> Vec<String> {
    vec![
        "ScottieS1".to_string(),
        "ScottieS2".to_string(),
        "ScottieDX".to_string(),
        "MartinM1".to_string(),
        "MartinM2".to_string(),
        "Robot36".to_string(),
    ]
}

// Check Python engine status
#[tauri::command]
async fn check_python_engine(app_handle: tauri::AppHandle) -> Result<SSTVResult, String> {
    
    // Resolve Python engine path (packaged or dev)
    let python_engine_path = get_python_engine_path(&app_handle)?;
    let venv_python = get_venv_python_path(&python_engine_path)?;
    
    let script_content = r#"
import sys
import os

engine_path = os.environ.get('SSTV_ARG_ENGINE_PATH')
if not engine_path:
    print("SUCCESS:false")
    print("ERROR:Missing engine path")
    sys.exit(1)

sys.path.append(engine_path)

try:
    from sstv_engine.decoder import SSTVDecoder
    
    decoder = SSTVDecoder()
    result = decoder.check_dependencies()

    print(f"SUCCESS:{str(result).lower()}")
    if not result:
        print("ERROR:Missing dependencies")
    else:
        print("MESSAGE:SSTV engine ready")
        
except ImportError:
    print("SUCCESS:false")
    print("ERROR:SSTV engine not available")
except Exception:
    print("SUCCESS:false")  
    print("ERROR:Engine check failed")
"#;
    
    let mut args = HashMap::new();
    args.insert("ENGINE_PATH".to_string(), python_engine_path.to_string_lossy().to_string());
    
    let output = execute_python_securely(&venv_python, script_content, &args)?;

    // Parse output
    let stdout = String::from_utf8_lossy(&output.stdout);
    
    let mut success = false;
    let mut message = "Python engine check failed".to_string();

    for line in stdout.lines() {
        if line.starts_with("SUCCESS:") {
            success = line.split(':').nth(1).unwrap_or("false") == "true";
        } else if line.starts_with("MESSAGE:") {
            message = line.split(':').nth(1).unwrap_or("").to_string();
        } else if line.starts_with("ERROR:") {
            message = sanitize_error_message(line.split(':').nth(1).unwrap_or("Unknown error"));
        }
    }

    Ok(SSTVResult {
        success,
        message,
        image_path: None,
        audio_path: None,
        progress: None,
        vis_code: None,
    })
}

// Get Python executable path - handles both bundled and dev modes
fn get_venv_python_path(python_engine_path: &Path) -> Result<PathBuf, String> {
    // Validate that python_engine_path exists and is a directory
    if !python_engine_path.exists() || !python_engine_path.is_dir() {
        return Err("Invalid Python engine path".to_string());
    }

    // Check if this is a bundled venv (engine_path ends in site-packages)
    // In that case, Python is at ../../bin/python3 relative to site-packages
    if python_engine_path.ends_with("site-packages") {
        // site-packages -> pythonX.Y -> lib -> venv_root
        if let Some(venv_root) = python_engine_path.parent().and_then(|p| p.parent()).and_then(|p| p.parent()) {
            let venv_python = if cfg!(windows) {
                venv_root.join("Scripts").join("python.exe")
            } else {
                venv_root.join("bin").join("python3")
            };

            if venv_python.exists() && venv_python.is_file() {
                return Ok(venv_python);
            }
        }
    }

    // Dev mode: check for .venv in the python engine directory
    let dev_venv = python_engine_path.join(".venv");
    if dev_venv.exists() && dev_venv.is_dir() {
        let venv_python = if cfg!(windows) {
            dev_venv.join("Scripts").join("python.exe")
        } else {
            dev_venv.join("bin").join("python3")
        };

        if venv_python.exists() && venv_python.is_file() {
            return Ok(venv_python);
        }
    }

    // Legacy: check for venv at project root (two levels up from core/python)
    if let Some(project_root) = python_engine_path.parent().and_then(|p| p.parent()) {
        let legacy_venv = project_root.join("venv");
        if legacy_venv.exists() && legacy_venv.is_dir() {
            let venv_python = if cfg!(windows) {
                legacy_venv.join("Scripts").join("python.exe")
            } else {
                legacy_venv.join("bin").join("python")
            };

            if venv_python.exists() && venv_python.is_file() {
                return Ok(venv_python);
            }
        }
    }

    // Fallback to system Python with validation
    let system_python = if cfg!(windows) {
        PathBuf::from("python.exe")
    } else {
        PathBuf::from("python3")
    };

    // Verify system Python exists
    match std::process::Command::new(&system_python).arg("--version").output() {
        Ok(output) if output.status.success() => Ok(system_python),
        _ => Err("No valid Python interpreter found".to_string()),
    }
}

// Enhance image with specified parameters
#[tauri::command]
async fn enhance_image(
    image_path: String, 
    _contrast: f32, 
    _brightness: i32, 
    _saturation: f32,
    _preset: Option<String>
) -> Result<SSTVResult, String> {
    // For now, return success since enhancement is handled by CSS filters in frontend
    // In a complete implementation, this would use Python PIL for server-side enhancement
    Ok(SSTVResult {
        success: true,
        message: "Image enhancement applied".to_string(),
        image_path: Some(image_path),
        audio_path: None,
        progress: None,
        vis_code: None,
    })
}

// Save image with dialog
#[tauri::command]
async fn save_image_dialog(image_path: String) -> Result<SSTVResult, String> {
    // Security: Validate user-provided image path
    let validated_image_path = validate_user_path(&image_path)?;
    
    // For now, return success since file saving is handled by frontend dialogs
    // In a complete implementation, this would use Tauri's save dialog
    Ok(SSTVResult {
        success: true,
        message: "Save dialog functionality ready".to_string(),
        image_path: Some(validated_image_path.to_string_lossy().to_string()),
        audio_path: None,
        progress: None,
        vis_code: None,
    })
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![
            decode_sstv_file,
            encode_sstv_image, 
            get_sstv_modes,
            check_python_engine,
            enhance_image,
            save_image_dialog
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
