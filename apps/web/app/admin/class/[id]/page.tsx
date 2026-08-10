"use client";

/**
 * Editor de artigo/aula do Class (admin).
 *
 * Três blocos: o CONTEÚDO (texto em markdown leve + publicação + o VÍNCULO
 * com módulo — escolher um módulo e a posição transforma o artigo em AULA da
 * trilha), as MÍDIAS (vídeo por URL ou arquivo, horizontal/vertical;
 * documentos anexos) e os HINTS — onde este conteúdo vira o ícone ⓘ no
 * painel. O admin escolhe a chave no catálogo (ex.: "Empenhado — Detalhe da
 * proposta") e o ícone passa a aparecer ao lado daquele dado, sem deploy.
 */

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, enviarMidiaAjuda } from "@/lib/api/client";
import { corpoEhHtml, markdownLeveParaHtml } from "@/components/CorpoConteudo";
import { RichTextEditor } from "@/components/RichTextEditor";
import { StatusBadge } from "@/components/StatusBadge";
import { Skeleton } from "@/components/Skeleton";
import { Aviso } from "@/components/ui";

interface Categoria {
  id: string;
  nome: string;
}

interface Midia {
  id: string;
  tipo: string;
  titulo?: string | null;
  url?: string | null;
  orientacao?: string | null;
  nome_arquivo?: string | null;
  tamanho?: number | null;
}

interface Modulo {
  id: string;
  titulo: string;
}

interface Artigo {
  id: string;
  titulo: string;
  slug: string;
  resumo?: string | null;
  corpo: string;
  publicado: boolean;
  ordem: number;
  categoria?: { id: string; nome: string } | null;
  modulo?: { id: string; titulo: string; slug: string } | null;
  midias: Midia[];
}

interface ChaveCatalogo {
  chave: string;
  rotulo: string;
  tela: string;
}

interface HintAdmin {
  id: string;
  chave: string;
  artigo_id: string;
  ativo: boolean;
  artigo_titulo: string;
}

