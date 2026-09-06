use std::sync::Arc;

use generic_license_tauri::{
    commands::license_check,
    models::LicenseConfig,
    GenericLicenseService,
};

fn build_license_config() -> LicenseConfig {
    LicenseConfig {
        base_url: std::env::var("LICENSE_API_BASE_URL").unwrap_or_default(),
        api_token: std::env::var("LICENSE_API_TOKEN").ok(),
        cache_namespace: "erp-desktop".to_string(),
        ..Default::default()
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let service = Arc::new(GenericLicenseService::new(build_license_config()));

    tauri::Builder::default()
        .manage(service)
        .invoke_handler(tauri::generate_handler![license_check])
        .run(tauri::generate_context!())
        .expect("erro ao executar aplicação");
}
