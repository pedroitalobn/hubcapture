"use client";

/**
 * Artigo/aula do Class — a página do link compartilhável.
 *
 * É aqui que chegam as três portas do help desk: a listagem do Class, o
 * "Artigo completo →" do popover de hint e o link copiado/colado no WhatsApp
 * da equipe. Corpo em markdown leve (títulos, listas, negrito), vídeos
 * horizontais e verticais (com picture-in-picture) e documentos anexos.
 * Quando o artigo é uma AULA (tem módulo), a mesma página ganha a trilha:
 * "aula N de M" no cabeçalho e a navegação anterior/próxima no rodapé.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api/client";
import { baixarMidia } from "@/lib/help";
import { HelpVideo } from "@/components/HelpVideo";
import { Skeleton } from "@/components/Skeleton";
import { Aviso } from "@/components/ui";

interface Midia {
  id: string;
  tipo: string;
  titulo?: string | null;
  url?: string | null;
  orientacao?: string | null;
  nome_arquivo?: string | null;
  mime?: string | null;
  tamanho?: number | null;
}

interface Artigo {
  id: string;
  titulo: string;
  slug: string;
  resumo?: string | null;
  corpo: string;
  categoria?: { nome: string; slug: string } | null;
  modulo?: { titulo: string; slug: string } | null;
  midias: Midia[];
  updated_at?: string | null;
}

interface AulaVizinha {
  titulo: string;
  slug: string;
}

/** Posição desta aula na trilha do módulo + vizinhas (anterior/próxima). */
interface Trilha {
  indice: number; // 1-based
  total: number;
  anterior: AulaVizinha | null;
  proxima: AulaVizinha | null;
}

/** Negrito inline (**texto**) — o único enfeite de linha que o corpo aceita. */
function linha(texto: string, chave: number): ReactNode {
  const partes = texto.split(/\*\*(.+?)\*\*/g);
  if (partes.length === 1) return texto;
  return (
    <span key={chave}>
      {partes.map((p, i) =>
        i % 2 === 1 ? <strong key={i}>{p}</strong> : <span key={i}>{p}</span>,
      )}
    </span>
  );
}

/**
 * Markdown leve, sem dependência e sem HTML cru (nada de
 * dangerouslySetInnerHTML): blocos separados por linha em branco; `## `
 * vira subtítulo, `- ` vira lista, o resto é parágrafo.
 */
