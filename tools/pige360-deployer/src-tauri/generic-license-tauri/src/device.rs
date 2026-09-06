use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::env;
use std::path::PathBuf;

use crate::models::LicenseCheckInput;

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct DeviceCollectedInfo {
    pub station_name: String,
    pub hostname: String,
    pub computer_name: String,
    pub serial_number: String,
    pub machine_guid: String,
    pub bios_serial: String,
    pub motherboard_serial: String,
    pub logged_user: String,
    pub os_name: String,
    pub os_version: String,
    pub os_arch: String,
    pub domain_name: String,
    pub mac_addresses: Vec<String>,
    pub install_mode: String,
}

pub fn enrich_input(input: &mut LicenseCheckInput) {
    let info = collect_device_metadata();

    if input.hostname.as_deref().unwrap_or("").is_empty() {
        input.hostname = Some(info.hostname.clone());
    }
    if input.computer_name.as_deref().unwrap_or("").is_empty() {
        input.computer_name = Some(info.computer_name.clone());
    }
    if input.station_name.as_deref().unwrap_or("").is_empty() {
        input.station_name = Some(info.station_name.clone());
    }
    if input.device_name.as_deref().unwrap_or("").is_empty() {
        input.device_name = Some(info.station_name.clone());
    }
    if input.serial_number.as_deref().unwrap_or("").is_empty() {
        input.serial_number = non_empty_or_none(info.serial_number.clone());
    }
    if input.machine_guid.as_deref().unwrap_or("").is_empty() {
        input.machine_guid = non_empty_or_none(info.machine_guid.clone());
    }
    if input.bios_serial.as_deref().unwrap_or("").is_empty() {
        input.bios_serial = non_empty_or_none(info.bios_serial.clone());
    }
    if input.motherboard_serial.as_deref().unwrap_or("").is_empty() {
        input.motherboard_serial = non_empty_or_none(info.motherboard_serial.clone());
    }
    if input.logged_user.as_deref().unwrap_or("").is_empty() {
        input.logged_user = non_empty_or_none(info.logged_user.clone());
    }
    if input.os_name.as_deref().unwrap_or("").is_empty() {
        input.os_name = non_empty_or_none(info.os_name.clone());
    }
    if input.os_version.as_deref().unwrap_or("").is_empty() {
        input.os_version = non_empty_or_none(info.os_version.clone());
    }
    if input.os_arch.as_deref().unwrap_or("").is_empty() {
        input.os_arch = non_empty_or_none(info.os_arch.clone());
    }
    if input.domain_name.as_deref().unwrap_or("").is_empty() {
        input.domain_name = non_empty_or_none(info.domain_name.clone());
    }
    if input.mac_addresses.is_empty() {
        input.mac_addresses = info.mac_addresses.clone();
    }
    if input.install_mode.as_deref().unwrap_or("").is_empty() {
        input.install_mode = non_empty_or_none(info.install_mode.clone());
    }

    if input.device_key.as_deref().unwrap_or("").is_empty() {
        input.device_key = Some(generate_device_key(input));
    }
}

pub fn hostname_or_unknown() -> String {
    hostname::get()
        .map(|v| v.to_string_lossy().to_string())
        .unwrap_or_else(|_| "unknown-host".to_string())
}

pub fn current_user_or_unknown() -> String {
    env::var("USERNAME")
        .or_else(|_| env::var("USER"))
        .unwrap_or_else(|_| "unknown-user".to_string())
}

pub fn default_device_name() -> String {
    let info = collect_device_metadata();
    info.station_name
}

pub fn generate_device_key(input: &LicenseCheckInput) -> String {
    let parts = vec![
        input.app_id.clone(),
        input.app_slug.clone().unwrap_or_default(),
        input.machine_guid.clone().unwrap_or_default(),
        input.bios_serial.clone().unwrap_or_default(),
        input.motherboard_serial.clone().unwrap_or_default(),
        input.mac_addresses.first().cloned().unwrap_or_default(),
        input.hostname.clone().unwrap_or_default(),
        input.os_name.clone().unwrap_or_default(),
        input.os_arch.clone().unwrap_or_default(),
    ];

    let mut hasher = Sha256::new();
    hasher.update(parts.join("|").as_bytes());
    hex::encode(hasher.finalize())
}

pub fn collect_device_metadata() -> DeviceCollectedInfo {
    let hostname = hostname_or_unknown();
    let computer_name = env::var("COMPUTERNAME").unwrap_or_else(|_| hostname.clone());
    let logged_user = current_user_or_unknown();
    let os_name = env::consts::OS.to_string();
    let os_arch = env::consts::ARCH.to_string();
    let os_version = os_version();
    let serial_number = first_non_empty(vec![system_serial_number(), bios_serial()]);
    let machine_guid = machine_guid();
    let bios_serial = bios_serial();
    let motherboard_serial = motherboard_serial();
    let domain_name = domain_name();
    let mac_addresses = mac_addresses();
    let install_mode = detect_install_mode();
    let station_name = hostname.clone();

    DeviceCollectedInfo {
        station_name,
        hostname,
        computer_name,
        serial_number,
        machine_guid,
        bios_serial,
        motherboard_serial,
        logged_user,
        os_name,
        os_version,
        os_arch,
        domain_name,
        mac_addresses,
        install_mode,
    }
}

