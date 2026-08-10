"use client";

/**
 * Editor rich text do Class (TipTap).
 *
 * O corpo do artigo/aula passa a ser HTML de verdade — títulos, negrito,
 * listas, citações, links e VÍDEO EMBEDADO no meio do texto (YouTube, Vimeo,
 * Bunny ou arquivo mp4, tocado pelo Plyr). O HTML gerado aqui é o que a
 * página do artigo renderiza (sanitizado, com os vídeos trocados pelo
 * player). Conteúdo antigo em markdown leve é convertido na carga do editor.
 */

import Link from "@tiptap/extension-link";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useState } from "react";
import { VideoEmbed } from "@/components/editor/VideoEmbed";
import { cx } from "@/components/ui";

function BotaoBarra({
  ativo,
  onClick,
  title,
  children,
}: {
  ativo?: boolean;
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      // mousedown para não roubar o foco/seleção do editor
      onMouseDown={(e) => {
        e.preventDefault();
        onClick();
      }}
      className={cx(
        "rounded-md border px-2 py-1 font-mono text-[11px] uppercase tracking-[0.04em] transition-colors",
        ativo
          ? "border-ink bg-ink text-surface"
          : "border-hairline text-ink-2 hover:border-ink-3 hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function FormVideo({ editor, fechar }: { editor: Editor; fechar: () => void }) {
  const [url, setUrl] = useState("");
  const [orientacao, setOrientacao] = useState<"horizontal" | "vertical">("horizontal");
  function inserir() {
    const limpa = url.trim();
    if (!limpa) return;
    editor.chain().focus().inserirVideo({ src: limpa, orientacao }).run();
    fechar();
  }
  return (
    <div className="flex w-full flex-wrap items-end gap-2 rounded-lg border border-hairline bg-surface-2 p-2.5">
      <label className="flex min-w-56 flex-1 flex-col gap-1">
        <span className="field-label">URL do vídeo (YouTube, Vimeo, Bunny ou .mp4)</span>
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              inserir();
            }
          }}
          placeholder="https://www.youtube.com/watch?v=… · https://iframe.mediadelivery.net/embed/…"
          className="input"
          autoFocus
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="field-label">Orientação</span>
        <select
          value={orientacao}
          onChange={(e) => setOrientacao(e.target.value as "horizontal" | "vertical")}
          className="input w-32"
        >
          <option value="horizontal">Horizontal</option>
          <option value="vertical">Vertical</option>
        </select>
      </label>
      <button type="button" onClick={inserir} className="btn btn-primary btn-sm">
        Inserir no texto
      </button>
      <button type="button" onClick={fechar} className="btn btn-ghost btn-sm">
        Cancelar
      </button>
    </div>
  );
}

export function RichTextEditor({
  valor,
  aoMudar,
}: {
  /** HTML inicial (conteúdo legado em markdown deve ser convertido ANTES). */
  valor: string;
  aoMudar: (html: string) => void;
}) {
  const [formVideo, setFormVideo] = useState(false);
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] }, // h1 é o título do artigo, fora do corpo
      }),
      Link.configure({
        openOnClick: false,
        autolink: true,
        defaultProtocol: "https",
      }),
      VideoEmbed,
    ],
    content: valor,
    // SSR do App Router: renderiza só no cliente (evita mismatch de hidratação)
    immediatelyRender: false,
    onUpdate: ({ editor: e }) => aoMudar(e.getHTML()),
    editorProps: {
      attributes: { class: "rich-text focus:outline-none" },
    },
  });

  if (!editor) {
    return <div className="skeleton h-72 w-full rounded-lg" aria-hidden />;
  }

  function alternarLink() {
    if (editor!.isActive("link")) {
      editor!.chain().focus().unsetLink().run();
      return;
    }
    const url = window.prompt("URL do link:");
    if (url) editor!.chain().focus().setLink({ href: url }).run();
  }

  return (
    <div className="rich-editor rounded-lg border border-hairline bg-surface">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-hairline p-2">
        <BotaoBarra
          title="Título de seção"
          ativo={editor.isActive("heading", { level: 2 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
        >
          H2
        </BotaoBarra>
        <BotaoBarra
          title="Subtítulo"
          ativo={editor.isActive("heading", { level: 3 })}
          onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        >
          H3
        </BotaoBarra>
        <span className="mx-1 h-4 w-px bg-hairline" aria-hidden />
        <BotaoBarra
          title="Negrito"
          ativo={editor.isActive("bold")}
          onClick={() => editor.chain().focus().toggleBold().run()}
        >
          B
        </BotaoBarra>
        <BotaoBarra
          title="Itálico"
          ativo={editor.isActive("italic")}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        >
          I
        </BotaoBarra>
        <BotaoBarra
          title="Tachado"
          ativo={editor.isActive("strike")}
          onClick={() => editor.chain().focus().toggleStrike().run()}
        >
          S
        </BotaoBarra>
        <span className="mx-1 h-4 w-px bg-hairline" aria-hidden />
        <BotaoBarra
          title="Lista"
          ativo={editor.isActive("bulletList")}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        >
          • Lista
        </BotaoBarra>
        <BotaoBarra
          title="Lista numerada"
          ativo={editor.isActive("orderedList")}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        >
          1. Lista
        </BotaoBarra>
        <BotaoBarra
          title="Citação"
          ativo={editor.isActive("blockquote")}
          onClick={() => editor.chain().focus().toggleBlockquote().run()}
        >
          &ldquo;&rdquo;
        </BotaoBarra>
        <span className="mx-1 h-4 w-px bg-hairline" aria-hidden />
        <BotaoBarra title="Link" ativo={editor.isActive("link")} onClick={alternarLink}>
          Link
        </BotaoBarra>
        <BotaoBarra
          title="Inserir vídeo no texto (YouTube, Vimeo, Bunny, mp4)"
          ativo={formVideo}
          onClick={() => setFormVideo((v) => !v)}
        >
          ▸ Vídeo
        </BotaoBarra>
      </div>
      {formVideo && (
        <div className="border-b border-hairline p-2">
          <FormVideo editor={editor} fechar={() => setFormVideo(false)} />
        </div>
      )}
      <EditorContent editor={editor} className="max-h-[36rem] overflow-y-auto p-4" />
    </div>
  );
}
