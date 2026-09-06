<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import AppSwitch from "../components/AppSwitch.vue";
import BasePage from "../components/base/BasePage.vue";
import {
  checkLicensingRuntime,
  enableSupportGuardTotp,
  getLicensingDeviceInfo,
  getLicensingStatus,
  getSupportGuardStatus,
  loadLicensingSettings,
  provisionSupportGuard,
  saveLicensingSettings,
  startTrialLicense,
  unlockSupportGuard,
} from "../services/crud";
import { logAppError, logAppInfo } from "../services/logger";
import { useSessionStore } from "../stores/session";

const session = useSessionStore();
const loading = ref(false);
const saving = ref(false);
const checking = ref(false);
const trialLoading = ref(false);
const provisioning = ref(false);
const unlocking = ref(false);
const enablingTotp = ref(false);
const message = ref("");
const error = ref("");
const status = ref<Record<string, unknown> | null>(null);
const runtime = ref<Record<string, unknown> | null>(null);
const deviceInfo = ref<Record<string, unknown> | null>(null);
const settings = ref<Record<string, unknown>>({});
const supportGuard = ref<Record<string, unknown>>({});
const unlockToken = ref("");
const lastProvision = ref<Record<string, unknown> | null>(null);
const authForm = ref({ currentPassword: "", supportSecret: "", totpCode: "" });

const empresaId = computed(() => session.activeCompanyId ?? session.user?.company_ids?.[0] ?? null);
const companyName = computed(() => String(status.value?.empresa_nome || runtime.value?.empresa_nome || "-"));
const companyDocument = computed(() => String(status.value?.cnpj || runtime.value?.cnpj || "-"));
const localLicense = computed(() => ((status.value?.license as Record<string, unknown> | null) || (runtime.value?.local_license as Record<string, unknown> | null) || null));
const onlineDecision = computed(() => (runtime.value?.decision as Record<string, unknown> | null) || null);
const disabledMode = computed({
  get: () => Boolean(settings.value.licensing_disabled),
  set: (value: boolean) => { settings.value.licensing_disabled = value; }
});
const isMaster = computed(() => session.isMaster);
const settingsProtected = computed(() => Boolean(settings.value.protected) || !unlockToken.value);
const guardConfigured = computed(() => Boolean(supportGuard.value.configured));
const guardTotpEnabled = computed(() => Boolean(Number(supportGuard.value.totp_enabled ?? 0) === 1 || supportGuard.value.totp_enabled === true));
const provisionRecoveryCodes = computed(() => Array.isArray(lastProvision.value?.recovery_codes) ? (lastProvision.value?.recovery_codes as unknown[]).map((item) => String(item)).join(", ") : "");

function stringValue(key: string) {
  return String(settings.value[key] ?? "");
}

function setString(key: string, value: string) {
  settings.value[key] = value;
}

function setBool(key: string, value: boolean) {
  settings.value[key] = value;
}

async function loadPage() {
  if (!session.sessionToken) return;
  loading.value = true;
  error.value = "";
  try {
    const [settingsData, statusData, deviceData, guardData] = await Promise.all([
      loadLicensingSettings(session.sessionToken, unlockToken.value || null),
      getLicensingStatus(session.sessionToken, empresaId.value),
      getLicensingDeviceInfo(session.sessionToken),
      isMaster.value ? getSupportGuardStatus(session.sessionToken) : Promise.resolve({}),
    ]);
    settings.value = { ...settingsData };
    if (!settings.value.company_name && statusData.empresa_nome) settings.value.company_name = statusData.empresa_nome;
    if (!settings.value.company_document && statusData.cnpj) settings.value.company_document = statusData.cnpj;
    if (!settings.value.company_email) settings.value.company_email = "";
    status.value = statusData;
    deviceInfo.value = deviceData;
    supportGuard.value = guardData;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao carregar o licenciamento.";
    logAppError("licensing", "Falha ao carregar página de licenciamento.", { error: error.value });
  } finally {
    loading.value = false;
  }
}

async function saveSettingsAction() {
  if (!session.sessionToken || !unlockToken.value) {
    error.value = "Desbloqueie a área administrativa reforçada antes de salvar configurações sensíveis.";
    return;
  }
  saving.value = true;
  message.value = "";
  error.value = "";
  try {
    settings.value = await saveLicensingSettings(session.sessionToken, unlockToken.value, settings.value);
    message.value = "Configurações de licenciamento salvas com sucesso.";
    logAppInfo("licensing", "Configurações de licenciamento salvas.");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao salvar configurações de licenciamento.";
    logAppError("licensing", "Falha ao salvar configurações sensíveis de licenciamento.", { error: error.value });
  } finally {
    saving.value = false;
  }
}

async function runCheck() {
  checking.value = true;
  message.value = "";
  error.value = "";
  try {
    runtime.value = await checkLicensingRuntime(session.sessionToken!, empresaId.value);
    message.value = "Validação de licenciamento concluída.";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao validar licenciamento.";
  } finally {
    checking.value = false;
  }
}

