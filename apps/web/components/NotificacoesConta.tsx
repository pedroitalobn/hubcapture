"use client";

/**
 * "Como quero ser avisado" (§63) — os canais de alerta da CONTA, num lugar só:
 * notificação no navegador/celular (Web Push), e-mail e WhatsApp.
 *
 * Os canais valem para TODO alerta (proposta favoritada, monitorada, busca de
 * futuras propostas): antes, cada monitoramento nascia só com "painel" e ligar
 * o WhatsApp na conta não mudava nada.
 *
 * `compacto` é a versão da central de Alertas: só o push, que é o canal que
 * depende DESTE navegador.
 */

import { useCallback, useEffect, useState } from "react";
import {
  ativarPush,
  desativarPush,
  estadoPush,
  lerPreferencias,
  precisaInstalarNoIOS,
  salvarEmail,
  testarPush,
  type EstadoPush,
  type PreferenciasNotificacao,
} from "@/lib/push";

const TEXTO_ESTADO: Record<EstadoPush, string> = {
  indisponivel: "Este navegador não suporta notificações push.",
  bloqueado:
    "As notificações foram bloqueadas neste navegador. Libere nas configurações do site (ícone de cadeado ao lado do endereço) e volte aqui.",
  inativo: "Desativadas neste navegador.",
  ativo: "Ativas neste navegador.",
};

export function NotificacoesConta({ compacto = false }: { compacto?: boolean }) {
  const [estado, setEstado] = useState<EstadoPush | null>(null);
  const [prefs, setPrefs] = useState<PreferenciasNotificacao | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  // lido no efeito, não no render: no servidor não há navigator e o HTML
  // hidratado divergiria do renderizado
  const [ios, setIos] = useState(false);

  const carregar = useCallback(async () => {
    setIos(precisaInstalarNoIOS());
    setEstado(await estadoPush().catch(() => "indisponivel" as const));
    if (!compacto) setPrefs(await lerPreferencias().catch(() => null));
  }, [compacto]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function acao(fn: () => Promise<void>) {
    setMsg(null);
    setOcupado(true);
    try {
      await fn();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Não foi possível concluir agora.");
    } finally {
      setOcupado(false);
    }
  }

  const ligar = () =>
    acao(async () => {
      const novo = await ativarPush();
      setEstado(novo);
      if (novo === "ativo") {
        const r = await testarPush();
        setMsg(
          r.enviados
            ? "Pronto — enviamos uma notificação de teste para este navegador."
            : "Navegador registrado, mas o envio de teste não chegou. Tente de novo em instantes.",
        );
      }
    });

  const desligar = () =>
    acao(async () => {
      setEstado(await desativarPush());
      setMsg("Notificações desativadas neste navegador.");
    });

  const testar = () =>
    acao(async () => {
      const r = await testarPush();
      setMsg(
        r.enviados
          ? `Teste enviado para ${r.enviados} navegador(es).`
          : "Nenhum navegador recebeu o teste — ative as notificações de novo.",
      );
    });

  const alternarEmail = (ligado: boolean) =>
    acao(async () => {
      setPrefs(await salvarEmail(ligado));
    });

  if (compacto) {
    if (estado === null || estado === "ativo" || estado === "indisponivel") return null;
    return (
      <div className="card flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
        <div className="min-w-0">
          <p className="font-medium text-ink">Receba os alertas no celular ou no computador</p>
          <p className="text-ink-3">
            {estado === "bloqueado"
              ? TEXTO_ESTADO.bloqueado
              : ios
                ? "No iPhone, adicione o Hub Capture à tela de início (Compartilhar → Adicionar à Tela de Início) e ative por lá."
                : "Ative as notificações deste navegador — avisamos quando uma proposta que você acompanha mudar."}
          </p>
          {msg && <p className="mt-1 text-ink-2">{msg}</p>}
        </div>
        {estado === "inativo" && !ios && (
          <button type="button" onClick={ligar} disabled={ocupado} className="btn btn-primary">
            {ocupado ? "Ativando…" : "Ativar notificações"}
          </button>
        )}
      </div>
    );
  }

  return (
    <section className="card flex max-w-md flex-col gap-4 p-6">
      <h2 className="label-mono">Como quero ser avisado</h2>
      <p className="text-xs leading-relaxed text-ink-3">
        Vale para todos os alertas: propostas favoritas e monitoradas e novas
        propostas do seu território. Todo alerta também fica na central de Alertas.
      </p>

      <div className="flex flex-col gap-2 border-t border-hairline pt-3">
        <span className="field-label">Notificação no navegador / celular</span>
        <p className="text-sm text-ink-2">
          {estado ? TEXTO_ESTADO[estado] : "Verificando…"}
        </p>
        {ios && estado !== "ativo" && (
          <p className="text-xs text-ink-3">
            No iPhone/iPad, as notificações só funcionam com o Hub Capture
            instalado: toque em Compartilhar → Adicionar à Tela de Início e abra
            o app por lá.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {estado === "inativo" && !ios && (
            <button type="button" onClick={ligar} disabled={ocupado} className="btn btn-primary btn-sm">
              {ocupado ? "Ativando…" : "Ativar neste navegador"}
            </button>
          )}
          {estado === "ativo" && (
            <>
              <button type="button" onClick={testar} disabled={ocupado} className="btn btn-sm">
                Enviar teste
              </button>
              <button type="button" onClick={desligar} disabled={ocupado} className="btn btn-ghost btn-sm">
                Desativar neste navegador
              </button>
            </>
          )}
        </div>
      </div>

      {prefs && (
        <>
          <label className="flex items-start gap-2 border-t border-hairline pt-3 text-sm text-ink-2">
            <input
              type="checkbox"
              checked={prefs.email}
              disabled={ocupado || !prefs.email_no_plano}
              onChange={(e) => void alternarEmail(e.target.checked)}
              className="accent-brand mt-0.5"
            />
            <span>
              Receber alertas por e-mail
              {!prefs.email_no_plano && (
                <span className="block text-xs text-ink-3">Não incluído no seu plano.</span>
              )}
            </span>
          </label>
          <p className="border-t border-hairline pt-3 text-sm text-ink-2">
            WhatsApp:{" "}
            {!prefs.wpp_no_plano
              ? "não incluído no seu plano."
              : prefs.wpp
                ? `ativo (${prefs.telefone_wpp}).`
                : "desativado — informe o telefone e marque “Receber alertas por WhatsApp” em Perfil."}
          </p>
        </>
      )}

      {msg && <p className="text-sm text-ink-2">{msg}</p>}
    </section>
  );
}
