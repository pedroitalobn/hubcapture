"use client";

/**
 * Módulo do Class — a trilha de aulas em sequência.
 *
 * O módulo é o índice do "curso": descrição e a lista ordenada de aulas
 * (aula é um artigo com módulo — a página da aula é a mesma do artigo, que
 * mostra "aula N de M" e a navegação anterior/próxima).
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { Skeleton } from "@/components/Skeleton";
import { Aviso } from "@/components/ui";

interface Aula {
  id: string;
  titulo: string;
  slug: string;
  resumo?: string | null;
  videos: number;
  documentos: number;
}

interface Modulo {
  id: string;
  titulo: string;
  slug: string;
  descricao?: string | null;
  aulas: Aula[];
}

export default function ModuloClassPage() {
  const params = useParams<{ slug: string }>();
  const [modulo, setModulo] = useState<Modulo | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    void (async () => {
      const { data, error } = await api.GET("/api/v1/class/modules/{slug}", {
        params: { path: { slug: params.slug } },
      });
      if (error || !data) {
        setErro(true);
        return;
      }
      setModulo(data as Modulo);
    })();
  }, [params.slug]);

  if (erro) {
    return (
      <div className="flex flex-col items-start gap-4">
        <Aviso tom="erro">
          Módulo não encontrado — pode ter sido despublicado ou o link mudou.
        </Aviso>
        <Link href="/panel/class" className="btn btn-ghost btn-sm">
          ← Class
        </Link>
      </div>
    );
  }

  if (!modulo) {
    return (
      <div className="flex flex-col gap-5">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-52 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
      <header>
        <Link
          href="/panel/class"
          className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 transition-colors hover:text-ink"
        >
          ← Class
        </Link>
        <p className="label-mono mt-2">
          Módulo · {modulo.aulas.length} aula{modulo.aulas.length === 1 ? "" : "s"}
        </p>
        <h1 className="page-title mt-1">{modulo.titulo}</h1>
        {modulo.descricao && (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink-2">
            {modulo.descricao}
          </p>
        )}
      </header>

      {modulo.aulas.length === 0 ? (
        <p className="text-sm text-ink-3">Este módulo ainda não tem aulas publicadas.</p>
      ) : (
        <ol className="card flex flex-col divide-y divide-hairline px-5">
          {modulo.aulas.map((a, i) => (
            <li key={a.id}>
              <Link
                href={`/panel/class/${a.slug}`}
                className="group flex items-baseline gap-4 py-4"
              >
                {/* o número da aula é a espinha da trilha — sempre visível */}
                <span className="num w-8 shrink-0 text-right text-sm text-ink-3">
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold leading-snug text-ink group-hover:underline">
                    {a.titulo}
                  </span>
                  {a.resumo && (
                    <span className="mt-1 line-clamp-2 block text-xs leading-relaxed text-ink-2">
                      {a.resumo}
                    </span>
                  )}
                  {(a.videos > 0 || a.documentos > 0) && (
                    <span className="mt-1.5 flex gap-3 font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
                      {a.videos > 0 && <span>▸ vídeo</span>}
                      {a.documentos > 0 && <span>⇩ material</span>}
                    </span>
                  )}
                </span>
                <span className="shrink-0 font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 group-hover:text-ink">
                  Assistir →
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
