"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

export interface Alerta {
  id: string;
  proposta_id?: string | null;
  tipo?: string | null;
  payload?: Record<string, unknown> | null;
  lido: boolean;
  created_at: string;
}

/** Escopo do critério: uma proposta-chave ou o território (município). */
export type EscopoCriterio = "proposta" | "territorio";

export interface CriterioAlerta {
  chave: string;
  rotulo: string;
  descricao: string;
  escopo: EscopoCriterio;
  padrao: boolean;
}

/**
 * Rótulos de retaguarda. O catálogo de verdade vem de `GET /alerts/criteria`
 * (registro do backend, §53) — este mapa só evita chip sem nome enquanto a
 * chamada não voltou, e cobre o tipo LEGADO `status` dos alertas antigos.
 */
export const ALERTA_TIPO_LABEL: Record<string, string> = {
  status: "Situação e movimentação",
  situacao: "Situação e movimentação",
  prazo: "Prazos",
  pendencia: "Pendências",
  parecer: "Atualização de pareceres",
  empenho: "Valor empenhado",
  pagamento: "Pagamento",
  publicacao: "Publicação",
  vencimento: "Vencimento do convênio",
  nova_proposta: "Novo alerta",
  oportunidade: "Novo alerta",
};

/**
 * Tipos de escopo TERRITÓRIO. Na PÍLULA da lista eles colapsam num rótulo só
 * ("Novo alerta"): qualificar a espécie da oportunidade ali não ajuda o gestor
 * — a frase ao lado já diz o que apareceu e onde. O rótulo específico do
 * catálogo continua valendo onde ele DECIDE algo: o multi-select de critérios.
 */
const TIPOS_TERRITORIO = new Set(["nova_proposta", "oportunidade"]);
const PILL_TERRITORIO = "Novo alerta";

// O catálogo é o mesmo para o app inteiro: uma chamada por sessão, compartilhada
// entre as telas que montam o multi-select (Alertas e detalhe da proposta).
let _cache: CriterioAlerta[] | null = null;
let _emVoo: Promise<CriterioAlerta[]> | null = null;

export async function carregarCriterios(): Promise<CriterioAlerta[]> {
  if (_cache) return _cache;
  if (!_emVoo) {
    _emVoo = api
      .GET("/api/v1/alerts/criteria")
      .then(({ data }) => {
        _cache = (data as CriterioAlerta[] | undefined) ?? [];
        return _cache;
      })
      .catch(() => [] as CriterioAlerta[])
      .finally(() => {
        _emVoo = null;
      });
  }
  return _emVoo;
}

/** Catálogo do escopo + rótulo por chave (com retaguarda estática). */
export function useCriteriosAlerta(escopo?: EscopoCriterio) {
  const [criterios, setCriterios] = useState<CriterioAlerta[]>(_cache ?? []);

  useEffect(() => {
    let vivo = true;
    void carregarCriterios().then((lista) => {
      if (vivo) setCriterios(lista);
    });
    return () => {
      vivo = false;
    };
  }, []);

  const doEscopo = escopo
    ? criterios.filter((c) => c.escopo === escopo)
    : criterios;
  const rotulo = (chave?: string | null) =>
    criterios.find((c) => c.chave === chave)?.rotulo ??
    ALERTA_TIPO_LABEL[chave ?? ""] ??
    chave ??
    "Alerta";
  return {
    criterios: doEscopo,
    rotulo,
    // rótulo da PÍLULA: território vira "Novo alerta" (sem espécie)
    rotuloPill: (chave?: string | null) =>
      TIPOS_TERRITORIO.has(chave ?? "") ? PILL_TERRITORIO : rotulo(chave),
  };
}

/** Padrões do escopo — é o que vale quando o monitoramento não escolheu nada. */
export function padroesDe(criterios: CriterioAlerta[]): string[] {
  return criterios.filter((c) => c.padrao).map((c) => c.chave);
}

export function alertaTipoLabel(tipo?: string | null): string {
  if (TIPOS_TERRITORIO.has(tipo ?? "")) return PILL_TERRITORIO;
  return ALERTA_TIPO_LABEL[tipo ?? ""] ?? tipo ?? "Alerta";
}

/**
 * Frase do alerta. Os de mudança trazem `resumo` pronto do backend (a mesma
 * frase que vai para o e-mail e o WhatsApp); os demais caem no antes/depois.
 */
export function descreverAlerta(a: Alerta): string {
  const p = a.payload ?? {};
  if (typeof p.resumo === "string" && p.resumo) return p.resumo;
  const antes = p.antes ?? p.de ?? p.anterior;
  const depois = p.depois ?? p.para ?? p.atual;
  if (antes !== undefined && depois !== undefined) {
    return `${String(antes) || "—"} → ${String(depois) || "—"}`;
  }
  if (typeof p.descricao === "string") return p.descricao;
  if (typeof p.mensagem === "string") return p.mensagem;
  return "Mudança detectada na proposta";
}
