#[cfg(all(any(target_os = "android", target_os = "ios"), feature = "desktop"))]
compile_error!(
    "Android e iOS devem ser compilados somente com a feature `mobile`; recursos `desktop` não podem ser ativados no alvo mobile."
);

mod app_state;
mod bootstrap;
mod db;
mod legacy_data;
mod migrations;
mod models;
mod security;
mod runtime_config;
mod net_bind;
#[allow(dead_code)]
mod core;
#[allow(dead_code)]
pub mod internal_api;
#[allow(dead_code)]
pub mod native_webhook;
#[allow(dead_code)]
pub mod native_websocket;
#[allow(dead_code)]
mod integrations;
#[allow(dead_code)]
mod service;
mod storage_contract;
#[allow(dead_code)]
pub mod cli;
pub mod deployer;

mod commands {
    #[cfg(any(feature = "desktop", feature = "mobile"))]
    pub mod access;
    #[cfg(any(feature = "desktop", feature = "mobile"))]
    pub mod app;
    pub mod auth;
    #[cfg(any(feature = "desktop", feature = "mobile"))]
    pub mod companies;
    pub mod entities;
    #[cfg(any(feature = "desktop", feature = "mobile"))]
    pub mod licensing;
    #[cfg(any(feature = "desktop", feature = "mobile"))]
    pub mod support;
    #[cfg(any(feature = "desktop", feature = "mobile"))]
    pub mod integrations;
    #[cfg(feature = "desktop")]
    pub mod runtime;
    #[cfg(feature = "desktop")]
    pub mod webhook;
    #[cfg(feature = "desktop")]
    pub mod websocket;
}

#[cfg(any(feature = "desktop", feature = "mobile"))]
use app_state::SharedState;
#[cfg(any(feature = "desktop", feature = "mobile"))]
use tauri::Manager;

