"use client";

import { createHubClient } from "@hub/api-client";

// Origem da API (sem /api/v1). Os paths do client tipado já carregam /api/v1.
// Vazio = same-origin: o navegador chama /api/v1/* no próprio domínio da web e
// o rewrite do next.config.mjs repassa para a API pela rede interna. Definir
// NEXT_PUBLIC_API_URL só se a API tiver domínio público próprio.
export const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL || "";

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

// ── Sessão com auto-refresh ─────────────────────────────────────────────────
// O access token expira em ~15 min; sem renovação, TODA chamada vira 401 e o
// app "apodrece" logado (painel vazio, admin negado). `garantirSessao` renova
// com o refresh token ANTES do request quando o access está vencido/perto de
// vencer (single-flight) e, se a sessão acabou de verdade, desloga e manda
// para o /login em vez de deixar a UI quebrada.

function _expDoToken(token: string): number | null {
  try {
    const payload = token.split(".")[1] ?? "";
    const json = JSON.parse(
      atob(payload.replace(/-/g, "+").replace(/_/g, "/")),
    ) as { exp?: number };
    return typeof json.exp === "number" ? json.exp : null;
  } catch {
    return null;
  }
}

function _expirado(token: string): boolean {
  const exp = _expDoToken(token);
  // 30s de margem para não perder o request na virada
  return exp !== null && exp * 1000 - 30_000 < Date.now();
}

let _refreshEmCurso: Promise<string | null> | null = null;

async function _renovarTokens(): Promise<string | null> {
  const refresh = window.localStorage.getItem(REFRESH_KEY);
  if (!refresh) return null;
  try {
    const resp = await fetch(`${API_ORIGIN}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!resp.ok) return null;
    const data = (await resp.json()) as {
      access_token: string;
      refresh_token: string;
    };
    setTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

/** Access token válido (renovando se preciso) ou null se a sessão acabou. */
export async function garantirSessao(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const atual = getToken();
  if (!atual) return null;
  if (!_expirado(atual)) return atual;
  _refreshEmCurso ??= _renovarTokens().finally(() => {
    _refreshEmCurso = null;
  });
  const novo = await _refreshEmCurso;
  if (novo) return novo;
  // refresh também venceu → sessão realmente encerrada
  clearTokens();
  const path = window.location.pathname;
  if (path.startsWith("/panel") || path.startsWith("/admin")) {
    window.location.href = "/login";
  }
  return null;
}

/** Client tipado (openapi-fetch) — injeta o Bearer, renovando quando vencido. */
export const api = createHubClient({ baseUrl: API_ORIGIN, getToken: garantirSessao });

/**
 * Zera TODAS as propostas do sistema (admin/superuser) — uso: validação da
 * coleta. Fetch cru autenticado (a rota é temporária e não está no client
 * tipado). As FKs são CASCADE: favoritos/pastas/monitoramentos somem junto.
 */
export async function zerarPropostas(): Promise<{ removidas: number }> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/admin/proposals`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${(await garantirSessao()) ?? ""}` },
  });
  if (!resp.ok) throw new Error(`Falha ao zerar propostas (HTTP ${resp.status})`);
  return resp.json();
}

export interface ResetPerfil {
  municipios: number;
  favoritos: number;
  pastas: number;
  monitoramentos: number;
  alertas: number;
  cache_invalidado: number;
}

/**
 * Zera o PRÓPRIO perfil (zona de perigo da conta): apaga território,
 * preferências e curadoria do usuário e manda o cache do território ser
 * recoletado. A conta continua existindo — o usuário volta ao onboarding.
 * Fetch cru autenticado (o client tipado só conhece o GET /profile).
 */
export async function zerarPerfil(): Promise<ResetPerfil> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/profile`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${(await garantirSessao()) ?? ""}` },
  });
  if (!resp.ok) throw new Error(`Falha ao zerar o perfil (HTTP ${resp.status})`);
  return resp.json();
}

/** Exclui um convite (admin). Rota fora do client tipado → fetch cru. */
export async function excluirConvite(id: string): Promise<void> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/admin/invites/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${(await garantirSessao()) ?? ""}` },
  });
  if (!resp.ok) throw new Error(`Falha ao excluir convite (HTTP ${resp.status})`);
}

