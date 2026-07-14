"use client";

import { createHubClient } from "@hub/api-client";

// Origem da API (sem /api/v1). Os paths do client tipado já carregam /api/v1.
export const API_ORIGIN =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "hub_access_token";
const REFRESH_KEY = "hub_refresh_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setTokens(access: string, refresh: string): void {
  window.localStorage.setItem(TOKEN_KEY, access);
  window.localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

/** Client tipado (openapi-fetch) — injeta o Bearer automaticamente. */
export const api = createHubClient({ baseUrl: API_ORIGIN, getToken });

/** Baixa o PDF de uma proposta (GET autenticado → blob → download). */
export async function baixarPdfProposta(id: string): Promise<void> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/propostas/${id}/pdf`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!resp.ok) throw new Error("Falha ao gerar PDF");
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `proposta-${id}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Chat do Copiloto (SSE). Chama `onDelta` a cada token e resolve ao terminar.
 */
export async function chatStream(
  pergunta: string,
  modo: "propostas" | "copiloto",
  onDelta: (t: string) => void,
): Promise<void> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/copiloto/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken() ?? ""}`,
    },
    body: JSON.stringify({ pergunta, modo }),
  });
  if (!resp.body) return;
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const linhas = buffer.split("\n\n");
    buffer = linhas.pop() ?? "";
    for (const linha of linhas) {
      const m = linha.replace(/^data: /, "").trim();
      if (!m || m === "[DONE]") continue;
      try {
        const { delta } = JSON.parse(m) as { delta?: string };
        if (delta) onDelta(delta);
      } catch {
        /* ignora linhas não-JSON */
      }
    }
  }
}

/**
 * Login usa OAuth2PasswordRequestForm (application/x-www-form-urlencoded),
 * então vai por fetch direto (não pelo client JSON tipado).
 */
export async function login(email: string, senha: string): Promise<void> {
  const body = new URLSearchParams({ username: email, password: senha });
  const resp = await fetch(`${API_ORIGIN}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!resp.ok) {
    throw new Error("Credenciais inválidas");
  }
  const data = (await resp.json()) as {
    access_token: string;
    refresh_token: string;
  };
  setTokens(data.access_token, data.refresh_token);
}

/** Cadastro (self-signup). Cria a conta e já autentica. */
export async function registrar(
  email: string,
  senha: string,
  nome?: string,
): Promise<void> {
  const { error } = await api.POST("/api/v1/auth/register", {
    // is_active/is_superuser/is_verified são ignorados pelo fastapi-users no
    // register (segurança); enviados só para satisfazer o tipo gerado.
    body: {
      email,
      password: senha,
      nome,
      is_active: true,
      is_superuser: false,
      is_verified: false,
      optin_wpp: false,
    },
  });
  if (error) {
    const detail = (error as { detail?: unknown }).detail;
    throw new Error(
      typeof detail === "string" ? detail : "Não foi possível criar a conta",
    );
  }
  await login(email, senha);
}

/** Solicita e-mail de recuperação de senha (sempre resolve — não revela se o e-mail existe). */
export async function esqueciSenha(email: string): Promise<void> {
  await api.POST("/api/v1/auth/forgot-password", { body: { email } });
}

/** Redefine a senha a partir do token recebido por e-mail. */
export async function redefinirSenha(token: string, senha: string): Promise<void> {
  const { error } = await api.POST("/api/v1/auth/reset-password", {
    body: { token, password: senha },
  });
  if (error) throw new Error("Token inválido ou expirado");
}