async function activateTrial() {
  trialLoading.value = true;
  message.value = "";
  error.value = "";
  try {
    await startTrialLicense(session.sessionToken!, empresaId.value);
    message.value = "Licença de teste de 45 dias liberada com sucesso.";
    await loadPage();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao liberar licença de teste.";
  } finally {
    trialLoading.value = false;
  }
}

async function provisionGuard(forceRotate = false) {
  if (!session.sessionToken) return;
  provisioning.value = true;
  error.value = "";
  message.value = "";
  try {
    lastProvision.value = await provisionSupportGuard(session.sessionToken, forceRotate);
    message.value = forceRotate ? "Secret administrativo rotacionado." : "Proteção administrativa provisionada.";
    await loadPage();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao provisionar proteção administrativa.";
  } finally {
    provisioning.value = false;
  }
}

async function unlockGuard() {
  if (!session.sessionToken) return;
  unlocking.value = true;
  error.value = "";
  message.value = "";
  try {
    const result = await unlockSupportGuard(
      session.sessionToken,
      authForm.value.currentPassword,
      authForm.value.supportSecret,
      authForm.value.totpCode || null,
      "licensing",
    );
    unlockToken.value = String(result.unlock_token || "");
    message.value = `Acesso administrativo reforçado liberado até ${String(result.expires_at || "")}.`;
    await loadPage();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao desbloquear área administrativa.";
  } finally {
    unlocking.value = false;
  }
}

async function enableTotp() {
  if (!session.sessionToken) return;
  enablingTotp.value = true;
  error.value = "";
  message.value = "";
  try {
    await enableSupportGuardTotp(
      session.sessionToken,
      authForm.value.currentPassword,
      authForm.value.supportSecret,
      authForm.value.totpCode,
    );
    message.value = "TOTP administrativo ativado com sucesso.";
    await loadPage();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao ativar TOTP administrativo.";
  } finally {
    enablingTotp.value = false;
  }
}

watch(empresaId, async () => {
  runtime.value = null;
  await loadPage();
});

onMounted(loadPage);
</script>

