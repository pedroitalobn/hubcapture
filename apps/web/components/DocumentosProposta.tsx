"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { useEhAdmin } from "@/lib/admin";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDate } from "@/lib/format";

/**
 * Documentos digitalizados da proposta — o ARQUIVO que comprova o ato.
 *
 * Quando a fonte diz "Publicado", a pergunta seguinte do gestor é "cadê o
 * documento?" (ponto 10 do feedback de 28/08): é o que ele anexa ao processo,
 * manda para o jurídico e leva para a reunião. A tela mostrava o rótulo e
 * parava ali, com o PDF a três cliques dentro do portal.
 *
 * O link aponta para a FONTE, não para o Hub: o arquivo é público na origem e
 * cachear binário de terceiro criaria um acervo que ninguém pediu para manter
 * — e que envelhece sem aviso quando a fonte republica.
 */

type Documento = {
  id: string;
  nome: string;
  tipo?: string | null;
  data_upload?: string | null;
  url?: string | null;
};

type Coleta = { status: string; total: number; erro?: string | null };

const TIPO_ROTULO: Record<string, string> = {
  publicacao: "Publicação",
  contrato: "Contrato",
  oficio: "Ofício",
  projeto: "Projeto",
  termo: "Termo",
  parecer: "Parecer",
  plano: "Plano de trabalho",
  outro: "Documento",
};

interface Props {
  proposta: { id: string };
  /** Estado da publicação — muda a FRASE do vazio, não a existência da seção:
   *  "publicado sem arquivo" é uma pendência da fonte que o gestor precisa
   *  enxergar; "não publicado sem arquivo" é o esperado. */
  publicado?: boolean;
  podeConsultarFonte?: boolean;
}

export function DocumentosProposta({
  proposta,
  publicado = false,
  podeConsultarFonte = true,
}: Props) {
  const admin = useEhAdmin();
  const [itens, setItens] = useState<Documento[]>([]);
  const [coleta, setColeta] = useState<Coleta | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);

  const carregar = useCallback(
    async (atualizar = false) => {
      atualizar ? setAtualizando(true) : setCarregando(true);
      const { data } = await api.GET("/api/v1/proposals/{proposta_id}/documents", {
        params: { path: { proposta_id: proposta.id }, query: { atualizar } },
      });
      if (data) {
        setItens((data.itens ?? []) as Documento[]);
        setColeta(data.coleta as Coleta);
      }
      setCarregando(false);
      setAtualizando(false);
    },
    [proposta.id],
  );

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // Fonte que não publica esta lista (FNS, FNDE, fundo a fundo) não ganha uma
  // seção vazia permanente na página — seria ruído em toda proposta delas.
  if (coleta?.status === "fonte_nao_suportada" && itens.length === 0) return null;
  if (!carregando && itens.length === 0 && coleta?.status === "ok" && !publicado) return null;

  return (
    <section className="card p-5">
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-2">
        <div className="flex flex-wrap items-baseline gap-2">
          <h2 className="label-mono">Documentos</h2>
          {itens.length > 0 && (
            <span className="text-xs text-ink-3">
              {itens.length} arquivo{itens.length > 1 ? "s" : ""} na fonte
            </span>
          )}
        </div>
        {podeConsultarFonte && (
          <button
            onClick={() => void carregar(true)}
            disabled={atualizando}
            className="btn btn-ghost btn-sm"
          >
            {atualizando ? "Consultando…" : "Consultar fonte"}
          </button>
        )}
      </div>

      {carregando ? (
        <p className="text-sm text-ink-3">Carregando…</p>
      ) : coleta?.status === "erro" && itens.length === 0 ? (
        <div className="flex flex-col gap-1">
          <p className="text-sm text-ink-3">
            Não foi possível consultar a fonte agora.
          </p>
          {admin && coleta.erro && (
            <details className="text-xs text-ink-3">
              <summary className="cursor-pointer select-none">
                Detalhe técnico (para a administração)
              </summary>
              <p className="mt-1.5 break-words">{coleta.erro}</p>
            </details>
          )}
        </div>
      ) : itens.length === 0 ? (
        <p className="text-sm text-ink-3">
          {publicado
            ? "A fonte informa a proposta como publicada, mas ainda não disponibilizou o arquivo da publicação na lista de documentos digitalizados."
            : "Nenhum documento digitalizado na fonte até agora."}
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-hairline">
          {itens.map((d) => (
            <li
              key={d.id}
              className="flex flex-wrap items-center justify-between gap-3 py-3"
            >
              <span className="flex min-w-0 flex-col gap-1">
                <span className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone={d.tipo === "publicacao" ? "success" : "neutral"}>
                    {TIPO_ROTULO[d.tipo ?? "outro"] ?? "Documento"}
                  </StatusBadge>
                  {d.data_upload && (
                    <span className="num text-xs text-ink-3">
                      {formatDate(d.data_upload)}
                    </span>
                  )}
                </span>
                <span className="break-words text-sm text-ink">{d.nome}</span>
              </span>
              {d.url ? (
                <a
                  href={d.url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-ghost btn-sm shrink-0"
                >
                  Baixar ↗
                </a>
              ) : (
                // Sem link, o nome ainda vale: o gestor pede o arquivo ao órgão
                // pelo nome exato. Fingir um botão que não baixa seria pior.
                <span className="text-xs text-ink-3">sem link na fonte</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {coleta?.status === "erro" && itens.length > 0 && (
        <p className="mt-3 text-xs text-ink-3">
          A última consulta à fonte falhou — a lista acima é a da consulta anterior.
        </p>
      )}
    </section>
  );
}
