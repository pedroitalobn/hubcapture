"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import { BotaoEspelho } from "@/components/BotaoEspelho";
import { Favorito } from "@/components/Favorito";
import { NumeroProposta } from "@/components/NumeroProposta";
import { TextoLimitado } from "@/components/TextoLimitado";
import { municipioPrincipal, municipioSecundario } from "@/lib/format";
import { useTerritorio } from "@/lib/territorio";

type Proposta = {
  id: string;
  fonte: string;
  id_externo: string;
  numero_proposta?: string | null;
  titulo?: string | null;
  objeto?: string | null;
  orgao_superior?: string | null;
  modalidade?: string | null;
  municipio_nome?: string | null;
  municipio_ibge?: string | null;
  uf?: string | null;
  valor_total?: string | null;
  situacao?: string | null;
};

function brl(v?: string | null): string {
  const n = Number(v);
  if (!v || Number.isNaN(n)) return "—";
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function MinhasPropostasPage() {
  const { selecionados } = useTerritorio();
  const [propostas, setPropostas] = useState<Proposta[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const { data } = await api.GET("/api/v1/favorites/proposals");
    if (data) setPropostas(data as Proposta[]);
    setCarregando(false);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // A lista já vem só das favoritas do usuário; o recorte de território do
  // painel se aplica aqui em memória (a API não precisa ser chamada de novo).
  const visiveis = useMemo(() => {
    if (selecionados.length === 0) return propostas;
    const escolhidos = new Set(selecionados);
    return propostas.filter(
      (p) => p.municipio_ibge && escolhidos.has(p.municipio_ibge),
    );
  }, [propostas, selecionados]);

  // Só tira da lista depois que a API confirmou — remover antes e ignorar o
  // erro faria a proposta "voltar" no próximo carregamento.
  async function desfavoritar(id: string) {
    const { error } = await api.DELETE("/api/v1/favorites/{proposta_id}", {
      params: { path: { proposta_id: id } },
    });
    if (error) {
      setErro("Não foi possível remover a favorita agora — tente novamente.");
      return;
    }
    setErro(null);
    setPropostas((prev) => prev.filter((p) => p.id !== id));
  }

  return (
    <>
      <header>
        <h1 className="page-title">Minhas Propostas</h1>
        <p className="mt-1 text-sm text-ink-2">
          As propostas que você favoritou para acompanhar. Clique para ver todos os
          dados; a estrela remove daqui.
        </p>
      </header>

      {erro && (
        <p role="status" className="text-sm tone-danger">
          {erro}
        </p>
      )}

      {carregando ? (
        <p className="text-sm text-ink-3">Carregando…</p>
      ) : visiveis.length === 0 ? (
        <div className="card p-8 text-center">
          <p className="text-sm text-ink-2">
            {propostas.length === 0
              ? "Você ainda não favoritou nenhuma proposta."
              : "Nenhuma proposta favoritada nos municípios filtrados — ajuste o território no menu lateral."}
          </p>
          <Link href="/panel/funding" className="btn btn-primary mt-4 inline-flex">
            Ir para as Propostas
          </Link>
        </div>
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-hairline text-left text-ink-3">
                <th className="w-16 px-4 py-3" />
                <th className="px-3 py-3">Proposta</th>
                <th className="px-3 py-3">Município</th>
                <th className="px-3 py-3">Valor</th>
                <th className="px-3 py-3">Situação</th>
              </tr>
            </thead>
            <tbody>
              {visiveis.map((p) => (
                <tr key={p.id} className="border-b border-hairline last:border-0 row-interactive">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Favorito
                        ativo
                        onToggle={() => desfavoritar(p.id)}
                        rotuloOn="Remover das minhas propostas"
                      />
                      <BotaoEspelho propostaId={p.id} formato="icone" />
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    {/* mesma pílula da captação e do feed. O `id_externo` saiu
                        da linha de apoio: é plumbing da integração e ocupava o
                        lugar da referência que o gestor de fato usa (§35). */}
                    <NumeroProposta numero={p.numero_proposta} tamanho="sm" className="mb-1" />
                    {/* mesmo teto de caracteres da lista de captação: o objeto
                        da fonte vem como título e pode ter milhares deles */}
                    <TextoLimitado
                      texto={p.titulo ?? p.objeto}
                      limite={110}
                      titulo={municipioPrincipal(p)}
                      rotulo="Objeto da proposta"
                      className="block"
                      vazio={
                        <Link
                          href={`/panel/funding/${p.id}`}
                          className="block font-medium hover:underline"
                        >
                          Proposta sem título na fonte
                        </Link>
                      }
                      envolver={(trecho) => (
                        <Link
                          href={`/panel/funding/${p.id}`}
                          className="font-medium hover:underline"
                        >
                          {trecho}
                        </Link>
                      )}
                    />
                    <p className="mt-0.5 max-w-md text-xs text-ink-3">
                      {[p.orgao_superior, p.modalidade].filter(Boolean).join(" · ")}
                    </p>
                  </td>
                  <td className="px-3 py-3 text-ink-2">
                    {/* nome do município lidera; código IBGE é apoio (seção 23) */}
                    <span className="block">{municipioPrincipal(p)}</span>
                    {municipioSecundario(p) && (
                      <span className="block font-mono text-[11px] text-ink-3">
                        {municipioSecundario(p)}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-3 tabular-nums">{brl(p.valor_total)}</td>
                  <td className="px-3 py-3 text-ink-2">{p.situacao ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