<template>
  <BasePage title="Licenciamento" subtitle="Página dedicada de licenciamento com proteção administrativa reforçada, sem modal bloqueante." icon="key">
    <template #actions>
      <button class="secondary" :disabled="loading || checking" @click="loadPage">Atualizar</button>
      <button class="primary" :disabled="checking || loading" @click="runCheck">Validar licença</button>
    </template>
    <div class="grid page-gap licensing-page">

    <div v-if="message" class="alert success">{{ message }}</div>
    <div v-if="error" class="alert error">{{ error }}</div>

    <div class="grid columns-2 mobile-columns-1 licensing-grid">
      <div class="card grid page-gap">
        <div class="section-title">Empresa e contexto</div>
        <div class="info-grid">
          <div class="info-item"><strong>Empresa ativa</strong><code>{{ companyName }}</code></div>
          <div class="info-item"><strong>CNPJ</strong><code>{{ companyDocument }}</code></div>
          <div class="info-item"><strong>Dispositivo</strong><code>{{ deviceInfo?.station_name || status?.machine_key || '-' }}</code></div>
          <div class="info-item"><strong>Fingerprint</strong><code>{{ deviceInfo?.device_key || status?.machine_key || '-' }}</code></div>
        </div>
      </div>

      <div class="card grid page-gap">
        <div class="section-title">Licença local / teste</div>
        <div v-if="localLicense" class="info-grid">
          <div class="info-item"><strong>Tipo</strong><code>{{ localLicense.license_kind }}</code></div>
          <div class="info-item"><strong>Status</strong><code>{{ localLicense.status }}</code></div>
          <div class="info-item"><strong>Emissão</strong><code>{{ localLicense.issued_at }}</code></div>
          <div class="info-item"><strong>Validade</strong><code>{{ localLicense.expires_at }}</code></div>
        </div>
        <div v-else class="muted-text">Nenhuma licença local gravada para a empresa ativa.</div>
        <div class="actions wrap">
          <button class="primary" :disabled="trialLoading || !!localLicense" @click="activateTrial">Liberar teste 45 dias</button>
        </div>
      </div>
    </div>

    <div v-if="isMaster" class="card grid page-gap">
      <div class="section-title">Proteção administrativa reforçada</div>
      <div class="muted-text">
        Acesso a parâmetros de licenciamento, white-label e funções administrativas sensíveis exige senha atual,
        secret exclusivo de suporte por instalação e TOTP quando habilitado.
      </div>
      <div class="actions wrap">
        <button class="secondary" :disabled="provisioning" @click="provisionGuard(false)">Provisionar secret</button>
        <button class="secondary" :disabled="provisioning || !guardConfigured" @click="provisionGuard(true)">Rotacionar secret</button>
      </div>
      <div v-if="lastProvision" class="info-grid">
        <div class="info-item"><strong>Secret suporte</strong><code>{{ lastProvision.support_secret }}</code></div>
        <div class="info-item"><strong>Secret TOTP</strong><code>{{ lastProvision.totp_secret }}</code></div>
        <div class="info-item info-item-full"><strong>Otpauth URI</strong><code>{{ lastProvision.otpauth_url }}</code></div>
        <div class="info-item info-item-full"><strong>Recovery codes</strong><code>{{ provisionRecoveryCodes }}</code></div>
      </div>
      <div class="form-grid two-columns licensing-form-grid">
        <label>
          <span>Senha atual do admin/master</span>
          <input v-model="authForm.currentPassword" type="password" />
        </label>
        <label>
          <span>Secret de suporte</span>
          <input v-model="authForm.supportSecret" type="password" />
        </label>
        <label>
          <span>Código TOTP</span>
          <input v-model="authForm.totpCode" type="text" maxlength="6" placeholder="000000" />
        </label>
      </div>
      <div class="actions wrap">
        <button class="primary" :disabled="unlocking || !guardConfigured" @click="unlockGuard">Desbloquear área sensível</button>
        <button class="secondary" :disabled="enablingTotp || !guardConfigured || guardTotpEnabled" @click="enableTotp">Ativar TOTP</button>
      </div>
    </div>

    <div class="card grid page-gap">
      <div class="section-title">Configuração do componente genérico</div>
      <div class="muted-text" v-if="settingsProtected">
        Os parâmetros sensíveis estão protegidos. Desbloqueie a área administrativa reforçada para visualizar e alterar.
      </div>
      <div class="form-grid two-columns licensing-form-grid">
        <label>
          <span>Service URL</span>
          <input :value="stringValue('service_url')" :disabled="settingsProtected" @input="setString('service_url', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Instância / app slug</span>
          <input :value="stringValue('app_instance')" :disabled="settingsProtected" @input="setString('app_instance', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Razão social</span>
          <input :value="stringValue('company_name')" @input="setString('company_name', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>CNPJ</span>
          <input :value="stringValue('company_document')" @input="setString('company_document', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>E-mail da empresa</span>
          <input :value="stringValue('company_email')" @input="setString('company_email', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Estação</span>
          <input :value="stringValue('station_name')" @input="setString('station_name', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Validation mode</span>
          <input :value="stringValue('auto_register_validation_mode')" :disabled="settingsProtected" @input="setString('auto_register_validation_mode', ($event.target as HTMLInputElement).value)" />
        </label>
        <label>
          <span>Interface mode</span>
          <input :value="stringValue('auto_register_interface_mode')" :disabled="settingsProtected" @input="setString('auto_register_interface_mode', ($event.target as HTMLInputElement).value)" />
        </label>
      </div>
      <div class="checkbox-grid licensing-checkboxes">
        <AppSwitch :model-value="Boolean(settings.auto_register_machine)" label="Permitir auto cadastro de empresa/dispositivo" :disabled="settingsProtected" @update:model-value="setBool('auto_register_machine', $event)" />
        <AppSwitch v-model="disabledMode" label="Desabilitar licenciamento na aplicação" :disabled="settingsProtected" />
      </div>
      <div class="actions wrap">
        <button class="primary" :disabled="saving || checking || settingsProtected" @click="saveSettingsAction">Salvar configurações</button>
      </div>
    </div>

    <div class="grid columns-2 mobile-columns-1 licensing-grid">
      <div class="card grid page-gap">
        <div class="section-title">Resultado da validação</div>
        <div v-if="onlineDecision" class="info-grid">
          <div class="info-item"><strong>Permitido</strong><code>{{ onlineDecision.allowed ? 'Sim' : 'Não' }}</code></div>
          <div class="info-item"><strong>Decisão</strong><code>{{ onlineDecision.decision || '-' }}</code></div>
          <div class="info-item"><strong>Motivo</strong><code>{{ onlineDecision.reason_code || '-' }}</code></div>
          <div class="info-item"><strong>Etapa</strong><code>{{ onlineDecision.step || '-' }}</code></div>
          <div class="info-item info-item-full"><strong>Mensagem</strong><code>{{ onlineDecision.message || '-' }}</code></div>
        </div>
        <div v-else class="muted-text">Execute a validação para consultar o status remoto/offline através do componente genérico.</div>
      </div>

      <div class="card grid page-gap">
        <div class="section-title">Informações do dispositivo</div>
        <div class="info-grid">
          <div class="info-item"><strong>Hostname</strong><code>{{ deviceInfo?.hostname || '-' }}</code></div>
          <div class="info-item"><strong>Station</strong><code>{{ deviceInfo?.station_name || '-' }}</code></div>
          <div class="info-item"><strong>Machine key</strong><code>{{ deviceInfo?.device_key || '-' }}</code></div>
          <div class="info-item"><strong>OS</strong><code>{{ `${deviceInfo?.os_name || '-'} ${deviceInfo?.os_version || ''}` }}</code></div>
        </div>
      </div>
    </div>
  </div>
  </BasePage>
</template>
