pub fn systemd_unit(app_name: &str, exec_path: &str) -> String {
    format!(
        r#"[Unit]
Description={app_name} Server
After=network.target

[Service]
ExecStart={exec_path} --mode=headless-api
Restart=always
Environment=APP_ENV=production

[Install]
WantedBy=multi-user.target
"#
    )
}
