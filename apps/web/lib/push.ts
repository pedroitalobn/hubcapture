"use client";

/**
 * Web Push no navegador (§63): registrar o service worker, pedir a permissão,
 * inscrever no serviço de push com a chave VAPID da API e mandar a inscrição
 * para o backend. A permissão concedida É o opt-in — a varredura de alertas
 * entrega a todo navegador inscrito da conta.
 *
 * Rotas fora do client tipado → fetch cru autenticado (mesmo padrão de
 * `lib/api/client.ts`).
 */

import { API_ORIGIN, garantirSessao } from "@/lib/api/client";

export type EstadoPush =
  | "indisponivel" // navegador sem suporte (ou iPhone fora do app instalado)
  | "bloqueado" // o usuário negou a permissão — só ele desfaz, nas configurações
  | "inativo" // suportado, ainda não ativado neste navegador
  | "ativo";

async function autenticado(caminho: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_ORIGIN}/api/v1${caminho}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${(await garantirSessao()) ?? ""}`,
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });
}

export function pushSuportado(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** iPhone/iPad só recebem push com o app instalado na tela de início. */
export function precisaInstalarNoIOS(): boolean {
  if (typeof window === "undefined") return false;
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const instalado =
    window.matchMedia?.("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return ios && !instalado;
}

async function registro(): Promise<ServiceWorkerRegistration> {
  const existente = await navigator.serviceWorker.getRegistration("/");
  if (existente) return existente;
  await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  return navigator.serviceWorker.ready;
}

function chaveParaBytes(base64url: string): Uint8Array {
  const pad = "=".repeat((4 - (base64url.length % 4)) % 4);
  const b64 = (base64url + pad).replace(/-/g, "+").replace(/_/g, "/");
  const bruto = atob(b64);
  return Uint8Array.from(bruto, (c) => c.charCodeAt(0));
}

export async function estadoPush(): Promise<EstadoPush> {
  if (!pushSuportado()) return "indisponivel";
  if (Notification.permission === "denied") return "bloqueado";
  const reg = await navigator.serviceWorker.getRegistration("/");
  const insc = reg ? await reg.pushManager.getSubscription() : null;
  if (insc && Notification.permission === "granted") {
    // reenvia ao backend a cada visita: se o servidor a apagou (410) ou o
    // usuário trocou de conta neste navegador, a inscrição volta a valer
    await enviarInscricao(insc).catch(() => undefined);
    return "ativo";
  }
  return "inativo";
}

async function enviarInscricao(insc: PushSubscription): Promise<void> {
  const resp = await autenticado("/notifications/push/subscriptions", {
    method: "POST",
    body: JSON.stringify(insc.toJSON()),
  });
  if (!resp.ok) throw new Error(`Falha ao registrar o navegador (HTTP ${resp.status})`);
}

/** Pede a permissão e inscreve este navegador. Lança com a razão da falha. */
export async function ativarPush(): Promise<EstadoPush> {
  if (!pushSuportado()) return "indisponivel";
  const permissao = await Notification.requestPermission();
  if (permissao === "denied") return "bloqueado";
  if (permissao !== "granted") return "inativo";

  const resp = await autenticado("/notifications/push/key");
  if (!resp.ok) throw new Error(`Falha ao obter a chave de push (HTTP ${resp.status})`);
  const { chave_publica } = (await resp.json()) as { chave_publica: string };

  const reg = await registro();
  let insc = await reg.pushManager.getSubscription();
  // inscrição feita com outra chave (par VAPID trocado no painel) não recebe
  // mais nada: descarta e inscreve de novo
  const atual = insc?.options.applicationServerKey;
  const nova = chaveParaBytes(chave_publica);
  if (insc && atual) {
    const antiga = new Uint8Array(atual);
    const igual = antiga.length === nova.length && antiga.every((b, i) => b === nova[i]);
    if (!igual) {
      await insc.unsubscribe();
      insc = null;
    }
  }
  insc ??= await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: nova as BufferSource,
  });
  await enviarInscricao(insc);
  return "ativo";
}

export async function desativarPush(): Promise<EstadoPush> {
  if (!pushSuportado()) return "indisponivel";
  const reg = await navigator.serviceWorker.getRegistration("/");
  const insc = reg ? await reg.pushManager.getSubscription() : null;
  if (insc) {
    await autenticado("/notifications/push/unsubscribe", {
      method: "POST",
      body: JSON.stringify({ endpoint: insc.endpoint }),
    }).catch(() => undefined);
    await insc.unsubscribe();
  }
  return "inativo";
}

export async function testarPush(): Promise<{ enviados: number; falhas: number; removidas: number }> {
  const resp = await autenticado("/notifications/push/test", { method: "POST" });
  if (!resp.ok) throw new Error(`Falha ao enviar o teste (HTTP ${resp.status})`);
  return resp.json();
}

export interface PreferenciasNotificacao {
  email: boolean;
  wpp: boolean;
  telefone_wpp?: string | null;
  push_inscricoes: number;
  email_no_plano: boolean;
  wpp_no_plano: boolean;
}

export async function lerPreferencias(): Promise<PreferenciasNotificacao> {
  const resp = await autenticado("/notifications/preferences");
  if (!resp.ok) throw new Error(`Falha ao ler as preferências (HTTP ${resp.status})`);
  return resp.json();
}

export async function salvarEmail(email: boolean): Promise<PreferenciasNotificacao> {
  const resp = await autenticado("/notifications/preferences", {
    method: "PUT",
    body: JSON.stringify({ email }),
  });
  if (!resp.ok) throw new Error(`Falha ao salvar (HTTP ${resp.status})`);
  return resp.json();
}
