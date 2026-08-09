#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    pige360_native_bridge::configure(tauri::Builder::default())
        .run(tauri::generate_context!())
        .expect("falha ao executar PIGE360");
}