#[cfg(feature = "desktop")]
pub fn run() {
    let _ = crate::runtime_config::init_env_file(None);

    let builder = tauri::Builder::default();

    builder
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if is_tray_enabled() && close_to_tray() {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .manage(SharedState::new())
        .setup(|app| {
            let state = app.state::<SharedState>();
            let _ = crate::runtime_config::init_env_file(Some(state.inner()));
            state.init().map_err(|err| -> Box<dyn std::error::Error> {
                Box::new(std::io::Error::other(err))
            })?;

            if let Some(window) = app.get_webview_window("main") {
                let _ = window.maximize();
                let _ = window.set_focus();
            }

            if is_tray_enabled() {
                setup_tray(app)?;
            }

            // Nenhum serviço de rede deve bloquear a criação da janela Tauri.
            // A UI monta primeiro; API/Webport/Webhook/WebSocket sobem em segundo plano,
            // com locks internos para evitar duas rotas tentando abrir a mesma porta.
            start_runtime_services_background(state.inner().clone());

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            deployer::desktop::pige360_embedded_agent_status,
            deployer::desktop::pige360_distribution_list,
            deployer::desktop::pige360_test_connection,
            deployer::desktop::pige360_deploy,
            commands::app::app_bootstrap,
            commands::app::app_meta,
            commands::app::system_info,
            commands::app::system_set_data_dir,
            commands::app::app_log_write,
            commands::app::app_log_list,
            commands::app::app_log_clear,
            commands::auth::auth_login,
            commands::auth::auth_restore,
            commands::auth::auth_logout,
            commands::auth::auth_change_password,
            commands::access::permission_catalog,
            commands::access::profile_list,
            commands::access::profile_get,
            commands::access::profile_save,
            commands::access::profile_delete,
            commands::access::user_list,
            commands::access::user_get,
            commands::access::user_policy_get,
            commands::access::user_policy_save,
            commands::access::user_save,
            commands::access::user_delete,
            commands::companies::company_list,
            commands::companies::company_get,
            commands::companies::company_save,
            commands::companies::company_delete,
            commands::companies::company_lookup_cnpj,
            commands::companies::company_lookup_ie,
            commands::entities::entity_list,
            commands::entities::entity_save,
            commands::entities::entity_delete,
            commands::entities::combo_list,
            commands::entities::entity_provider_list,
            commands::entities::provider_entity_list,
            commands::entities::provider_entity_get,
            commands::entities::provider_entity_create,
            commands::entities::provider_entity_update,
            commands::entities::provider_entity_delete,
            commands::licensing::licensing_status,
            commands::licensing::licensing_load_settings,
            commands::licensing::licensing_save_settings,
            commands::licensing::licensing_device_info,
            commands::licensing::licensing_check_runtime,
            commands::licensing::licensing_start_trial,
            commands::support::support_guard_status,
            commands::support::support_guard_provision,
            commands::support::support_guard_enable_totp,
            commands::support::support_guard_unlock,
            commands::integrations::integration_list,
            commands::integrations::integration_save,
            commands::integrations::integration_delete,
            commands::integrations::integration_test,
            commands::integrations::integration_logs,
            commands::runtime::internal_api_status,
            commands::runtime::internal_api_start,
            commands::runtime::internal_api_stop,
            commands::runtime::internal_api_restart,
            commands::runtime::internal_api_test_port,
            commands::runtime::internal_api_test,
            commands::runtime::web_proxy_restart,
            commands::runtime::web_proxy_stop,
            commands::runtime::web_proxy_start,
            commands::runtime::web_proxy_status,
            commands::webhook::webhook_status,
            commands::webhook::webhook_start,
            commands::webhook::webhook_stop,
            commands::webhook::webhook_restart,
            commands::webhook::webhook_list_events,
            commands::webhook::webhook_clear_events,
            commands::webhook::webhook_test_receive,
            commands::websocket::websocket_status,
            commands::websocket::websocket_start,
            commands::websocket::websocket_stop,
            commands::websocket::websocket_restart,
            commands::websocket::websocket_list_clients,
            commands::websocket::websocket_broadcast_test,
            commands::runtime::runtime_settings_load,
            commands::runtime::runtime_settings_save,
            commands::runtime::runtime_env_example,
            commands::runtime::startup_with_windows_set,
            commands::runtime::app_service_install,
            commands::runtime::app_service_uninstall,
            commands::runtime::app_service_start,
            commands::runtime::app_service_stop,
            commands::runtime::app_service_restart,
            commands::runtime::app_service_status,
            commands::runtime::open_print_preview,
            commands::runtime::tray_status,
            commands::runtime::tray_restore_window,
            commands::runtime::tray_exit_app,
        ])
        .run(tauri::generate_context!())
        .expect("erro ao executar a aplicação Tauri");
}

#[cfg(all(feature = "mobile", not(feature = "desktop")))]
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let _ = crate::runtime_config::init_env_file(None);

    tauri::Builder::default()
        .manage(SharedState::new())
        .setup(|app| {
            let state = app.state::<SharedState>();
            let data_dir =
                app.path()
                    .app_local_data_dir()
                    .map_err(|error| -> Box<dyn std::error::Error> {
                        Box::new(std::io::Error::other(format!(
                            "Falha ao resolver o diretório local privado do dispositivo: {error}"
                        )))
                    })?;
            state
                .init_with_data_dir(data_dir)
                .map_err(|error| -> Box<dyn std::error::Error> {
                    Box::new(std::io::Error::other(error))
                })?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::app::app_bootstrap,
            commands::app::app_meta,
            commands::app::system_info,
            commands::app::system_set_data_dir,
            commands::app::app_log_write,
            commands::app::app_log_list,
            commands::app::app_log_clear,
            commands::auth::auth_login,
            commands::auth::auth_restore,
            commands::auth::auth_logout,
            commands::auth::auth_change_password,
            commands::access::permission_catalog,
            commands::access::profile_list,
            commands::access::profile_get,
            commands::access::profile_save,
            commands::access::profile_delete,
            commands::access::user_list,
            commands::access::user_get,
            commands::access::user_policy_get,
            commands::access::user_policy_save,
            commands::access::user_save,
            commands::access::user_delete,
            commands::companies::company_list,
            commands::companies::company_get,
            commands::companies::company_save,
            commands::companies::company_delete,
            commands::companies::company_lookup_cnpj,
            commands::companies::company_lookup_ie,
            commands::entities::entity_list,
            commands::entities::entity_save,
            commands::entities::entity_delete,
            commands::entities::combo_list,
            commands::entities::entity_provider_list,
            commands::entities::provider_entity_list,
            commands::entities::provider_entity_get,
            commands::entities::provider_entity_create,
            commands::entities::provider_entity_update,
            commands::entities::provider_entity_delete,
            commands::licensing::licensing_status,
            commands::licensing::licensing_load_settings,
            commands::licensing::licensing_save_settings,
            commands::licensing::licensing_device_info,
            commands::licensing::licensing_check_runtime,
            commands::licensing::licensing_start_trial,
            commands::support::support_guard_status,
            commands::support::support_guard_provision,
            commands::support::support_guard_enable_totp,
            commands::support::support_guard_unlock,
            commands::integrations::integration_list,
            commands::integrations::integration_save,
            commands::integrations::integration_delete,
            commands::integrations::integration_test,
            commands::integrations::integration_logs,
        ])
        .run(tauri::generate_context!())
        .expect("erro ao executar a aplicação Tauri mobile");
}

