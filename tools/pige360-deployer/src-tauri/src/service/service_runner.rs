#[derive(Debug, Clone)]
pub enum ServiceCommand {
    Install,
    Uninstall,
    Start,
    Stop,
    Restart,
    Status,
}

pub fn parse_command(value: &str) -> ServiceCommand {
    match value {
        "install" => ServiceCommand::Install,
        "uninstall" => ServiceCommand::Uninstall,
        "start" => ServiceCommand::Start,
        "stop" => ServiceCommand::Stop,
        "restart" => ServiceCommand::Restart,
        _ => ServiceCommand::Status,
    }
}
