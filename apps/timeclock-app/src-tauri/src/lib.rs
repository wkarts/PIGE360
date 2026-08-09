#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            pige360_native_bridge::secure_session_put,
            pige360_native_bridge::secure_session_get,
            pige360_native_bridge::secure_session_delete,
            pige360_native_bridge::offline_initialize,
            pige360_native_bridge::offline_outbox_enqueue,
            pige360_native_bridge::offline_outbox_pending,
            pige360_native_bridge::offline_outbox_apply_result,
            pige360_native_bridge::offline_cache_get,
            pige360_native_bridge::offline_cache_put,
            pige360_native_bridge::fiscal_snapshot_verify,
            pige360_native_bridge::print_enqueue,
            pige360_native_bridge::native_wipe_user,
        ])
        .run(tauri::generate_context!())
        .expect("falha ao executar PIGE360");
}
