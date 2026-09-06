use pige360_deployer_lib::deployer::agent;
use pige360_deployer_lib::deployer::protocol::{AgentEvent, DeployRequest, PROTOCOL_VERSION};
use std::io::{self, Read};

fn main() {
    let code = match run() {
        Ok(code) => code,
        Err(error) => {
            println!("{}", serde_json::to_string(&AgentEvent::error("fatal", error.to_string())).unwrap_or_default());
            2
        }
    };
    std::process::exit(code);
}

fn run() -> Result<i32, Box<dyn std::error::Error>> {
    match std::env::args().nth(1).as_deref() {
        Some("self-test") => {
            println!("{}", serde_json::json!({"ok": true, "version": env!("CARGO_PKG_VERSION"), "protocol": PROTOCOL_VERSION, "os": std::env::consts::OS, "arch": std::env::consts::ARCH}));
            Ok(0)
        }
        Some("execute") => {
            let mut input = String::new();
            io::stdin().take(2_000_001).read_to_string(&mut input)?;
            if input.len() > 2_000_000 { return Err("Solicitação excede 2 MB.".into()); }
            let request: DeployRequest = serde_json::from_str(&input)?;
            let receipt = agent::execute(request)?;
            println!("{}", serde_json::to_string(&AgentEvent::result("complete", "Operação PIGE360 concluída.", serde_json::to_value(&receipt)?))?);
            Ok(0)
        }
        _ => Err("Uso: pige360-deploy-agent <self-test|execute>".into()),
    }
}