#[cfg(feature = "desktop")]
fn start_runtime_services_background(state: SharedState) {
    std::thread::Builder::new()
        .name("pige360-deployer-runtime-services-orchestrator".to_string())
        .spawn(move || {
            if should_start_internal_api(&state) {
                match crate::runtime_config::resolve_internal_api_config(&state) {
                    Ok(config) => {
                        if let Err(err) =
                            crate::internal_api::server::start_background(state.clone(), config)
                        {
                            eprintln!("Falha ao iniciar API interna: {err}");
                        }
                    }
                    Err(err) => eprintln!("Falha ao resolver configuração da API interna: {err}"),
                }
            }

            if should_start_web_proxy(&state) {
                if let Err(err) = crate::internal_api::web_server::start_background(state.clone()) {
                    eprintln!("Falha ao iniciar Webport/proxy: {err}");
                }
            }

            if should_auto_start_webhook_service(&state) {
                let _ = crate::native_webhook::server::start_background(state.clone());
            }

            if should_auto_start_websocket_service(&state) {
                let _ = crate::native_websocket::server::start_background(state);
            }
        })
        .map(|_| ())
        .unwrap_or_else(|err| eprintln!("Falha ao iniciar orquestrador de serviços: {err}"));
}

#[cfg(feature = "desktop")]
fn setup_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    use tauri::menu::{Menu, MenuItem};
    use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};

    let restore = MenuItem::with_id(app, "restore", "Restaurar", true, None::<&str>)?;
    let api_start = MenuItem::with_id(app, "api_start", "Iniciar API interna", true, None::<&str>)?;
    let api_restart = MenuItem::with_id(
        app,
        "api_restart",
        "Reiniciar API interna",
        true,
        None::<&str>,
    )?;
    let api_stop = MenuItem::with_id(app, "api_stop", "Parar API interna", true, None::<&str>)?;
    let webhook_start =
        MenuItem::with_id(app, "webhook_start", "Iniciar Webhooks", true, None::<&str>)?;
    let websocket_start = MenuItem::with_id(
        app,
        "websocket_start",
        "Iniciar WebSocket",
        true,
        None::<&str>,
    )?;
    let quit = MenuItem::with_id(app, "quit", "Sair definitivamente", true, None::<&str>)?;
    let menu = Menu::with_items(
        app,
        &[
            &restore,
            &api_start,
            &api_restart,
            &api_stop,
            &webhook_start,
            &websocket_start,
            &quit,
        ],
    )?;

    let mut builder = TrayIconBuilder::with_id("main-tray")
        .tooltip(runtime_app_name())
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                if let Some(window) = tray.app_handle().get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
        })
        .on_menu_event(|app, event| match event.id().as_ref() {
            "restore" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
            "api_start" => {
                let state = app.state::<SharedState>();
                if let Ok(config) =
                    crate::runtime_config::resolve_internal_api_config(state.inner())
                {
                    let _ = crate::internal_api::server::start_background(
                        state.inner().clone(),
                        config,
                    );
                }
            }
            "api_restart" => {
                let _ = crate::internal_api::server::stop_background();
                let state = app.state::<SharedState>();
                if let Ok(config) =
                    crate::runtime_config::resolve_internal_api_config(state.inner())
                {
                    let _ = crate::internal_api::server::start_background(
                        state.inner().clone(),
                        config,
                    );
                }
            }
            "api_stop" => {
                let _ = crate::internal_api::server::stop_background();
            }
            "webhook_start" => {
                let state = app.state::<SharedState>();
                let _ = crate::native_webhook::server::start_background(state.inner().clone());
            }
            "websocket_start" => {
                let state = app.state::<SharedState>();
                let _ = crate::native_websocket::server::start_background(state.inner().clone());
            }
            "quit" => app.exit(0),
            _ => {}
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    let _tray = builder.build(app)?;

    Ok(())
}

#[cfg(feature = "desktop")]
fn runtime_app_name() -> String {
    std::env::var("PIGE360_DEPLOYER_NAME")
        .or_else(|_| std::env::var("APP_NAME"))
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "PIGE360 Deployer".to_string())
}

