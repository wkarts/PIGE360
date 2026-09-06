use std::io;
use std::net::{IpAddr, Ipv4Addr, SocketAddr, TcpListener, UdpSocket};
use std::time::Duration;

#[derive(Debug)]
pub struct PreparedListener {
    pub listener: TcpListener,
    pub bind_host: String,
    pub public_host: String,
    pub port: u16,
    pub note: Option<String>,
}

/// Prepara um listener respeitando porta fixa.
///
/// Regra importante para Windows:
/// - 0.0.0.0:PORTA pode falhar com WSAEADDRINUSE se a mesma porta já estiver
///   presa em 127.0.0.1 por uma instância anterior.
/// - nesse caso, para não trocar a porta e não quebrar LAN, tentamos a mesma
///   PORTA no IPv4 principal da placa de rede, por exemplo 192.168.x.x:PORTA.
///
/// Isso não é fallback de porta. É fallback de interface/bind usando a mesma porta.
pub fn bind_fixed_service_listener(host: &str, port: u16) -> io::Result<PreparedListener> {
    let normalized_host = normalize_bind_host(host);
    let primary_addr = parse_addr(&normalized_host, port)?;

    match bind_with_retry(primary_addr) {
        Ok(listener) => Ok(PreparedListener {
            listener,
            bind_host: normalized_host.clone(),
            public_host: public_host_for_bind(&normalized_host),
            port,
            note: None,
        }),
        Err(primary_err)
            if primary_err.kind() == io::ErrorKind::AddrInUse
                && is_wildcard_host(&normalized_host) =>
        {
            match detect_primary_lan_ipv4() {
                Some(lan_host) if !lan_host.eq_ignore_ascii_case("127.0.0.1") => {
                    let lan_addr = parse_addr(&lan_host, port)?;
                    match bind_with_retry(lan_addr) {
                        Ok(listener) => Ok(PreparedListener {
                            listener,
                            bind_host: lan_host.clone(),
                            public_host: lan_host.clone(),
                            port,
                            note: Some(format!(
                                "Bind em {normalized_host}:{port} estava indisponível; publicado na mesma porta pela interface de rede {lan_host}:{port}."
                            )),
                        }),
                        Err(lan_err) => Err(io::Error::new(
                            lan_err.kind(),
                            format!(
                                "{primary_err}; tentativa alternativa na interface LAN {lan_host}:{port} também falhou: {lan_err}"
                            ),
                        )),
                    }
                }
                _ => Err(primary_err),
            }
        }
        Err(err) => Err(err),
    }
}

pub fn normalize_bind_host(host: &str) -> String {
    let value = host.trim();
    if value.is_empty() || value.eq_ignore_ascii_case("localhost") {
        "127.0.0.1".to_string()
    } else {
        value.to_string()
    }
}

pub fn public_host_for_bind(host: &str) -> String {
    match host.trim() {
        "0.0.0.0" | "::" | "[::]" | "" => "127.0.0.1".to_string(),
        "localhost" => "127.0.0.1".to_string(),
        value => value.to_string(),
    }
}

pub fn is_wildcard_host(host: &str) -> bool {
    matches!(host.trim(), "0.0.0.0" | "::" | "[::]")
}

pub fn detect_primary_lan_ipv4() -> Option<String> {
    let socket = UdpSocket::bind((Ipv4Addr::UNSPECIFIED, 0)).ok()?;
    // UDP connect não envia pacote; ele apenas força o SO a escolher a rota/interface.
    let _ = socket.connect((Ipv4Addr::new(8, 8, 8, 8), 80));
    let local = socket.local_addr().ok()?;
    match local.ip() {
        IpAddr::V4(ip) if !ip.is_loopback() && !ip.is_unspecified() => Some(ip.to_string()),
        _ => None,
    }
}

fn parse_addr(host: &str, port: u16) -> io::Result<SocketAddr> {
    format!("{host}:{port}")
        .parse::<SocketAddr>()
        .map_err(|err| {
            io::Error::new(
                io::ErrorKind::InvalidInput,
                format!("Endereço inválido {host}:{port}: {err}"),
            )
        })
}

fn bind_with_retry(addr: SocketAddr) -> io::Result<TcpListener> {
    let mut last_error: Option<io::Error> = None;
    for attempt in 0..10 {
        match TcpListener::bind(addr) {
            Ok(listener) => return Ok(listener),
            Err(err) if err.kind() == io::ErrorKind::AddrInUse => {
                last_error = Some(err);
                std::thread::sleep(Duration::from_millis(180 + attempt * 70));
            }
            Err(err) => return Err(err),
        }
    }
    Err(last_error.unwrap_or_else(|| io::Error::new(io::ErrorKind::AddrInUse, "porta ocupada")))
}
