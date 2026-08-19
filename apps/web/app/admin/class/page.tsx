"use client";

/**
 * Admin do Class — módulos, artigos e categorias.
 *
 * Daqui a equipe cria o conteúdo que responde as dúvidas do gestor
 * ("o que é um empenho?"): MÓDULOS de aprendizagem (trilhas de aulas em
 * sequência), artigos de texto com vídeos e documentos anexos, agrupados por
 * categoria. O editor (conteúdo + mídias + hints + vínculo com módulo) fica
 * em /admin/class/<id>; aqui é a visão geral e a criação.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, mensagemDaFalha } from "@/lib/api/client";
import { StatusBadge } from "@/components/StatusBadge";
import { Skeleton } from "@/components/Skeleton";

interface Categoria {
  id: string;
  nome: string;
  slug: string;
  artigos: number;
}

interface Modulo {
  id: string;
  titulo: string;
  slug: string;
  descricao?: string | null;
  publicado: boolean;
  aulas: number;
}

interface ArtigoResumo {
  id: string;
  titulo: string;
  slug: string;
  publicado: boolean;
  categoria?: { id?: string; nome: string } | null;
  modulo?: { id: string; titulo: string } | null;
  ordem: number;
  videos: number;
  documentos: number;
  hints: number;
}

export default function AdminClassPage() {
  const router = useRouter();
  const [artigos, setArtigos] = useState<ArtigoResumo[] | null>(null);
  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [titulo, setTitulo] = useState("");
  const [categoriaId, setCategoriaId] = useState("");
  const [novoModulo, setNovoModulo] = useState("");
  const [descricaoModulo, setDescricaoModulo] = useState("");
  const [novaCategoria, setNovaCategoria] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const [arts, mods, cats] = await Promise.all([
      api.GET("/api/v1/admin/class/articles"),
      api.GET("/api/v1/admin/class/modules"),
      api.GET("/api/v1/admin/class/categories"),
    ]);
    if (arts.error) {
      setMsg("Acesso negado — é necessário ser administrador.");
      setArtigos([]);
      return;
    }
    setArtigos((arts.data as ArtigoResumo[]) ?? []);
    setModulos((mods.data as Modulo[]) ?? []);
    setCategorias((cats.data as Categoria[]) ?? []);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function criarArtigo(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      const { data, error } = await api.POST("/api/v1/admin/class/articles", {
        body: {
          titulo,
          categoria_id: categoriaId || null,
          modulo_id: null,
          corpo: "",
          publicado: false,
          ordem: 0,
        },
      });
      if (error || !data) {
        setMsg(mensagemDaFalha(error, "Falha ao criar o artigo"));
        return;
      }
      // direto para o editor: o fluxo natural é escrever em seguida
      router.push(`/admin/class/${(data as { id: string }).id}`);
    } catch (err) {
      setMsg(mensagemDaFalha(err, "Falha ao criar o artigo"));
    }
  }

  async function criarModulo(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      const { error } = await api.POST("/api/v1/admin/class/modules", {
        body: {
          titulo: novoModulo,
          descricao: descricaoModulo || null,
          publicado: false,
          ordem: 0,
        },
      });
      if (error) {
        setMsg(mensagemDaFalha(error, "Falha ao criar o módulo"));
        return;
      }
      setNovoModulo("");
      setDescricaoModulo("");
      await carregar();
    } catch (err) {
      setMsg(mensagemDaFalha(err, "Falha ao criar o módulo"));
    }
  }

  async function alternarModulo(m: Modulo) {
    setMsg(null);
    try {
      const { error } = await api.PATCH("/api/v1/admin/class/modules/{modulo_id}", {
        params: { path: { modulo_id: m.id } },
        body: { publicado: !m.publicado },
      });
      if (error) {
        setMsg(mensagemDaFalha(error, "Falha ao publicar o módulo"));
        return;
      }
      await carregar();
    } catch (err) {
      setMsg(mensagemDaFalha(err, "Falha ao publicar o módulo"));
    }
  }

  async function excluirModulo(m: Modulo) {
    if (
      !window.confirm(
        `Excluir o módulo "${m.titulo}"? As aulas NÃO somem — voltam a ser artigos avulsos.`,
      )
    )
      return;
    await api.DELETE("/api/v1/admin/class/modules/{modulo_id}", {
      params: { path: { modulo_id: m.id } },
    });
    await carregar();
  }

  async function criarCategoria(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      const { error } = await api.POST("/api/v1/admin/class/categories", {
        body: { nome: novaCategoria, ordem: 0 },
      });
      if (error) {
        setMsg(mensagemDaFalha(error, "Falha ao criar a categoria"));
        return;
      }
      setNovaCategoria("");
      await carregar();
    } catch (err) {
      setMsg(mensagemDaFalha(err, "Falha ao criar a categoria"));
    }
  }

  async function excluirCategoria(id: string) {
    if (!window.confirm("Excluir a categoria? Os artigos dela ficam sem categoria.")) return;
    await api.DELETE("/api/v1/admin/class/categories/{categoria_id}", {
      params: { path: { categoria_id: id } },
    });
    await carregar();
  }

  // aulas de módulo listadas junto (com o badge do módulo); avulsos primeiro
  const avulsos = (artigos ?? []).filter((a) => !a.modulo);
  const aulas = (artigos ?? []).filter((a) => a.modulo);

  const linhaArtigo = (a: ArtigoResumo) => (
    <li key={a.id} className="flex flex-wrap items-center gap-3 py-3.5">
      <div className="min-w-48 flex-1">
        <Link
          href={`/admin/class/${a.id}`}
          className="text-sm tracking-tight text-ink hover:underline"
        >
          {a.titulo}
        </Link>
        <p className="mt-0.5 flex flex-wrap gap-x-3 font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
          {a.modulo && (
            <span>
              aula {a.ordem} · {a.modulo.titulo}
            </span>
          )}
          {a.categoria && <span>{a.categoria.nome}</span>}
          <span>/{a.slug}</span>
          {a.videos > 0 && <span>▸ {a.videos} vídeo(s)</span>}
          {a.documentos > 0 && <span>⇩ {a.documentos} anexo(s)</span>}
          {a.hints > 0 && <span>? {a.hints} hint(s)</span>}
        </p>
      </div>
      <StatusBadge tone={a.publicado ? "success" : "neutral"}>
        {a.publicado ? "publicado" : "rascunho"}
      </StatusBadge>
      <Link href={`/admin/class/${a.id}`} className="btn btn-ghost btn-sm">
        Editar
      </Link>
    </li>
  );

  return (
    <>
      <header>
        <h1 className="page-title">Class</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Módulos de aulas, artigos, vídeos e materiais que explicam os termos e
          dados do painel (ex.: &ldquo;o que é um empenho?&rdquo;). Cada artigo
          ou aula pode virar um hint <span className="font-mono text-xs">?</span>{" "}
          ao lado do dado que ele explica — isso se configura dentro do editor.
        </p>
      </header>

      {msg && <p className="text-sm text-warn">{msg}</p>}

      {/* ── Módulos ─────────────────────────────────────────────────── */}
      <section className="card p-5">
        <h2 className="label-mono mb-3 border-b border-hairline pb-2">
          Módulos (trilhas de aulas)
        </h2>
        <form onSubmit={criarModulo} className="mb-4 flex flex-wrap items-end gap-3">
          <label className="flex min-w-56 flex-col gap-1.5">
            <span className="field-label">Novo módulo</span>
            <input
              value={novoModulo}
              onChange={(e) => setNovoModulo(e.target.value)}
              placeholder="Ex.: Captação 101 — do edital à proposta"
              required
              className="input"
            />
          </label>
          <label className="flex min-w-64 flex-1 flex-col gap-1.5">
            <span className="field-label">Descrição (opcional)</span>
            <input
              value={descricaoModulo}
              onChange={(e) => setDescricaoModulo(e.target.value)}
              className="input"
            />
          </label>
          <button type="submit" className="btn btn-primary">
            Criar módulo
          </button>
        </form>
        {modulos.length === 0 ? (
          <p className="text-sm text-ink-3">
            Nenhum módulo ainda. Crie um e depois vincule as aulas pelo editor de
            cada artigo (campo &ldquo;Módulo&rdquo;).
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-hairline">
            {modulos.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-48 flex-1">
                  <span className="text-sm tracking-tight text-ink">{m.titulo}</span>
                  <p className="mt-0.5 flex flex-wrap gap-x-3 font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3">
                    <span>
                      {m.aulas} aula{m.aulas === 1 ? "" : "s"}
                    </span>
                    <span>/{m.slug}</span>
                  </p>
                </div>
                <StatusBadge tone={m.publicado ? "success" : "neutral"}>
                  {m.publicado ? "publicado" : "rascunho"}
                </StatusBadge>
                <button
                  onClick={() => void alternarModulo(m)}
                  className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-2 hover:text-ink"
                >
                  {m.publicado ? "Despublicar" : "Publicar"}
                </button>
                <button
                  onClick={() => void excluirModulo(m)}
                  className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 hover:text-ink"
                >
                  Excluir
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── Artigos ─────────────────────────────────────────────────── */}
      <form onSubmit={criarArtigo} className="card flex flex-wrap items-end gap-3 p-5">
        <label className="flex min-w-64 flex-1 flex-col gap-1.5">
          <span className="field-label">Novo artigo (ou aula — vincule ao módulo no editor)</span>
          <input
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Ex.: O que é um empenho?"
            required
            className="input"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Categoria</span>
          <select
            value={categoriaId}
            onChange={(e) => setCategoriaId(e.target.value)}
            className="input w-48"
          >
            <option value="">Sem categoria</option>
            {categorias.map((c) => (
              <option key={c.id} value={c.id}>
                {c.nome}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn btn-primary">
          Criar e escrever
        </button>
      </form>

      {artigos === null ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : (
        <>
          <ul className="card flex flex-col divide-y divide-hairline px-5">
            {avulsos.map(linhaArtigo)}
            {avulsos.length === 0 && (
              <li className="py-3.5 text-sm text-ink-3">
                Nenhum artigo avulso ainda — crie o primeiro acima.
              </li>
            )}
          </ul>
          {aulas.length > 0 && (
            <section>
              <h2 className="label-mono mb-2">Aulas (dentro de módulos)</h2>
              <ul className="card flex flex-col divide-y divide-hairline px-5">
                {aulas.map(linhaArtigo)}
              </ul>
            </section>
          )}
        </>
      )}

      <section className="card p-5">
        <h2 className="label-mono mb-3 border-b border-hairline pb-2">Categorias</h2>
        <form onSubmit={criarCategoria} className="mb-3 flex flex-wrap items-end gap-3">
          <label className="flex min-w-56 flex-col gap-1.5">
            <span className="field-label">Nova categoria</span>
            <input
              value={novaCategoria}
              onChange={(e) => setNovaCategoria(e.target.value)}
              placeholder="Ex.: Orçamento e finanças"
              required
              className="input"
            />
          </label>
          <button type="submit" className="btn btn-ghost">
            Adicionar
          </button>
        </form>
        <ul className="flex flex-wrap gap-2">
          {categorias.map((c) => (
            <li
              key={c.id}
              className="inline-flex items-center gap-2 rounded-full border border-hairline px-3 py-1 text-sm text-ink-2"
            >
              {c.nome}
              <span className="font-mono text-[11px] text-ink-3">{c.artigos}</span>
              <button
                onClick={() => void excluirCategoria(c.id)}
                title="Excluir categoria"
                className="text-ink-3 transition-colors hover:text-ink"
              >
                ×
              </button>
            </li>
          ))}
          {categorias.length === 0 && (
            <li className="text-sm text-ink-3">Nenhuma categoria ainda.</li>
          )}
        </ul>
      </section>
    </>
  );
}
