#[cfg(target_os = "linux")]
pub mod agent;
pub mod catalog;
pub mod error;
pub mod github;
pub mod protocol;

#[cfg(feature = "desktop")]
pub mod desktop;