#[cfg(feature = "desktop")]
fn env_bool(key: &str, default: bool) -> bool {
    std::env::var(key)
        .ok()
        .map(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "1" | "true" | "yes" | "on"
            )
        })
        .unwrap_or(default)
}

#[cfg(feature = "desktop")]
fn is_tray_enabled() -> bool {
    env_bool("PIGE360_DEPLOYER_TRAY_ENABLED", true)
}

#[cfg(feature = "desktop")]
fn close_to_tray() -> bool {
    env_bool("PIGE360_DEPLOYER_TRAY_CLOSE_TO_TRAY", false)
}

#[cfg(feature = "desktop")]
fn should_start_internal_api(state: &SharedState) -> bool {
    let settings = crate::runtime_config::load_settings(state)
        .map(|payload| payload.settings)
        .unwrap_or_default();
    settings.internal_api_auto_start
        && !env_bool("PIGE360_DEPLOYER_API_DISABLED", false)
        && !env_bool("APP_API_DISABLED", false)
        && !env_bool("PIGE360_DEPLOYER_INTERNAL_API_DISABLED", false)
}

#[cfg(feature = "desktop")]
fn should_start_web_proxy(state: &SharedState) -> bool {
    let settings = crate::runtime_config::load_settings(state)
        .map(|payload| payload.settings)
        .unwrap_or_default();
    let enabled = settings.local_web_enabled
        && !env_bool("PIGE360_DEPLOYER_WEB_DISABLED", false)
        && !env_bool("APP_WEB_DISABLED", false);
    let requested = settings.local_web_auto_start
        || settings.services_auto_start
        || env_bool("PIGE360_DEPLOYER_SERVICES_AUTO_START", false)
        || arg_present(&[
            "--start-web-proxy",
            "--web-proxy-auto-start",
            "--start-webport",
            "--webport-auto-start",
            "--start-services",
            "--services-auto-start",
            "--auto-start-services",
        ]);
    enabled && requested
}

#[cfg(feature = "desktop")]
fn should_auto_start_webhook_service(state: &SharedState) -> bool {
    let settings = crate::runtime_config::load_settings(state)
        .map(|payload| payload.settings)
        .unwrap_or_default();
    let enabled = settings.webhook_enabled
        && !env_bool("PIGE360_DEPLOYER_WEBHOOK_DISABLED", false)
        && !env_bool("APP_WEBHOOK_DISABLED", false);
    let requested = settings.webhook_auto_start
        || settings.services_auto_start
        || env_bool("PIGE360_DEPLOYER_SERVICES_AUTO_START", false)
        || arg_present(&[
            "--start-webhook",
            "--webhook-auto-start",
            "--webhook",
            "--start-services",
            "--services-auto-start",
            "--auto-start-services",
        ]);
    enabled && requested
}

#[cfg(feature = "desktop")]
fn should_auto_start_websocket_service(state: &SharedState) -> bool {
    let settings = crate::runtime_config::load_settings(state)
        .map(|payload| payload.settings)
        .unwrap_or_default();
    let enabled = settings.websocket_enabled
        && !env_bool("PIGE360_DEPLOYER_WEBSOCKET_DISABLED", false)
        && !env_bool("APP_WEBSOCKET_DISABLED", false);
    let requested = settings.websocket_auto_start
        || settings.services_auto_start
        || env_bool("PIGE360_DEPLOYER_SERVICES_AUTO_START", false)
        || arg_present(&[
            "--start-websocket",
            "--websocket-auto-start",
            "--websocket",
            "--start-services",
            "--services-auto-start",
            "--auto-start-services",
        ]);
    enabled && requested
}

#[cfg(feature = "desktop")]
fn arg_present(names: &[&str]) -> bool {
    std::env::args().any(|arg| names.iter().any(|name| arg.eq_ignore_ascii_case(name)))
}
