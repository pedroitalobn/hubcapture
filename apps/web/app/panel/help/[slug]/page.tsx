"use client";

/**
 * Artigo da Central de ajuda — a página do link compartilhável.
 *
 * É aqui que chegam as três portas do help desk: a listagem da Central, o
 * "Artigo completo →" do popover de hint e o link copiado/colado no WhatsApp
 * da equipe. Corpo em markdown leve (títulos, listas, negrito), vídeos
 * horizontais e verticais (com picture-in-picture) e documentos anexos.
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
  midias: Midia[];
  updated_at?: string | null;
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

export default function ArtigoAjudaPage() {
  const params = useParams<{ slug: string }>();
  const [artigo, setArtigo] = useState<Artigo | null>(null);
  const [erro, setErro] = useState(false);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => {
    void (async () => {
      const { data, error } = await api.GET("/api/v1/help/articles/{slug}", {
        params: { path: { slug: params.slug } },
      });
      if (error || !data) {
        setErro(true);
        return;
      }
      setArtigo(data as Artigo);
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
        <Link href="/panel/help" className="btn btn-ghost btn-sm">
          ← Central de ajuda
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
          <Link
            href="/panel/help"
            className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 transition-colors hover:text-ink"
          >
            ← Central de ajuda
          </Link>
          {artigo.categoria && <p className="label-mono mt-2">{artigo.categoria.nome}</p>}
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
    </div>
  );
}
