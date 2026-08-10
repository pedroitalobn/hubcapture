"use client";

/**
 * Renderizador do corpo do artigo/aula do Class.
 *
 * Dois formatos convivem: o corpo NOVO é HTML do editor rich text (TipTap),
 * sanitizado aqui com DOMPurify e com os marcadores `div[data-video]`
 * trocados pelo player (Plyr) — é assim que o vídeo aparece NO MEIO do
 * texto; o corpo LEGADO é markdown leve (## título · - lista · **negrito**),
 * renderizado pelo caminho antigo. `markdownLeveParaHtml` faz a conversão
 * quando o editor abre um conteúdo legado.
 */

import { useEffect, useState, type ReactNode } from "react";
import { HelpVideo } from "@/components/HelpVideo";

/** O corpo veio do editor rich text (HTML) ou é markdown leve legado? */
export function corpoEhHtml(corpo: string): boolean {
  return /^\s*</.test(corpo);
}

function escaparHtml(texto: string): string {
  return texto
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function negritoInline(texto: string): string {
  return texto.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

/** Converte o markdown leve legado para o HTML do editor (carga única). */
export function markdownLeveParaHtml(md: string): string {
  const blocos = md.replaceAll("\r\n", "\n").split(/\n{2,}/);
  const html: string[] = [];
  for (const bloco of blocos) {
    const linhas = bloco.split("\n").filter((l) => l.trim() !== "");
    if (linhas.length === 0) continue;
    if (linhas.every((l) => l.trimStart().startsWith("- "))) {
      const itens = linhas
        .map((l) => `<li>${negritoInline(escaparHtml(l.trimStart().slice(2)))}</li>`)
        .join("");
      html.push(`<ul>${itens}</ul>`);
      continue;
    }
    const primeira = linhas[0]!;
    if (primeira.startsWith("## ")) {
      html.push(`<h2>${negritoInline(escaparHtml(primeira.slice(3)))}</h2>`);
      continue;
    }
    html.push(
      `<p>${linhas.map((l) => negritoInline(escaparHtml(l))).join("<br>")}</p>`,
    );
  }
  return html.join("");
}

// ── Corpo HTML (editor novo) ────────────────────────────────────────────────

type Segmento =
  | { tipo: "html"; html: string }
  | { tipo: "video"; src: string; orientacao: string };

/**
 * Sanitiza e fatia o HTML nos marcadores de vídeo. Roda só no navegador
 * (DOMPurify/DOMParser precisam de DOM) — no SSR renderiza o esqueleto.
 */
function CorpoHtml({ html }: { html: string }) {
  const [segmentos, setSegmentos] = useState<Segmento[] | null>(null);

  useEffect(() => {
    let vivo = true;
    void (async () => {
      const { default: DOMPurify } = await import("dompurify");
      const limpo = DOMPurify.sanitize(html, {
        ALLOWED_TAGS: [
          "p", "h2", "h3", "strong", "em", "s", "u", "a",
          "ul", "ol", "li", "blockquote", "br", "hr",
          "div", "span", "code", "pre",
        ],
        ALLOWED_ATTR: ["href", "target", "rel", "data-video", "data-orientacao", "class"],
      });
      const doc = new DOMParser().parseFromString(limpo, "text/html");
      const segs: Segmento[] = [];
      let buffer = "";
      const despejar = () => {
        if (buffer.trim() !== "") segs.push({ tipo: "html", html: buffer });
        buffer = "";
      };
      doc.body.childNodes.forEach((node) => {
        if (node instanceof HTMLElement && node.hasAttribute("data-video")) {
          despejar();
          segs.push({
            tipo: "video",
            src: node.getAttribute("data-video") ?? "",
            orientacao: node.getAttribute("data-orientacao") ?? "horizontal",
          });
        } else if (node instanceof HTMLElement) {
          buffer += node.outerHTML;
        } else if (node.textContent) {
          buffer += escaparHtml(node.textContent);
        }
      });
      despejar();
      if (vivo) setSegmentos(segs);
    })();
    return () => {
      vivo = false;
    };
  }, [html]);

  if (segmentos === null) {
    return <div className="skeleton h-40 w-full" aria-hidden />;
  }

  return (
    <div className="rich-text">
      {segmentos.map((s, i) =>
        s.tipo === "video" ? (
          <HelpVideo
            key={i}
            midia={{ id: `corpo-${i}`, url: s.src, orientacao: s.orientacao }}
            className="my-4"
          />
        ) : (
          // sanitizado logo acima com allowlist estrita — este é o único
          // dangerouslySetInnerHTML do app, e ele nunca vê HTML cru da fonte
          <div key={i} dangerouslySetInnerHTML={{ __html: s.html }} />
        ),
      )}
    </div>
  );
}

// ── Corpo legado (markdown leve) ────────────────────────────────────────────

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

function CorpoMarkdown({ corpo }: { corpo: string }) {
  const blocos = corpo.replaceAll("\r\n", "\n").split(/\n{2,}/);
  return (
    <div className="flex flex-col gap-4">
      {blocos.map((bloco, bi) => {
        const linhas = bloco.split("\n").filter((l) => l.trim() !== "");
        const primeira = linhas[0];
        if (primeira === undefined) return null;
        if (linhas.every((l) => l.trimStart().startsWith("- "))) {
          return (
            <ul
              key={bi}
              className="flex list-disc flex-col gap-1.5 pl-5 text-sm leading-relaxed text-ink-2"
            >
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

/** Porta única: decide o formato e renderiza o corpo completo. */
export function CorpoConteudo({ corpo }: { corpo: string }) {
  return corpoEhHtml(corpo) ? <CorpoHtml html={corpo} /> : <CorpoMarkdown corpo={corpo} />;
}
