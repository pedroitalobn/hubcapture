"use client";

/**
 * Player de vídeo da Central de ajuda.
 *
 * Três origens, um componente: YouTube/Vimeo viram iframe de embed; URL de
 * arquivo (mp4 hospedado) e UPLOAD do admin tocam em <video> nativo — e aí o
 * botão "Picture-in-picture" destaca o vídeo numa janela flutuante, para o
 * gestor assistir a explicação SEM sair da página da proposta. A orientação
 * (horizontal 16:9 × vertical 9:16) vem do cadastro da mídia, não de sniffing.
 */

import { useEffect, useRef, useState } from "react";
import { urlDaMidia, urlDeEmbed } from "@/lib/help";
import { cx } from "@/components/ui";

export interface MidiaVideo {
  id: string;
  url?: string | null;
  titulo?: string | null;
  orientacao?: string | null; // 'horizontal' | 'vertical'
  mime?: string | null;
}

export function HelpVideo({
  midia,
  compacto = false,
  className,
}: {
  midia: MidiaVideo;
  /** No popover do hint o player é menor (o artigo completo usa o tamanho cheio). */
  compacto?: boolean;
  className?: string;
}) {
  const vertical = midia.orientacao === "vertical";
  const embed = midia.url ? urlDeEmbed(midia.url) : null;
  const videoRef = useRef<HTMLVideoElement>(null);
  // upload (sem url): busca autenticada → object URL; revoga ao desmontar
  const [src, setSrc] = useState<string | null>(midia.url && !embed ? midia.url : null);
  const [erro, setErro] = useState(false);
  const [pipDisponivel, setPipDisponivel] = useState(false);

  useEffect(() => {
    if (midia.url) return;
    let ativo = true;
    let objUrl: string | null = null;
    void urlDaMidia(midia.id)
      .then((u) => {
        objUrl = u;
        if (ativo) setSrc(u);
        else URL.revokeObjectURL(u);
      })
      .catch(() => ativo && setErro(true));
    return () => {
      ativo = false;
      if (objUrl) URL.revokeObjectURL(objUrl);
    };
  }, [midia.id, midia.url]);

  useEffect(() => {
    // PiP nativo só existe para <video> (e não em todo navegador)
    setPipDisponivel(
      typeof document !== "undefined" && Boolean(document.pictureInPictureEnabled),
    );
  }, []);

  async function abrirPip() {
    const video = videoRef.current;
    if (!video) return;
    try {
      if (document.pictureInPictureElement === video) {
        await document.exitPictureInPicture();
      } else {
        await video.requestPictureInPicture();
        // em PiP o vídeo continua na janelinha mesmo navegando na página
        void video.play().catch(() => undefined);
      }
    } catch {
      /* navegador recusou (política/foco) — o player normal segue valendo */
    }
  }

  // vertical: player estreito e centrado (formato Reels/Shorts); horizontal: 16:9
  const moldura = vertical
    ? cx("aspect-[9/16] w-full", compacto ? "max-w-[200px]" : "max-w-[300px]", "mx-auto")
    : "aspect-video w-full";

  if (erro) {
    return (
      <p className={cx("text-xs text-ink-3", className)}>
        Não foi possível carregar o vídeo.
      </p>
    );
  }

  return (
    <figure className={className}>
      {embed ? (
        <div className={cx(moldura, "overflow-hidden rounded-lg border border-hairline")}>
          <iframe
            src={embed}
            title={midia.titulo ?? "Vídeo de ajuda"}
            className="h-full w-full"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
          />
        </div>
      ) : (
        <div className={cx(moldura, "relative")}>
          {src ? (
            <video
              ref={videoRef}
              src={src}
              controls
              playsInline
              preload="metadata"
              className="h-full w-full rounded-lg border border-hairline bg-black object-contain"
            />
          ) : (
            <div className="skeleton h-full w-full rounded-lg" aria-hidden />
          )}
          {pipDisponivel && src && (
            <button
              type="button"
              onClick={abrirPip}
              title="Assistir em picture-in-picture (janela flutuante)"
              className="absolute right-2 top-2 rounded-md border border-hairline bg-black/60 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.04em] text-white backdrop-blur transition-colors hover:bg-black/80"
            >
              ⧉ PiP
            </button>
          )}
        </div>
      )}
      {midia.titulo && (
        <figcaption className="mt-1.5 text-xs text-ink-3">{midia.titulo}</figcaption>
      )}
    </figure>
  );
}
