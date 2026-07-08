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
