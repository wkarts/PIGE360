import { reactive, readonly } from "vue";

export type SplashTone = "success" | "error" | "info" | "warning";

export interface SplashMessage {
  id: number;
  tone: SplashTone;
  text: string;
}

const splashStateInternal = reactive({
  messages: [] as SplashMessage[],
});

let splashSequence = 0;
const splashTimers = new Map<number, number>();
const MAX_ACTIVE_MESSAGES = 4;

const defaultDurationByTone: Record<SplashTone, number> = {
  success: 3200,
  info: 4200,
  warning: 5200,
  error: 6200,
};

function pushSplash(text: string, tone: SplashTone, durationMs = defaultDurationByTone[tone]): number {
  const normalizedText = String(text || "").trim() || "Operação concluída.";
  const existing = splashStateInternal.messages.find((item) => item.text === normalizedText && item.tone === tone);
  if (existing) {
    const activeTimer = splashTimers.get(existing.id);
    if (activeTimer) window.clearTimeout(activeTimer);
    const renewed = window.setTimeout(() => dismissSplash(existing.id), Math.max(1200, durationMs));
    splashTimers.set(existing.id, renewed);
    return existing.id;
  }

  const id = ++splashSequence;
  splashStateInternal.messages.push({ id, tone, text: normalizedText });
  while (splashStateInternal.messages.length > MAX_ACTIVE_MESSAGES) {
    const oldest = splashStateInternal.messages.shift();
    if (oldest) dismissSplash(oldest.id);
  }
  const timer = window.setTimeout(() => dismissSplash(id), Math.max(1200, durationMs));
  splashTimers.set(id, timer);
  return id;
}

export function dismissSplash(id: number) {
  const timer = splashTimers.get(id);
  if (timer) {
    window.clearTimeout(timer);
    splashTimers.delete(id);
  }
  const index = splashStateInternal.messages.findIndex((item) => item.id === id);
  if (index >= 0) splashStateInternal.messages.splice(index, 1);
}

export function showSplashSuccess(text: string, durationMs?: number): number {
  return pushSplash(text, "success", durationMs);
}

export function showSplashError(text: string, durationMs = 5600): number {
  return pushSplash(text, "error", durationMs);
}

export function showSplashInfo(text: string, durationMs?: number): number {
  return pushSplash(text, "info", durationMs);
}


export function showSplashWarning(text: string, durationMs?: number): number {
  return pushSplash(text, "warning", durationMs);
}

export function splashFromResult(message?: string | null, error?: string | null, warning?: string | null) {
  if (error) return showSplashError(error);
  if (warning) return showSplashWarning(warning);
  if (message) return showSplashSuccess(message);
  return null;
}

export const splashState = readonly(splashStateInternal);