/** Exclui um usuário (admin). FKs CASCADE limpam favoritos/monitoramentos/etc. */
export async function excluirUsuario(id: string): Promise<void> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/admin/users/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${(await garantirSessao()) ?? ""}` },
  });
  if (!resp.ok) throw new Error(`Falha ao excluir usuário (HTTP ${resp.status})`);
}

/** Dispara um e-mail de teste (admin) e devolve o resultado do provedor. */
export async function testarEmail(
  destinatario?: string,
): Promise<{ enviado: boolean; detalhe: string }> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/admin/email/test`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${(await garantirSessao()) ?? ""}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ destinatario: destinatario || null }),
  });
  if (!resp.ok) throw new Error(`Falha ao testar e-mail (HTTP ${resp.status})`);
  return resp.json();
}

/** Nome do arquivo servido pela API (`Content-Disposition`), com retaguarda. */
function nomeDoArquivo(resp: Response, padrao: string): string {
  const disp = resp.headers.get("Content-Disposition") ?? "";
  return /filename="?([^"';]+)"?/.exec(disp)?.[1]?.trim() || padrao;
}

export type ResultadoEspelho = "compartilhado" | "baixado";

/**
 * Espelho da proposta em PDF — o documento que o gestor encaminha.
 *
 * No celular abre a folha nativa de compartilhamento (WhatsApp, e-mail) com o
 * arquivo anexado; onde isso não existe, baixa. É a mesma ação em toda a UI, e
 * por isso mora aqui e não em cada tela.
 */
export async function exportarEspelhoProposta(
  id: string,
): Promise<ResultadoEspelho> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/proposals/${id}/pdf`, {
    headers: { Authorization: `Bearer ${(await garantirSessao()) ?? ""}` },
  });
  if (!resp.ok) throw new Error("Não foi possível gerar o espelho em PDF");
  const blob = await resp.blob();
  const nome = nomeDoArquivo(resp, `espelho-proposta-${id}.pdf`);

  const arquivo = new File([blob], nome, { type: "application/pdf" });
  // `canShare` com o arquivo é a checagem que importa: há navegador com
  // navigator.share que recusa anexos, e aí a folha abriria sem o PDF.
  if (navigator.canShare?.({ files: [arquivo] })) {
    try {
      await navigator.share({ files: [arquivo], title: nome });
      return "compartilhado";
    } catch (e) {
      // usuário fechou a folha de compartilhamento — não é erro nem download
      if ((e as Error)?.name === "AbortError") return "compartilhado";
    }
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  a.click();
  URL.revokeObjectURL(url);
  return "baixado";
}

/**
 * Upload de mídia do Class (admin) — multipart, fora do client
 * JSON tipado. Vídeo curto ou documento; vídeo pesado vai por URL.
 */
export async function enviarMidiaAjuda(
  artigoId: string,
  arquivo: File,
  opts: { tipo: "video" | "documento"; titulo?: string; orientacao?: "horizontal" | "vertical" },
): Promise<void> {
  const form = new FormData();
  form.append("arquivo", arquivo);
  form.append("tipo", opts.tipo);
  if (opts.titulo) form.append("titulo", opts.titulo);
  form.append("orientacao", opts.orientacao ?? "horizontal");
  const resp = await fetch(
    `${API_ORIGIN}/api/v1/admin/class/articles/${artigoId}/media/upload`,
    {
      method: "POST",
      headers: { Authorization: `Bearer ${(await garantirSessao()) ?? ""}` },
      body: form,
    },
  );
  if (!resp.ok) {
    const corpo = (await resp.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(
      typeof corpo?.detail === "string"
        ? corpo.detail
        : `Falha no upload (HTTP ${resp.status})`,
    );
  }
}

/** Baixa a agenda de contatos em .vcf (importável no Google/Apple/Outlook). */
export async function baixarContatosVcf(): Promise<void> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/contacts/export`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!resp.ok) throw new Error("Falha ao exportar contatos");
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "contatos-hub-capture.vcf";
  a.click();
  URL.revokeObjectURL(url);
}