fn detect_install_mode() -> String {
    let exe = env::current_exe().unwrap_or_else(|_| PathBuf::from("."));
    let exe_str = exe.to_string_lossy().to_string();

    if env::var("SESSIONNAME")
        .unwrap_or_default()
        .to_uppercase()
        .contains("RDP")
    {
        return "terminal-session".to_string();
    }

    if exe_str.starts_with(r"\\") || exe_str.starts_with("//") {
        return "shared-server".to_string();
    }

    "workstation".to_string()
}

fn os_version() -> String {
    #[cfg(target_os = "windows")]
    {
        env::var("OS").unwrap_or_default()
    }
    #[cfg(target_os = "linux")]
    {
        let release = std::fs::read_to_string("/etc/os-release").unwrap_or_default();
        release
            .lines()
            .find(|l| l.starts_with("PRETTY_NAME="))
            .map(|l| l.replace("PRETTY_NAME=", "").trim_matches('"').to_string())
            .unwrap_or_default()
    }
    #[cfg(target_os = "macos")]
    {
        String::new()
    }
    #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
    {
        String::new()
    }
}

fn machine_guid() -> String {
    #[cfg(target_os = "windows")]
    {
        String::new()
    }
    #[cfg(target_os = "linux")]
    {
        let candidates = ["/etc/machine-id", "/var/lib/dbus/machine-id"];
        for path in candidates {
            let content = std::fs::read_to_string(path)
                .unwrap_or_default()
                .trim()
                .to_string();
            if !content.is_empty() {
                return content;
            }
        }
        String::new()
    }
    #[cfg(target_os = "macos")]
    {
        String::new()
    }
    #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
    {
        String::new()
    }
}

fn bios_serial() -> String {
    #[cfg(target_os = "windows")]
    {
        String::new()
    }
    #[cfg(target_os = "linux")]
    {
        let val = std::fs::read_to_string("/sys/class/dmi/id/bios_version").unwrap_or_default();
        let val = val.trim();
        if val.is_empty() {
            String::new()
        } else {
            val.to_string()
        }
    }
    #[cfg(target_os = "macos")]
    {
        String::new()
    }
    #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
    {
        String::new()
    }
}

fn motherboard_serial() -> String {
    #[cfg(target_os = "windows")]
    {
        String::new()
    }
    #[cfg(target_os = "linux")]
    {
        let val = std::fs::read_to_string("/sys/class/dmi/id/board_serial").unwrap_or_default();
        let val = val.trim();
        if val.is_empty() {
            String::new()
        } else {
            val.to_string()
        }
    }
    #[cfg(target_os = "macos")]
    {
        String::new()
    }
    #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
    {
        String::new()
    }
}

fn system_serial_number() -> String {
    #[cfg(target_os = "windows")]
    {
        String::new()
    }
    #[cfg(target_os = "linux")]
    {
        let val = std::fs::read_to_string("/sys/class/dmi/id/product_uuid").unwrap_or_default();
        let val = val.trim();
        if val.is_empty() {
            String::new()
        } else {
            val.to_string()
        }
    }
    #[cfg(target_os = "macos")]
    {
        String::new()
    }
    #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
    {
        String::new()
    }
}

fn domain_name() -> String {
    env::var("USERDOMAIN")
        .or_else(|_| env::var("DOMAINNAME"))
        .unwrap_or_default()
}

fn mac_addresses() -> Vec<String> {
    #[cfg(target_os = "windows")]
    {
        Vec::new()
    }
    #[cfg(target_os = "linux")]
    {
        let mut macs = Vec::new();
        if let Ok(entries) = std::fs::read_dir("/sys/class/net") {
            for entry in entries.flatten() {
                let addr_path = entry.path().join("address");
                let value = std::fs::read_to_string(addr_path).unwrap_or_default();
                let mac = value.trim().to_string();
                if !mac.is_empty() && mac != "00:00:00:00:00:00" {
                    macs.push(mac);
                }
            }
        }
        macs
    }
    #[cfg(target_os = "macos")]
    {
        Vec::new()
    }
    #[cfg(not(any(target_os = "windows", target_os = "linux", target_os = "macos")))]
    {
        Vec::new()
    }
}

fn first_non_empty(values: Vec<String>) -> String {
    values
        .into_iter()
        .find(|v| !v.trim().is_empty())
        .unwrap_or_default()
}

fn non_empty_or_none(value: String) -> Option<String> {
    if value.trim().is_empty() {
        None
    } else {
        Some(value)
    }
}
