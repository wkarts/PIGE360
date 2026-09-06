export function formatMinutes(value: number): string {
  const negative = value < 0;
  const absolute = Math.abs(value);
  const hours = Math.floor(absolute / 60);
  const minutes = absolute % 60;
  return `${negative ? "-" : ""}${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export function booleanLabel(value: unknown): string {
  return Number(value) === 1 || value === true ? "Sim" : "Não";
}

export function onlyDigits(value: unknown): string {
  return String(value ?? "").replace(/\D+/g, "");
}

export function formatCpfCnpj(value: unknown): string {
  const digits = onlyDigits(value);

  if (digits.length === 11) {
    return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  }

  if (digits.length === 14) {
    return digits.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
  }

  return String(value ?? "");
}

export function formatCpf(value: unknown): string {
  const digits = onlyDigits(value);
  if (digits.length === 11) {
    return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  }
  return String(value ?? "");
}

export function formatPis(value: unknown): string {
  const digits = onlyDigits(value);
  if (digits.length === 11) {
    return digits.replace(/(\d{3})(\d{5})(\d{2})(\d{1})/, "$1.$2.$3-$4");
  }
  return String(value ?? "");
}

export function formatPhone(value: unknown): string {
  const digits = onlyDigits(value);
  if (digits.length === 10) {
    return digits.replace(/(\d{2})(\d{4})(\d{4})/, "($1) $2-$3");
  }
  if (digits.length === 11) {
    return digits.replace(/(\d{2})(\d{5})(\d{4})/, "($1) $2-$3");
  }
  return String(value ?? "");
}

export function formatCep(value: unknown): string {
  const digits = onlyDigits(value);
  if (digits.length === 8) {
    return digits.replace(/(\d{5})(\d{3})/, "$1-$2");
  }
  return String(value ?? "");
}

export function emptyToNull<T>(value: T): T | null {
  if (value === undefined || value === null) return null;
  if (typeof value === "string" && value.trim() === "") return null;
  return value;
}
