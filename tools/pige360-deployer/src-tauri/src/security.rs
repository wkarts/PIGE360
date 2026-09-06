use argon2::{
    password_hash::{PasswordHash, PasswordHasher, PasswordVerifier, SaltString},
    Argon2,
};
use base64::{engine::general_purpose::STANDARD as BASE64_STANDARD, Engine};
use data_encoding::BASE32_NOPAD;
use hmac::{Hmac, Mac};
use rand::{distributions::Alphanumeric, rngs::OsRng, Rng, RngCore};
use sha1::Sha1;
use sha2::{Digest, Sha256};

pub fn hash_password(password: &str) -> Result<String, String> {
    let salt = SaltString::generate(&mut OsRng);
    Argon2::default()
        .hash_password(password.as_bytes(), &salt)
        .map(|hash| hash.to_string())
        .map_err(|err| format!("Falha ao gerar hash da senha: {err}"))
}

pub fn verify_password(password: &str, password_hash: &str) -> Result<bool, String> {
    let parsed_hash = PasswordHash::new(password_hash)
        .map_err(|err| format!("Falha ao interpretar hash armazenado: {err}"))?;

    Ok(Argon2::default()
        .verify_password(password.as_bytes(), &parsed_hash)
        .is_ok())
}

pub fn machine_key() -> String {
    let host = std::env::var("COMPUTERNAME")
        .or_else(|_| std::env::var("HOSTNAME"))
        .unwrap_or_else(|_| "unknown-host".to_string());
    let user = std::env::var("USERNAME")
        .or_else(|_| std::env::var("USER"))
        .unwrap_or_else(|_| "unknown-user".to_string());
    format!("{host}:{user}")
}

fn derive_secret(seed: &str) -> Vec<u8> {
    let mut hasher = Sha256::new();
    hasher.update(b"PIGE360-DEPLOYER-LIC");
    hasher.update(seed.as_bytes());
    hasher.finalize().to_vec()
}

pub fn encrypt_text(seed: &str, plain: &str) -> String {
    let secret = derive_secret(seed);
    let bytes = plain
        .as_bytes()
        .iter()
        .enumerate()
        .map(|(idx, byte)| byte ^ secret[idx % secret.len()])
        .collect::<Vec<_>>();
    BASE64_STANDARD.encode(bytes)
}

pub fn decrypt_text(seed: &str, cipher: &str) -> Result<String, String> {
    let secret = derive_secret(seed);
    let bytes = BASE64_STANDARD
        .decode(cipher)
        .map_err(|err| format!("Falha ao decodificar conteúdo criptografado: {err}"))?;
    let plain = bytes
        .iter()
        .enumerate()
        .map(|(idx, byte)| byte ^ secret[idx % secret.len()])
        .collect::<Vec<_>>();
    String::from_utf8(plain)
        .map_err(|err| format!("Falha ao reconstruir texto criptografado: {err}"))
}

pub fn integrity_hash(seed: &str, payload: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(seed.as_bytes());
    hasher.update(payload.as_bytes());
    format!("{:x}", hasher.finalize())
}

pub fn generate_support_secret() -> String {
    OsRng
        .sample_iter(&Alphanumeric)
        .take(32)
        .map(char::from)
        .collect::<String>()
}

pub fn generate_recovery_codes() -> Vec<String> {
    (0..8)
        .map(|_| {
            OsRng
                .sample_iter(&Alphanumeric)
                .take(10)
                .map(char::from)
                .collect::<String>()
        })
        .collect()
}

pub fn generate_totp_secret() -> String {
    let mut bytes = [0u8; 20];
    OsRng.fill_bytes(&mut bytes);
    BASE32_NOPAD.encode(&bytes)
}

pub fn build_otpauth_url(secret: &str, account_label: &str, issuer: &str) -> String {
    let label = account_label.replace(' ', "%20").replace('@', "%40");
    let issuer_enc = issuer.replace(' ', "%20");
    format!(
        "otpauth://totp/{}?secret={}&issuer={}&algorithm=SHA1&digits=6&period=30",
        label, secret, issuer_enc
    )
}

fn hotp(secret: &[u8], counter: u64) -> Result<u32, String> {
    let mut mac = Hmac::<Sha1>::new_from_slice(secret)
        .map_err(|err| format!("Falha ao inicializar HMAC do TOTP: {err}"))?;
    mac.update(&counter.to_be_bytes());
    let result = mac.finalize().into_bytes();
    let offset = (result[19] & 0x0f) as usize;
    let binary = ((u32::from(result[offset]) & 0x7f) << 24)
        | (u32::from(result[offset + 1]) << 16)
        | (u32::from(result[offset + 2]) << 8)
        | u32::from(result[offset + 3]);
    Ok(binary % 1_000_000)
}

pub fn verify_totp_code(secret_base32: &str, code: &str) -> Result<bool, String> {
    let normalized = code.trim().replace(' ', "");
    if normalized.len() != 6 || !normalized.chars().all(|c| c.is_ascii_digit()) {
        return Ok(false);
    }
    let expected = normalized
        .parse::<u32>()
        .map_err(|err| format!("Falha ao interpretar código TOTP: {err}"))?;
    let secret = BASE32_NOPAD
        .decode(secret_base32.trim().as_bytes())
        .map_err(|err| format!("Falha ao decodificar secret TOTP: {err}"))?;
    let unix = chrono::Utc::now().timestamp().div_euclid(30);
    for delta in -1..=1 {
        let counter = (unix + delta) as u64;
        if hotp(&secret, counter)? == expected {
            return Ok(true);
        }
    }
    Ok(false)
}
