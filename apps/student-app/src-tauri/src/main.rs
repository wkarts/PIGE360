#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[path = "../../../../rust/crates/native-bridge/src/tauri_commands.rs"]
mod tauri_commands;

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            tauri_commands::secure_session_put,
            tauri_commands::secure_session_get,
            tauri_commands::secure_session_delete,
            tauri_commands::offline_initialize,
            tauri_commands::offline_outbox_enqueue,
            tauri_commands::offline_outbox_pending,
            tauri_commands::offline_outbox_apply_result,
            tauri_commands::offline_cache_get,
            tauri_commands::offline_cache_put,
            tauri_commands::fiscal_snapshot_verify,
            tauri_commands::print_enqueue,
            tauri_commands::native_wipe_user,
        ])
        .run(tauri::generate_context!())
        .expect("falha ao executar PIGE360");
}