function CorpoArtigo({ corpo }: { corpo: string }) {
  const blocos = corpo.replaceAll("\r\n", "\n").split(/\n{2,}/);
  return (
    <div className="flex flex-col gap-4">
      {blocos.map((bloco, bi) => {
        const linhas = bloco.split("\n").filter((l) => l.trim() !== "");
        const primeira = linhas[0];
        if (primeira === undefined) return null;
        if (linhas.every((l) => l.trimStart().startsWith("- "))) {
          return (
            <ul key={bi} className="flex list-disc flex-col gap-1.5 pl-5 text-sm leading-relaxed text-ink-2">
              {linhas.map((l, li) => (
                <li key={li}>{linha(l.trimStart().slice(2), li)}</li>
              ))}
            </ul>
          );
        }
        if (primeira.startsWith("## ")) {
          return (
            <h2 key={bi} className="mt-2 text-base font-semibold tracking-tight text-ink">
              {primeira.slice(3)}
            </h2>
          );
        }
        return (
          <p key={bi} className="text-sm leading-relaxed text-ink-2">
            {linhas.map((l, li) => (
              <span key={li}>
                {li > 0 && <br />}
                {linha(l, li)}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function tamanhoLegivel(bytes?: number | null): string {
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ArtigoClassPage() {
  const params = useParams<{ slug: string }>();
  const [artigo, setArtigo] = useState<Artigo | null>(null);
  const [trilha, setTrilha] = useState<Trilha | null>(null);
  const [erro, setErro] = useState(false);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    void (async () => {
      const { data, error } = await api.GET("/api/v1/class/articles/{slug}", {
        params: { path: { slug: params.slug } },
      });
      if (error || !data) {
        setErro(true);
        return;
      }
      const a = data as Artigo;
      setArtigo(a);
      setTrilha(null);

      // aula: busca o módulo para saber a posição e as vizinhas
      if (a.modulo) {
        const mod = await api.GET("/api/v1/class/modules/{slug}", {
          params: { path: { slug: a.modulo.slug } },
        });
        const aulas =
          ((mod.data as { aulas?: AulaVizinha[] } | undefined)?.aulas ?? []);
        const i = aulas.findIndex((x) => x.slug === a.slug);
        if (i >= 0) {
          setTrilha({
            indice: i + 1,
            total: aulas.length,
            anterior: aulas[i - 1] ?? null,
            proxima: aulas[i + 1] ?? null,
          });
        }
      }
    })();
  }, [params.slug]);

  async function compartilhar() {
    const url = window.location.href;
    // no celular abre a folha nativa; onde não existe, copia o link
    if (navigator.share) {
      try {
        await navigator.share({ title: artigo?.titulo, url });
        return;
      } catch {
        /* usuário fechou a folha */
      }
    }
    await navigator.clipboard.writeText(url).catch(() => undefined);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  }

  if (erro) {
    return (
      <div className="flex flex-col items-start gap-4">
        <Aviso tom="erro">
          Artigo não encontrado — pode ter sido despublicado ou o link mudou.
        </Aviso>
        <Link href="/panel/class" className="btn btn-ghost btn-sm">
          ← Class
        </Link>
      </div>
    );
  }

  if (!artigo) {
    return (
      <div className="flex flex-col gap-5">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-52 w-full" />
      </div>
    );
  }

  const videos = artigo.midias.filter((m) => m.tipo === "video");
  const documentos = artigo.midias.filter((m) => m.tipo === "documento");

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
      <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <div className="min-w-0">
          {/* aula volta para o índice do módulo; artigo avulso, para o Class */}
          <Link
            href={
              artigo.modulo
                ? `/panel/class/modules/${artigo.modulo.slug}`
                : "/panel/class"
            }
            className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 transition-colors hover:text-ink"
          >
            ← {artigo.modulo ? artigo.modulo.titulo : "Class"}
          </Link>
          {artigo.modulo ? (
            <p className="label-mono mt-2">
              {trilha ? `Aula ${trilha.indice} de ${trilha.total}` : "Aula"}
            </p>
          ) : (
            artigo.categoria && <p className="label-mono mt-2">{artigo.categoria.nome}</p>
          )}
          <h1 className="page-title mt-1">{artigo.titulo}</h1>
          {artigo.resumo && (
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-2">
              {artigo.resumo}
            </p>
          )}
        </div>
        <button onClick={compartilhar} className="btn btn-ghost btn-sm shrink-0">
          {copiado ? "✓ Link copiado" : "Compartilhar"}
        </button>
      </header>

      {artigo.corpo.trim() !== "" && (
        <section className="card p-6">
          <CorpoArtigo corpo={artigo.corpo} />
        </section>
      )}

      {videos.length > 0 && (
        <section className="card p-6">
          <h2 className="label-mono mb-4 border-b border-hairline pb-2">Vídeos</h2>
          <div className="flex flex-col gap-6">
            {videos.map((v) => (
              <HelpVideo key={v.id} midia={v} />
            ))}
          </div>
        </section>
      )}

      {documentos.length > 0 && (
        <section className="card p-6">
          <h2 className="label-mono mb-3 border-b border-hairline pb-2">Materiais</h2>
          <ul>
            {documentos.map((d) => (
              <li key={d.id} className="data-row">
                <span className="text-sm text-ink">
                  {d.titulo || d.nome_arquivo || "Documento"}
                </span>
                <span className="flex shrink-0 items-baseline gap-3">
                  {d.tamanho ? (
                    <span className="num text-xs text-ink-3">
                      {tamanhoLegivel(d.tamanho)}
                    </span>
                  ) : null}
                  {d.url ? (
                    <a
                      href={d.url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 hover:text-ink"
                    >
                      Abrir ↗
                    </a>
                  ) : (
                    <button
                      onClick={() =>
                        void baixarMidia(d.id, d.nome_arquivo ?? "material")
                      }
                      className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 hover:text-ink"
                    >
                      ⇩ Baixar
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Trilha do módulo: anterior/próxima aula ──────────────────── */}
      {trilha && (trilha.anterior || trilha.proxima) && (
        <nav
          aria-label="Navegação entre aulas"
          className="flex items-stretch justify-between gap-3"
        >
          {trilha.anterior ? (
            <Link
              href={`/panel/class/${trilha.anterior.slug}`}
              className="card block max-w-[48%] flex-1 p-4"
            >
              <span className="label-mono block">← Aula anterior</span>
              <span className="mt-1 block truncate text-sm text-ink">
                {trilha.anterior.titulo}
              </span>
            </Link>
          ) : (
            <span aria-hidden className="flex-1" />
          )}
          {trilha.proxima ? (
            <Link
              href={`/panel/class/${trilha.proxima.slug}`}
              className="card block max-w-[48%] flex-1 p-4 text-right"
            >
              <span className="label-mono block">Próxima aula →</span>
              <span className="mt-1 block truncate text-sm text-ink">
                {trilha.proxima.titulo}
              </span>
            </Link>
          ) : (
            <span aria-hidden className="flex-1" />
          )}
        </nav>
      )}
    </div>
  );
}