/** Importa um arquivo .vcf escolhido pelo usuário. */
export async function importarContatosVcf(arquivo: File) {
  const conteudo = await arquivo.text();
  const { data, error } = await api.POST("/api/v1/contacts/import", {
    body: { conteudo },
  });
  if (error) throw new Error("Não foi possível ler o arquivo .vcf");
  return data;
}

/**
 * Baixa um relatório CSV da API (GET autenticado → blob → download).
 * Usado pelos botões "Baixar relatório" da captação e das emendas.
 */
export async function baixarCsv(
  path: string,
  params: Record<string, string | number | boolean | string[] | null | undefined>,
  filename: string,
): Promise<void> {
  const qs = new URLSearchParams();
  for (const [chave, valor] of Object.entries(params)) {
    if (valor === null || valor === undefined || valor === "") continue;
    // lista = parâmetro repetido (?municipio=A&municipio=B), como a API espera
    if (Array.isArray(valor)) valor.forEach((v) => v !== "" && qs.append(chave, String(v)));
    else qs.set(chave, String(valor));
  }
  const resp = await fetch(`${API_ORIGIN}${path}?${qs.toString()}`, {
    headers: { Authorization: `Bearer ${(await garantirSessao()) ?? ""}` },
  });
  if (!resp.ok) throw new Error("Falha ao gerar o relatório");
  const url = URL.createObjectURL(await resp.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
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
  const resp = await fetch(`${API_ORIGIN}/api/v1/copilot/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${(await garantirSessao()) ?? ""}`,
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

/** Confirma o e-mail a partir do token recebido. */
export async function verificarEmail(token: string): Promise<void> {
  const { error } = await api.POST("/api/v1/auth/verify", { body: { token } });
  if (error) throw new Error("Token inválido ou expirado");
}

/** Dados do usuário logado. */
export async function meProfile() {
  const { data, error } = await api.GET("/api/v1/users/me");
  if (error) throw new Error("Sessão expirada");
  return data;
}

/** Atualiza o próprio perfil (nome/telefone/opt-in e, opcionalmente, senha). */
export async function atualizarPerfil(patch: {
  nome?: string;
  telefone_wpp?: string;
  optin_wpp?: boolean;
  password?: string;
}): Promise<void> {
  const { error } = await api.PATCH("/api/v1/users/me", { body: patch });
  if (error) {
    const detail = (error as { detail?: unknown }).detail;
    throw new Error(
      typeof detail === "string" ? detail : "Não foi possível salvar",
    );
  }
}

/** Evento do agente do Dynamic Island: ferramenta em uso ou texto da resposta. */
export type IslandEvento = { tool?: string; delta?: string };

/**
 * Copiloto do Dynamic Island (SSE) — agente com tool calling no backend.
 * Emite {tool} quando o agente consulta uma ferramenta e {delta} com a resposta.
 */
export async function islandStream(
  pergunta: string,
  onEvento: (e: IslandEvento) => void,
  /** Recorte de território do painel — o agente responde sobre o mesmo conjunto. */
  municipios?: string[],
): Promise<void> {
  const resp = await fetch(`${API_ORIGIN}/api/v1/copilot/island`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${(await garantirSessao()) ?? ""}`,
    },
    body: JSON.stringify({ pergunta, municipios: municipios?.length ? municipios : null }),
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
        onEvento(JSON.parse(m) as IslandEvento);
      } catch {
        /* ignora linhas não-JSON */
      }
    }
  }
}
