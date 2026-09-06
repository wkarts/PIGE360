<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import logoMark from "../assets/branding/logo-mark.png";
import { appBranding } from "../config/appBranding";
import { useSessionStore } from "../stores/session";

const router = useRouter();
const session = useSessionStore();
const form = reactive({ currentPassword: "", newPassword: "", confirmation: "" });
const error = ref("");
const validConfirmation = computed(() => form.newPassword === form.confirmation);

async function submit() {
  error.value = "";
  if (!validConfirmation.value) {
    error.value = "A confirmação não corresponde à nova senha.";
    return;
  }
  try {
    await session.changePassword(form.currentPassword, form.newPassword);
    await router.replace("/");
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Falha ao alterar senha.";
  }
}

async function logout() {
  await session.logout();
  await router.replace("/login");
}
</script>

<template>
  <main class="login-page">
    <section class="login-box first-access-card" aria-labelledby="first-access-title">
      <div class="login-brand">
        <img :src="logoMark" :alt="appBranding.appName" class="login-logo" />
      </div>
      <div class="badge">Primeiro acesso</div>
      <h1 id="first-access-title">Crie sua senha definitiva</h1>
      <p class="muted">
        A credencial de implantação é temporária. Para proteger seus dados, nenhuma outra tela
        fica disponível até que você defina uma senha exclusiva.
      </p>

      <form class="grid" @submit.prevent="submit">
        <div class="field">
          <label for="current-password">Senha temporária</label>
          <input id="current-password" v-model="form.currentPassword" type="password" autocomplete="current-password" required />
        </div>
        <div class="field">
          <label for="new-password">Nova senha</label>
          <input id="new-password" v-model="form.newPassword" type="password" autocomplete="new-password" minlength="12" required />
          <small>Use 12 ou mais caracteres, com maiúscula, minúscula, número e símbolo.</small>
        </div>
        <div class="field">
          <label for="password-confirmation">Confirmar nova senha</label>
          <input id="password-confirmation" v-model="form.confirmation" type="password" autocomplete="new-password" minlength="12" required />
        </div>
        <div v-if="error" class="alert error" role="alert">{{ error }}</div>
        <button class="primary" type="submit" :disabled="session.loading">
          {{ session.loading ? "Salvando..." : "Definir senha e continuar" }}
        </button>
        <button class="secondary" type="button" :disabled="session.loading" @click="logout">Sair</button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.first-access-card { max-width: 520px; }
.field small { color: var(--muted, #64748b); line-height: 1.45; }
</style>
