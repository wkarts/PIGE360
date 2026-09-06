export type AuthMethod = "key" | "agent";
export type DistributionChannel = "develop" | "prerelease" | "stable";
export type DeploymentEnvironment = "develop" | "production";
export type DeploymentPlatform = "compose" | "dockge" | "cloudpanel" | "portainer";
export type DeploymentAction = "plan" | "prepare" | "apply" | "rollback";

export interface ConnectionInput {
  host: string;
  port: number;
  user: string;
  auth_method: AuthMethod;
  key_file?: string | null;
  known_hosts_file?: string | null;
  accept_new_host_key: boolean;
  sudo: boolean;
  connect_timeout_seconds: number;
}

export interface DeployRequest {
  protocol_version: number;
  repository: string;
  channel: DistributionChannel;
  environment: DeploymentEnvironment;
  requested_version: string;
  platform: DeploymentPlatform;
  directory: string;
  action: DeploymentAction;
  rollback_tag?: string | null;
  github_token?: string | null;
  registry_user?: string | null;
  registry_token?: string | null;
  env_input?: string | null;
  env_overrides: Record<string, string>;
  secret_inputs: Record<string, string>;
  wait_seconds: number;
}

export interface DesktopDeployRequest {
  connection: ConnectionInput;
  deploy: DeployRequest;
  env_input_path?: string | null;
}

export interface ServerPreflight {
  os: string;
  architecture: string;
  kernel: string;
  docker_available: boolean;
  docker_version?: string | null;
  compose_available: boolean;
  compose_version?: string | null;
  cloudpanel_available: boolean;
  disk_available_bytes?: number | null;
  effective_user: string;
}

export interface ConnectionTestResult {
  known_host_status: string;
  fingerprint_sha256?: string | null;
  host_key_type?: string | null;
  server: ServerPreflight;
}

export interface DistributionDescriptor {
  channel: DistributionChannel;
  version: string;
  reference: string;
  commit: string;
  prerelease: boolean;
  published_at?: string | null;
}

export interface AgentEvent {
  protocol_version: number;
  kind: "info" | "warning" | "error" | "result";
  step: string;
  message: string;
  progress?: number | null;
  data?: unknown;
}

export interface AgentStatus {
  amd64?: { embedded: boolean; bytes: number; sha256?: string | null };
  supported_architectures?: string[];
}
