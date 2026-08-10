"use client";

/**
 * Nó TipTap de VÍDEO EMBEDADO no corpo do artigo/aula.
 *
 * Serializa como `<div data-video="URL" data-orientacao="...">` — é esse
 * marcador que a página do artigo troca pelo player (Plyr) na renderização.
 * Dentro do editor, o node view mostra o player REAL (preview fiel) com um
 * botão de remover; o nó é atômico (não se edita por dentro).
 */

import { mergeAttributes, Node } from "@tiptap/core";
import {
  NodeViewWrapper,
  ReactNodeViewRenderer,
  type NodeViewProps,
} from "@tiptap/react";
import { HelpVideo } from "@/components/HelpVideo";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    videoEmbed: {
      /** Insere um vídeo (YouTube/Vimeo/Bunny/mp4) no ponto do cursor. */
      inserirVideo: (attrs: { src: string; orientacao?: string }) => ReturnType;
    };
  }
}

function VideoEmbedView({ node, deleteNode, selected }: NodeViewProps) {
  const src = String(node.attrs.src ?? "");
  const orientacao = String(node.attrs.orientacao ?? "horizontal");
  return (
    <NodeViewWrapper
      className={`video-embed relative my-3 rounded-lg ${
        selected ? "ring-2 ring-brand" : ""
      }`}
      data-drag-handle
    >
      <HelpVideo
        midia={{ id: "embed", url: src, orientacao }}
        compacto={orientacao === "vertical"}
      />
      <button
        type="button"
        onClick={deleteNode}
        title="Remover vídeo"
        className="absolute right-2 top-2 z-10 rounded-md border border-hairline bg-black/60 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.04em] text-white backdrop-blur transition-colors hover:bg-black/80"
      >
        × Remover
      </button>
    </NodeViewWrapper>
  );
}

export const VideoEmbed = Node.create({
  name: "videoEmbed",
  group: "block",
  atom: true,
  draggable: true,

  addAttributes() {
    return {
      src: { default: "" },
      orientacao: { default: "horizontal" },
    };
  },

  parseHTML() {
    return [
      {
        tag: "div[data-video]",
        getAttrs: (el) => ({
          src: (el as HTMLElement).getAttribute("data-video") ?? "",
          orientacao:
            (el as HTMLElement).getAttribute("data-orientacao") ?? "horizontal",
        }),
      },
    ];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-video": node.attrs.src,
        "data-orientacao": node.attrs.orientacao,
        class: "video-embed",
      }),
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(VideoEmbedView);
  },

  addCommands() {
    return {
      inserirVideo:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs }),
    };
  },
});
