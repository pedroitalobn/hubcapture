"use client";

/**
 * Player de vídeo do Class — Plyr em todas as fontes que ele suporta.
 *
 * Quatro origens, um componente: YouTube e Vimeo tocam no Plyr com o provider
 * de embed nativo; arquivo direto (mp4/webm, hospedado ou UPLOAD do admin)
 * toca no Plyr html5 — com picture-in-picture, para o gestor assistir a
 * explicação SEM sair da página da proposta; Bunny Stream (e outros /embed/
 * desconhecidos) rendem o iframe do próprio provedor, que já traz player.
 *
 * IMPORTANTE (estrutura): o Plyr embrulha/move o elemento alvo no DOM, o que
 * quebra a desmontagem do React se o alvo for um nó renderizado por JSX. Por
 * isso o React só é dono do HOLDER — o elemento de mídia é criado
 * imperativamente dentro dele e destruído no cleanup, e o React nunca
 * enxerga a bagunça interna do player.
 */

import { useEffect, useRef, useState } from "react";
import type Plyr from "plyr";
import { analisarVideo, urlDaMidia, type FonteVideo } from "@/lib/help";
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
  const fonte: FonteVideo | null = midia.url ? analisarVideo(midia.url) : null;
  const holderRef = useRef<HTMLDivElement>(null);
  // upload (sem url): busca autenticada → object URL; revoga ao desmontar
  const [src, setSrc] = useState<string | null>(
    fonte && fonte.modo === "arquivo" ? fonte.src : null,
  );
  const [erro, setErro] = useState(false);

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

  const modo = fonte?.modo ?? "arquivo";
  const embedId = fonte && (fonte.modo === "youtube" || fonte.modo === "vimeo") ? fonte.id : null;

  // Plyr é browser-only (referencia document) → import dinâmico no effect.
  useEffect(() => {
    if (modo === "iframe") return; // player do provedor (Bunny etc.), Plyr fora
    if (modo === "arquivo" && !src) return; // upload ainda baixando
    const holder = holderRef.current;
    if (!holder) return;

    // o alvo do Plyr é criado AQUI, fora do JSX — ver comentário do topo
    let alvo: HTMLElement;
    if (modo === "arquivo") {
      const video = document.createElement("video");
      video.src = src!;
      video.playsInline = true;
      video.preload = "metadata";
      video.controls = true;
      alvo = video;
    } else {
      const div = document.createElement("div");
      div.dataset.plyrProvider = modo;
      div.dataset.plyrEmbedId = embedId ?? "";
      alvo = div;
    }
    holder.replaceChildren(alvo);

    let player: Plyr | null = null;
    let vivo = true;
    void import("plyr").then(({ default: PlyrCtor }) => {
      if (!vivo) return;
      player = new PlyrCtor(alvo, {
        // PiP no html5: o gestor solta o vídeo numa janelinha e segue na página
        controls: [
          "play-large",
          "play",
          "progress",
          "current-time",
          "mute",
          "volume",
          "settings",
          ...(modo === "arquivo" ? ["pip"] : []),
          "fullscreen",
        ],
        ratio: vertical ? "9:16" : "16:9",
        youtube: { noCookie: true },
      });
    });
    return () => {
      vivo = false;
      player?.destroy();
      holder.replaceChildren();
    };
  }, [modo, embedId, src, vertical]);

  // vertical: player estreito e centrado (formato Reels/Shorts); horizontal: 16:9
  const moldura = vertical
    ? cx("w-full", compacto ? "max-w-[200px]" : "max-w-[300px]", "mx-auto")
    : "w-full";

  if (erro) {
    return (
      <p className={cx("text-xs text-ink-3", className)}>
        Não foi possível carregar o vídeo.
      </p>
    );
  }

  return (
    <figure className={className}>
      <div className={cx(moldura, "overflow-hidden rounded-lg border border-hairline")}>
        {fonte?.modo === "iframe" ? (
          // Bunny/embeds desconhecidos: o iframe do provedor já traz o player
          <div className={vertical ? "aspect-[9/16]" : "aspect-video"}>
            <iframe
              src={fonte.src}
              title={midia.titulo ?? "Vídeo"}
              className="h-full w-full"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowFullScreen
            />
          </div>
        ) : modo === "arquivo" && !src ? (
          <div
            className={cx("skeleton", vertical ? "aspect-[9/16]" : "aspect-video")}
            aria-hidden
          />
        ) : (
          // holder: o React é dono deste div; o Plyr, do que há dentro dele
          <div ref={holderRef} />
        )}
      </div>
      {midia.titulo && (
        <figcaption className="mt-1.5 text-xs text-ink-3">{midia.titulo}</figcaption>
      )}
    </figure>
  );
}
