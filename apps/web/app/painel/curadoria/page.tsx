"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { PropostaCard } from "@/components/PropostaCard";
import { SkeletonList } from "@/components/Skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { Aviso, Button, Card, Input, cx } from "@/components/ui";
import { api, baixarPdfProposta } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import type { Proposta } from "@/lib/proposta";

interface Pasta {
  id: string;
  nome: string;
  cor?: string | null;
  created_at: string;
}

const CORES = ["#1d4ed8", "#067647", "#b54708", "#b42318", "#6b21a8", "#0e7490"];

export default function CuradoriaPage() {
  const [favoritos, setFavoritos] = useState<Set<string>>(new Set());
  const [monitoradas, setMonitoradas] = useState<Set<string>>(new Set());
  const [propostas, setPropostas] = useState<Map<string, Proposta>>(new Map());
  const [pastas, setPastas] = useState<Pasta[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const [novaPasta, setNovaPasta] = useState("");
  const [novaCor, setNovaCor] = useState(CORES[0]!);
  const [criando, setCriando] = useState(false);
  const [pastaAlvo, setPastaAlvo] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const [fav, mon, props, past] = await Promise.all([
      api.GET("/api/v1/favoritos"),
      api.GET("/api/v1/monitoramentos"),
      api.GET("/api/v1/propostas", { params: { query: {} } }),
      api.GET("/api/v1/pastas"),
    ]);
    if (Array.isArray(fav.data)) {
      setFavoritos(new Set((fav.data as { proposta_id: string }[]).map((f) => f.proposta_id)));
    }
    if (Array.isArray(mon.data)) {
      setMonitoradas(
        new Set(
          (mon.data as { proposta_id: string; ativo: boolean }[])
            .filter((m) => m.ativo)
            .map((m) => m.proposta_id),
        ),
      );
    }
    if (Array.isArray(props.data)) {
      setPropostas(new Map((props.data as Proposta[]).map((p) => [p.id, p])));
    }
    if (Array.isArray(past.data)) setPastas(past.data as Pasta[]);
    setCarregando(false);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function criarPasta(e: React.FormEvent) {
    e.preventDefault();
    const nome = novaPasta.trim();
    if (!nome) return;
    setCriando(true);
    setErro(null);
    const { data, error } = await api.POST("/api/v1/pastas", {
      body: { nome, cor: novaCor },
    });
    if (error) setErro("Não foi possível criar a pasta.");
    else {
      setPastas((p) => [...p, data as Pasta]);
      setNovaPasta("");
      setOk(`Pasta “${nome}” criada.`);
    }
    setCriando(false);
  }

  async function removerFavorito(p: Proposta) {
    setFavoritos((s) => {
      const n = new Set(s);
      n.delete(p.id);
      return n;
    });
    const { error } = await api.DELETE("/api/v1/favoritos/{proposta_id}", {
      params: { path: { proposta_id: p.id } },
    });
    if (error) {
      setFavoritos((s) => new Set(s).add(p.id));
      setErro("Não foi possível remover o favorito.");
    }
  }

  async function adicionarNaPasta(p: Proposta) {
    if (!pastaAlvo) {
      setErro("Escolha uma pasta antes de arquivar.");
      return;
    }
    setErro(null);
    const { error } = await api.POST("/api/v1/pastas/{pasta_id}/propostas", {
      params: { path: { pasta_id: pastaAlvo } },
      body: { proposta_id: p.id },
    });
    const pasta = pastas.find((x) => x.id === pastaAlvo);
    if (error) setErro("Não foi possível arquivar a proposta na pasta.");
    else setOk(`Arquivada em “${pasta?.nome ?? "pasta"}”.`);
  }

  const lista = useMemo(
    () =>
      [...favoritos]
        .map((id) => propostas.get(id))
        .filter((p): p is Proposta => Boolean(p)),
    [favoritos, propostas],
  );

  // Favorito de proposta fora do território atual sai da RLS e não vem na
  // listagem — melhor dizer isso do que sumir com o item em silêncio.
  const foraDoAlcance = favoritos.size - lista.length;

  return (
    <>
      <PageHeader
        titulo="Favoritos e pastas"
        descricao="Sua curadoria: o que você marcou e como organizou."
      />

      {erro && <Aviso tom="erro">{erro}</Aviso>}
      {ok && <Aviso tom="ok">{ok}</Aviso>}

      <Card className="flex flex-col gap-4 p-4">
        <div className="flex flex-col gap-2">
          <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Pastas
          </h2>
          {pastas.length === 0 ? (
            <p className="text-sm text-muted">
              Nenhuma pasta ainda. Crie a primeira para agrupar propostas por tema, bairro
              ou emenda.
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {pastas.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setPastaAlvo(pastaAlvo === p.id ? null : p.id)}
                  aria-pressed={pastaAlvo === p.id}
                  className={cx(
                    "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm transition",
                    pastaAlvo === p.id
                      ? "border-brand bg-brand font-medium text-brand-fg"
                      : "border-line bg-bg text-ink-2 hover:border-line-strong hover:text-ink",
                  )}
                >
                  <span
                    aria-hidden
                    className="size-2.5 rounded-full"
                    style={{ backgroundColor: p.cor ?? "#6b7686" }}
                  />
                  {p.nome}
                  <span className="text-xs opacity-70">{formatDate(p.created_at)}</span>
                </button>
              ))}
            </div>
          )}
          {pastaAlvo && (
            <p className="text-xs text-muted">
              Pasta selecionada — use “Arquivar aqui” em qualquer favorito abaixo.
            </p>
          )}
        </div>

        <form onSubmit={criarPasta} className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-ink">Nova pasta</span>
            <Input
              value={novaPasta}
              onChange={(e) => setNovaPasta(e.target.value)}
              placeholder="Emendas 2026"
              maxLength={255}
              className="w-56"
            />
          </label>
          <div className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-ink">Cor</span>
            <div className="flex gap-1.5 pb-1">
              {CORES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setNovaCor(c)}
                  aria-label={`Cor ${c}`}
                  aria-pressed={novaCor === c}
                  className={cx(
                    "size-7 rounded-full border-2 transition",
                    novaCor === c ? "border-ink" : "border-transparent",
                  )}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>
          <Button type="submit" disabled={criando || !novaPasta.trim()}>
            {criando ? "Criando…" : "Criar pasta"}
          </Button>
        </form>
      </Card>

      <section className="flex flex-col gap-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Favoritos
        </h2>

        {carregando ? (
          <SkeletonList count={2} />
        ) : lista.length === 0 ? (
          <EmptyState
            titulo="Nenhuma proposta favoritada."
            descricao="Marque propostas com ☆ na Captação para acompanhá-las aqui."
            acao={
              <Link href="/painel/captacao">
                <Button variante="secondary">Ir para Captação</Button>
              </Link>
            }
          />
        ) : (
          <div className="flex flex-col gap-3">
            {lista.map((p) => (
              <div key={p.id} className="flex flex-col gap-2">
                <PropostaCard
                  proposta={p}
                  favorito
                  monitorada={monitoradas.has(p.id)}
                  onFavoritar={removerFavorito}
                  onPdf={(x) => void baixarPdfProposta(x.id)}
                />
                {pastas.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 pl-4 text-xs text-muted">
                    <span>Organizar:</span>
                    <Button
                      variante="secondary"
                      tamanho="sm"
                      onClick={() => adicionarNaPasta(p)}
                      disabled={!pastaAlvo}
                    >
                      Arquivar aqui
                    </Button>
                    {!pastaAlvo && <span>selecione uma pasta acima</span>}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {foraDoAlcance > 0 && (
          <p className="text-xs text-muted">
            <StatusBadge tone="neutral">{foraDoAlcance}</StatusBadge>{" "}
            {foraDoAlcance === 1 ? "favorito está" : "favoritos estão"} fora do território
            atual do seu perfil e não aparecem aqui.
          </p>
        )}
      </section>
    </>
  );
}
