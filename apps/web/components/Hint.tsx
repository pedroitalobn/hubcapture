"use client";

/**
 * Hint contextual — o ⓘ ao lado do elemento que o artigo explica.
 *
 * `<Hint chave="proposta.empenhado" />` ao lado do rótulo "Empenhado": se o
 * admin plantou um artigo naquela chave (e ele está publicado), aparece o
 * ícone; clicou, abre um popover com o resumo, o PRIMEIRO vídeo do artigo
 * (com picture-in-picture — dá para assistir sem sair da proposta) e o link
 * para o artigo completo no Class. Sem hint plantado, o componente
 * não renderiza nada — plantar/despublicar é decisão do admin, sem deploy.
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import { useHint } from "@/lib/help";
import { HelpVideo, type MidiaVideo } from "@/components/HelpVideo";
import { cx } from "@/components/ui";

interface ArtigoPopover {
  midias?: {
    id: string;
    tipo: string;
    url?: string | null;
    titulo?: string | null;
    orientacao?: string | null;
  }[];
}

export function Hint({ chave, className }: { chave: string; className?: string }) {
  const hint = useHint(chave);
  const [aberto, setAberto] = useState(false);
  const [video, setVideo] = useState<MidiaVideo | null>(null);
  const [copiado, setCopiado] = useState(false);
  const buscouVideo = useRef(false);
  const raiz = useRef<HTMLSpanElement>(null);

  // fecha no clique fora e no Esc — comportamento padrão de popover
  useEffect(() => {
    if (!aberto) return;
    function aoClicar(e: MouseEvent) {
      // com o vídeo em picture-in-picture, clique fora NÃO fecha: fechar
      // desmontaria o <video> e derrubaria a janelinha flutuante — a graça é
      // justamente navegar pela proposta com o vídeo rodando ao lado.
      if (document.pictureInPictureElement) return;
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAberto(false);
    }
    function aoTeclar(e: KeyboardEvent) {
      if (e.key === "Escape") setAberto(false);
    }
    document.addEventListener("mousedown", aoClicar);
    document.addEventListener("keydown", aoTeclar);
    return () => {
      document.removeEventListener("mousedown", aoClicar);
      document.removeEventListener("keydown", aoTeclar);
    };
  }, [aberto]);

  // o mapa de hints não carrega mídias; o primeiro vídeo vem do artigo,
  // buscado UMA vez na primeira abertura (quem nunca clica não paga nada)
  useEffect(() => {
    if (!aberto || buscouVideo.current || !hint) return;
    buscouVideo.current = true;
    void (async () => {
      const { data } = await api.GET("/api/v1/class/articles/{slug}", {
        params: { path: { slug: hint.artigo_slug } },
      });
      const v = ((data as ArtigoPopover | undefined)?.midias ?? []).find(
        (m) => m.tipo === "video",
      );
      if (v) setVideo(v);
    })();
  }, [aberto, video, hint]);

  if (!hint) return null;

  async function copiarLink() {
    try {
      await navigator.clipboard.writeText(
        `${window.location.origin}/panel/class/${hint!.artigo_slug}`,
      );
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* clipboard bloqueado — o link continua acessível pelo artigo */
    }
  }

  return (
    <span ref={raiz} className={cx("relative inline-flex", className)}>
      <button
        type="button"
        aria-label={`Ajuda: ${hint.titulo}`}
        aria-expanded={aberto}
        title={hint.titulo}
        onClick={(e) => {
          // o ícone convive dentro de linhas/links clicáveis — o clique é dele
          e.preventDefault();
          e.stopPropagation();
          setAberto((v) => !v);
        }}
        className={cx(
          "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border font-mono text-[10px] leading-none transition-colors",
          aberto
            ? "border-ink-2 text-ink"
            : "border-hairline text-ink-3 hover:border-ink-3 hover:text-ink",
        )}
      >
        ?
      </button>

      {aberto && (
        <span
          role="dialog"
          aria-label={hint.titulo}
          className="card anim-pop absolute left-1/2 top-full z-50 mt-2 block w-[19rem] -translate-x-1/2 cursor-auto p-4 text-left shadow-xl sm:w-80"
          onClick={(e) => e.stopPropagation()}
        >
          <span className="label-mono block">Class</span>
          <span className="mt-1 block text-sm font-semibold leading-snug text-ink">
            {hint.titulo}
          </span>
          {hint.resumo && (
            <span className="mt-1.5 block text-xs leading-relaxed text-ink-2">
              {hint.resumo}
            </span>
          )}
          {video && <HelpVideo midia={video} compacto className="mt-3 block" />}
          <span className="mt-3 flex items-center justify-between gap-2 border-t border-hairline pt-2.5">
            <Link
              href={`/panel/class/${hint.artigo_slug}`}
              className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 transition-colors hover:text-ink"
            >
              Artigo completo →
            </Link>
            <button
              type="button"
              onClick={copiarLink}
              className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 transition-colors hover:text-ink"
            >
              {copiado ? "✓ Copiado" : "Copiar link"}
            </button>
          </span>
        </span>
      )}
    </span>
  );
}