export default function AdminHelpdeskEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();

  const [artigo, setArtigo] = useState<Artigo | null>(null);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [catalogo, setCatalogo] = useState<ChaveCatalogo[]>([]);
  const [hints, setHints] = useState<HintAdmin[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  // formulário do conteúdo. `corpo` é HTML do editor rich text; null = ainda
  // não carregado (o editor só monta com o valor inicial pronto — ele é
  // não-controlado e daí em diante o espelho vem de `aoMudar`).
  const [titulo, setTitulo] = useState("");
  const [resumo, setResumo] = useState("");
  const [corpo, setCorpo] = useState<string | null>(null);
  const [categoriaId, setCategoriaId] = useState("");
  // vínculo com módulo: preenchido = este conteúdo é uma AULA da trilha
  const [moduloId, setModuloId] = useState("");
  const [ordem, setOrdem] = useState(0);
  const [salvando, setSalvando] = useState(false);

  // mídia por URL
  const [urlVideo, setUrlVideo] = useState("");
  const [tituloVideo, setTituloVideo] = useState("");
  const [orientacaoUrl, setOrientacaoUrl] = useState<"horizontal" | "vertical">("horizontal");

  // upload de arquivo
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [tipoArquivo, setTipoArquivo] = useState<"video" | "documento">("documento");
  const [orientacaoArq, setOrientacaoArq] = useState<"horizontal" | "vertical">("horizontal");
  const [enviando, setEnviando] = useState(false);

  // hint novo
  const [chaveNova, setChaveNova] = useState("");

  const carregar = useCallback(async () => {
    const [art, cats, mods, chaves, todosHints] = await Promise.all([
      api.GET("/api/v1/admin/class/articles/{artigo_id}", {
        params: { path: { artigo_id: params.id } },
      }),
      api.GET("/api/v1/admin/class/categories"),
      api.GET("/api/v1/admin/class/modules"),
      api.GET("/api/v1/admin/class/hint-keys"),
      api.GET("/api/v1/admin/class/hints"),
    ]);
    if (art.error || !art.data) {
      setErro("Artigo não encontrado (ou acesso negado).");
      return;
    }
    const a = art.data as Artigo;
    setArtigo(a);
    setTitulo(a.titulo);
    setResumo(a.resumo ?? "");
    // só na PRIMEIRA carga: recarregar (após upload de mídia etc.) não pode
    // sobrescrever o que está sendo digitado no editor não-controlado.
    // Conteúdo legado em markdown leve é convertido para o HTML do editor.
    setCorpo((atual) =>
      atual !== null
        ? atual
        : !a.corpo || corpoEhHtml(a.corpo)
          ? a.corpo
          : markdownLeveParaHtml(a.corpo),
    );
    setCategoriaId(a.categoria?.id ?? "");
    setModuloId(a.modulo?.id ?? "");
    setOrdem(a.ordem ?? 0);
    setCategorias((cats.data as Categoria[]) ?? []);
    setModulos((mods.data as Modulo[]) ?? []);
    setCatalogo((chaves.data as ChaveCatalogo[]) ?? []);
    setHints((todosHints.data as HintAdmin[]) ?? []);
  }, [params.id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const hintsDoArtigo = useMemo(
    () => hints.filter((h) => h.artigo_id === params.id),
    [hints, params.id],
  );
  // chave já ocupada por OUTRO artigo — o admin vê antes de realocar
  const ocupadaPor = useMemo(() => {
    const mapa = new Map<string, HintAdmin>();
    for (const h of hints) if (h.artigo_id !== params.id) mapa.set(h.chave, h);
    return mapa;
  }, [hints, params.id]);

  const catalogoPorTela = useMemo(() => {
    const grupos = new Map<string, ChaveCatalogo[]>();
    for (const c of catalogo) {
      const lista = grupos.get(c.tela) ?? [];
      lista.push(c);
      grupos.set(c.tela, lista);
    }
    return [...grupos.entries()];
  }, [catalogo]);

  async function salvar(publicado?: boolean) {
    setSalvando(true);
    setMsg(null);
    const { data, error } = await api.PATCH("/api/v1/admin/class/articles/{artigo_id}", {
      params: { path: { artigo_id: params.id } },
      body: {
        titulo,
        resumo: resumo || null,
        corpo: corpo ?? "",
        categoria_id: categoriaId || null,
        modulo_id: moduloId || null,
        ordem,
        ...(publicado === undefined ? {} : { publicado }),
      },
    });
    setSalvando(false);
    if (error || !data) {
      setMsg("Falha ao salvar.");
      return;
    }
    setArtigo(data as Artigo);
    setMsg(
      publicado === true
        ? "Publicado — o artigo (e os hints dele) já aparecem no painel."
        : publicado === false
          ? "Despublicado — voltou a rascunho."
          : "Salvo.",
    );
  }

  async function excluirArtigo() {
    if (!window.confirm("Excluir o artigo? Mídias e hints dele somem junto.")) return;
    await api.DELETE("/api/v1/admin/class/articles/{artigo_id}", {
      params: { path: { artigo_id: params.id } },
    });
    router.push("/admin/class");
  }

  async function adicionarVideoUrl(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    const { error } = await api.POST("/api/v1/admin/class/articles/{artigo_id}/media", {
      params: { path: { artigo_id: params.id } },
      body: {
        tipo: "video",
        url: urlVideo,
        titulo: tituloVideo || null,
        orientacao: orientacaoUrl,
        ordem: 0,
      },
    });
    if (error) {
      setMsg("Falha ao adicionar o vídeo.");
      return;
    }
    setUrlVideo("");
    setTituloVideo("");
    await carregar();
  }

  async function enviarArquivo(e: React.FormEvent) {
    e.preventDefault();
    if (!arquivo) return;
    setEnviando(true);
    setMsg(null);
    try {
      await enviarMidiaAjuda(params.id, arquivo, {
        tipo: tipoArquivo,
        orientacao: orientacaoArq,
      });
      setArquivo(null);
      await carregar();
    } catch (err) {
      setMsg((err as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  async function removerMidia(id: string) {
    await api.DELETE("/api/v1/admin/class/media/{midia_id}", {
      params: { path: { midia_id: id } },
    });
    await carregar();
  }

  async function plantarHint(e: React.FormEvent) {
    e.preventDefault();
    if (!chaveNova) return;
    setMsg(null);
    const { error } = await api.PUT("/api/v1/admin/class/hints", {
      body: { chave: chaveNova, artigo_id: params.id, ativo: true },
    });
    if (error) {
      setMsg("Falha ao plantar o hint.");
      return;
    }
    setChaveNova("");
    await carregar();
  }

  async function alternarHint(h: HintAdmin) {
    await api.PUT("/api/v1/admin/class/hints", {
      body: { chave: h.chave, artigo_id: params.id, ativo: !h.ativo },
    });
    await carregar();
  }

  async function removerHint(chave: string) {
    await api.DELETE("/api/v1/admin/class/hints/{chave}", {
      params: { path: { chave } },
    });
    await carregar();
  }

  function rotuloDaChave(chave: string): string {
    const c = catalogo.find((x) => x.chave === chave);
    return c ? `${c.rotulo} — ${c.tela}` : chave;
  }

  if (erro) {
    return (
      <div className="flex flex-col items-start gap-4">
        <Aviso tom="erro">{erro}</Aviso>
        <Link href="/admin/class" className="btn btn-ghost btn-sm">
          ← Class
        </Link>
      </div>
    );
  }
  if (!artigo) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href="/admin/class"
            className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 hover:text-ink"
          >
            ← Class
          </Link>
          <h1 className="page-title mt-1.5">{artigo.titulo}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-ink-2">
            <StatusBadge tone={artigo.publicado ? "success" : "neutral"}>
              {artigo.publicado ? "publicado" : "rascunho"}
            </StatusBadge>
            <span className="font-mono text-[11px] text-ink-3">/panel/class/{artigo.slug}</span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {artigo.publicado && (
            <Link
              href={`/panel/class/${artigo.slug}`}
              target="_blank"
              className="btn btn-ghost btn-sm"
            >
              Ver no painel ↗
            </Link>
          )}
          <button onClick={excluirArtigo} className="btn btn-ghost btn-sm tone-danger">
            Excluir
          </button>
        </div>
      </header>

      {msg && <Aviso tom={msg.startsWith("Falha") ? "erro" : "ok"}>{msg}</Aviso>}

      {/* ── Conteúdo ─────────────────────────────────────────────────── */}
      <section className="card flex flex-col gap-4 p-5">
        <h2 className="label-mono border-b border-hairline pb-2">Conteúdo</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Título</span>
            <input
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              required
              className="input"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Categoria</span>
            <select
              value={categoriaId}
              onChange={(e) => setCategoriaId(e.target.value)}
              className="input"
            >
              <option value="">Sem categoria</option>
              {categorias.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.nome}
                </option>
              ))}
            </select>
          </label>
        </div>

        {/* Vínculo com módulo: escolher um módulo transforma este conteúdo em
            AULA da trilha; a posição ordena a sequência. Sem módulo = artigo
            avulso do acervo. */}
        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Módulo (vira aula da trilha)</span>
            <select
              value={moduloId}
              onChange={(e) => setModuloId(e.target.value)}
              className="input"
            >
              <option value="">Nenhum — artigo avulso</option>
              {modulos.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.titulo}
                </option>
              ))}
            </select>
          </label>
          {moduloId && (
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Posição no módulo (aula nº)</span>
              <input
                type="number"
                min={0}
                value={ordem}
                onChange={(e) => setOrdem(Number(e.target.value))}
                className="input w-32"
              />
            </label>
          )}
        </div>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Resumo (aparece no popover do hint e na listagem)</span>
          <textarea
            value={resumo}
            onChange={(e) => setResumo(e.target.value)}
            rows={2}
            className="input min-h-16"
            placeholder="Uma ou duas frases diretas — é o que o gestor lê primeiro ao clicar no ⓘ."
          />
        </label>
        <div className="flex flex-col gap-1.5">
          <span className="field-label">
            Conteúdo — use &ldquo;▸ Vídeo&rdquo; para embedar YouTube, Vimeo,
            Bunny ou mp4 no meio do texto
          </span>
          {corpo === null ? (
            <div className="skeleton h-72 w-full rounded-lg" aria-hidden />
          ) : (
            <RichTextEditor valor={corpo} aoMudar={setCorpo} />
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => void salvar()} disabled={salvando} className="btn btn-primary">
            {salvando ? "Salvando…" : "Salvar"}
          </button>
          {artigo.publicado ? (
            <button onClick={() => void salvar(false)} disabled={salvando} className="btn btn-ghost">
              Despublicar
            </button>
          ) : (
            <button onClick={() => void salvar(true)} disabled={salvando} className="btn btn-accent">
              Salvar e publicar
            </button>
          )}
        </div>
      </section>

      {/* ── Mídias ───────────────────────────────────────────────────── */}
      <section className="card flex flex-col gap-4 p-5">
        <h2 className="label-mono border-b border-hairline pb-2">
          Vídeos e materiais
        </h2>

        {artigo.midias.length > 0 && (
          <ul className="flex flex-col divide-y divide-hairline">
            {artigo.midias.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <span className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
                  {m.tipo === "video" ? `▸ vídeo ${m.orientacao}` : "⇩ documento"}
                </span>
                <span className="min-w-40 flex-1 truncate text-sm text-ink">
                  {m.titulo || m.nome_arquivo || m.url || "—"}
                </span>
                <button
                  onClick={() => void removerMidia(m.id)}
                  className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 hover:text-ink"
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={adicionarVideoUrl} className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-64 flex-1 flex-col gap-1.5">
            <span className="field-label">Vídeo por URL (YouTube, Vimeo ou .mp4)</span>
            <input
              value={urlVideo}
              onChange={(e) => setUrlVideo(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=…"
              required
              className="input"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Título (opcional)</span>
            <input
              value={tituloVideo}
              onChange={(e) => setTituloVideo(e.target.value)}
              className="input w-44"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Orientação</span>
            <select
              value={orientacaoUrl}
              onChange={(e) => setOrientacaoUrl(e.target.value as "horizontal" | "vertical")}
              className="input w-36"
            >
              <option value="horizontal">Horizontal</option>
              <option value="vertical">Vertical</option>
            </select>
          </label>
          <button type="submit" className="btn btn-ghost">
            Adicionar vídeo
          </button>
        </form>

        <form
          onSubmit={enviarArquivo}
          className="flex flex-wrap items-end gap-3 border-t border-hairline pt-4"
        >
          <label className="flex min-w-64 flex-1 flex-col gap-1.5">
            <span className="field-label">Enviar arquivo (vídeo curto ou documento, máx. 50MB)</span>
            <input
              type="file"
              onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
              className="input"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Tipo</span>
            <select
              value={tipoArquivo}
              onChange={(e) => setTipoArquivo(e.target.value as "video" | "documento")}
              className="input w-36"
            >
              <option value="documento">Documento</option>
              <option value="video">Vídeo</option>
            </select>
          </label>
          {tipoArquivo === "video" && (
            <label className="flex flex-col gap-1.5">
              <span className="field-label">Orientação</span>
              <select
                value={orientacaoArq}
                onChange={(e) => setOrientacaoArq(e.target.value as "horizontal" | "vertical")}
                className="input w-36"
              >
                <option value="horizontal">Horizontal</option>
                <option value="vertical">Vertical</option>
              </select>
            </label>
          )}
          <button type="submit" disabled={!arquivo || enviando} className="btn btn-ghost">
            {enviando ? "Enviando…" : "Enviar arquivo"}
          </button>
        </form>
      </section>

      {/* ── Hints ────────────────────────────────────────────────────── */}
      <section className="card flex flex-col gap-4 p-5">
        <h2 className="label-mono border-b border-hairline pb-2">
          Hints — onde este artigo aparece como ⓘ
        </h2>
        <p className="-mt-2 text-xs leading-relaxed text-ink-3">
          Escolha o dado do painel que este artigo explica. O ícone{" "}
          <span className="font-mono">?</span> passa a aparecer ao lado dele —
          só enquanto o artigo estiver publicado.
        </p>

        {hintsDoArtigo.length > 0 && (
          <ul className="flex flex-col divide-y divide-hairline">
            {hintsDoArtigo.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <span className="min-w-40 flex-1 text-sm text-ink">
                  {rotuloDaChave(h.chave)}
                  <span className="ml-2 font-mono text-[11px] text-ink-3">{h.chave}</span>
                </span>
                <StatusBadge tone={h.ativo ? "success" : "neutral"}>
                  {h.ativo ? "ativo" : "pausado"}
                </StatusBadge>
                <button
                  onClick={() => void alternarHint(h)}
                  className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 hover:text-ink"
                >
                  {h.ativo ? "Pausar" : "Reativar"}
                </button>
                <button
                  onClick={() => void removerHint(h.chave)}
                  className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 hover:text-ink"
                >
                  Remover
                </button>
              </li>
            ))}
          </ul>
        )}

        <form onSubmit={plantarHint} className="flex flex-wrap items-end gap-3">
          <label className="flex min-w-72 flex-col gap-1.5">
            <span className="field-label">Plantar em</span>
            <select
              value={chaveNova}
              onChange={(e) => setChaveNova(e.target.value)}
              required
              className="input"
            >
              <option value="">Escolha o dado…</option>
              {catalogoPorTela.map(([tela, chaves]) => (
                <optgroup key={tela} label={tela}>
                  {chaves.map((c) => (
                    <option key={c.chave} value={c.chave}>
                      {c.rotulo}
                      {ocupadaPor.has(c.chave)
                        ? ` (hoje: ${ocupadaPor.get(c.chave)!.artigo_titulo})`
                        : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <button type="submit" className="btn btn-primary">
            Plantar hint
          </button>
        </form>
        {chaveNova && ocupadaPor.has(chaveNova) && (
          <p className="text-xs text-warn">
            Esta chave já aponta para “{ocupadaPor.get(chaveNova)!.artigo_titulo}” —
            plantar aqui transfere o hint para este artigo.
          </p>
        )}
      </section>
    </>
  );
}
