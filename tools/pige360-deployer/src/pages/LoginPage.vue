<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { useSessionStore } from "../stores/session";
import logoLight from "../assets/branding/logo-light.png";
import { appBranding } from "../config/appBranding";
import { logAppError, logAppInfo } from "../services/logger";

const router = useRouter();
const session = useSessionStore();

const form = reactive({
  login: "",
  senha: ""
});

const error = ref("");
const info = ref("");
const logoFailed = ref(false);

function handleLogoError() {
  logoFailed.value = true;
  logAppError("assets", "Falha ao carregar logo-light.png; fallback visual aplicado.", { asset: "src/assets/branding/logo-light.png" });
}

function clearCredentials() {
  form.login = "";
  form.senha = "";
  error.value = "";
  info.value = "";
}

onMounted(() => {
  clearCredentials();
});

async function submit() {
  error.value = "";
  info.value = "";
  try {
    const response = await session.login(form.login, form.senha);
    info.value = response.message;
    logAppInfo("auth", "Login concluído pela tela de login.", { usuario: form.login });
    await router.push("/");
  } catch (err) {
    error.value = err instanceof Error ? err.message : "Falha ao autenticar.";
    logAppError("auth", "Falha de autenticação exibida na tela de login.", { usuario: form.login, error: error.value });
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-box">
      <div class="login-brand">
        <img v-if="!logoFailed" :src="logoLight" :alt="appBranding.appName" class="login-logo" @error="handleLogoError" />
        <div v-else class="login-logo fallback-logo">{{ appBranding.shortName }}</div>
      </div>
      <div class="badge">{{ appBranding.appName }}</div>
      <h1>Acesso ao sistema</h1>
      <p class="muted">Informe suas credenciais para acessar o sistema.</p>

      <form class="grid" @submit.prevent="submit">
        <div class="field">
          <label>Login</label>
          <input v-model="form.login" type="text" autocomplete="username" autocapitalize="none" spellcheck="false" />
        </div>

        <div class="field">
          <label>Senha</label>
          <input v-model="form.senha" type="password" autocomplete="current-password" />
        </div>

        <div v-if="info" class="alert info">{{ info }}</div>
        <div v-if="error" class="alert error">{{ error }}</div>

        <button class="primary" type="submit" :disabled="session.loading || session.restoring">
          {{ session.loading ? "Entrando..." : session.restoring ? "Restaurando..." : "Entrar" }}
        </button>
        <div class="actions top-gap-12">
        <button class="secondary" type="button" @click="clearCredentials">Limpar credenciais</button>
      </div>
      </form>
    </div>
  </div>
</template>
