"use client";

/**
 * Editor da marca (white label, §69) — o MESMO para o admin da plataforma e
 * para o dono da marca; `admin` só acrescenta o bloco de operação (slug,
 * ativação, dono, plano, provisionamento, exclusão).
 *
 * O tema é editado como RASCUNHO local e pré-visualizado ao vivo: a API monta
 * o CSS escopado em `.marca-preview` (POST /branding/preview) — a mesma função
 * que veste o site, então o que se vê aqui é o que vai ao ar. Nada é aplicado
 * ao próprio painel antes de salvar.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { components } from "@hub/api-client";
import { StatusBadge, type BadgeTone } from "@/components/StatusBadge";
import { api, enviarArquivoMarca, mensagemDaFalha } from "@/lib/api/client";

type Marca = components["schemas"]["MarcaRead"];
type Tema = components["schemas"]["TemaMarca"];
type Opcoes = components["schemas"]["OpcoesMarca"];
type Membro = components["schemas"]["MembroMarca"];
type Convite = components["schemas"]["ConviteRead"];

const PADRAO_CORES = { acento: "#43cf9b", escuro: "#031918", acao: "#1c6555" };

const STATUS_DOMINIO: Record<string, { rotulo: string; tom: BadgeTone }> = {
  pendente: { rotulo: "Aguardando DNS", tom: "neutral" },
  verificado: { rotulo: "DNS ok · aguardando ativação", tom: "info" },
  ativo: { rotulo: "Ativo", tom: "success" },
  erro: { rotulo: "Não verificado", tom: "danger" },
};

const ACEITA: Record<string, string> = {
  logo: "image/png,image/jpeg,image/webp,image/svg+xml",
  logo_escuro: "image/png,image/jpeg,image/webp,image/svg+xml",
  icone: "image/png,image/svg+xml",
  login_imagem: "image/png,image/jpeg,image/webp",
  fonte_corpo: ".woff2,font/woff2",
  fonte_titulo: ".woff2,font/woff2",
};

function Secao({
  titulo,
  descricao,
  children,
}: {
  titulo: string;
  descricao?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card flex flex-col gap-4 p-5 sm:p-6">
      <header className="flex flex-col gap-1">
        <h2 className="label-mono">{titulo}</h2>
        {descricao && <p className="text-sm text-ink-2">{descricao}</p>}
      </header>
      {children}
    </section>
  );
}

function Campo({
  rotulo,
  children,
  ajuda,
}: {
  rotulo: string;
  children: React.ReactNode;
  ajuda?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="field-label">{rotulo}</span>
      {children}
      {ajuda && <span className="text-xs text-ink-3">{ajuda}</span>}
    </label>
  );
}

function Segmentado<T extends string>({
  valor,
  opcoes,
  aoMudar,
  rotulo,
}: {
  valor: T;
  opcoes: { chave: string; rotulo: string }[];
  aoMudar: (v: T) => void;
  rotulo: string;
}) {
  return (
    <div className="segmented flex-wrap" role="radiogroup" aria-label={rotulo}>
      {opcoes.map((o) => (
        <button
          key={o.chave}
          type="button"
          role="radio"
          aria-checked={valor === o.chave}
          onClick={() => aoMudar(o.chave as T)}
          className={`segmented-item ${valor === o.chave ? "segmented-item-active" : ""}`}
        >
          {o.rotulo}
        </button>
      ))}
    </div>
  );
}

function CampoCor({
  rotulo,
  valor,
  padrao,
  ajuda,
  aoMudar,
}: {
  rotulo: string;
  valor: string | null | undefined;
  padrao: string;
  ajuda: string;
  aoMudar: (v: string | null) => void;
}) {
  const [texto, setTexto] = useState(valor ?? "");
  useEffect(() => setTexto(valor ?? ""), [valor]);
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="field-label">{rotulo}</span>
        {valor && (
          <button type="button" className="link-soft text-xs" onClick={() => aoMudar(null)}>
            usar padrão
          </button>
        )}
      </div>
      <div className="flex min-w-0 items-center gap-2">
        <input
          type="color"
          aria-label={`${rotulo} — seletor`}
          value={valor ?? padrao}
          onChange={(e) => aoMudar(e.target.value)}
          className="h-10 w-11 shrink-0 cursor-pointer rounded-md border border-hairline bg-transparent p-1"
        />
        <input
          className="input min-w-0 flex-1 font-mono"
          aria-label={`${rotulo} — hexadecimal`}
          value={texto}
          placeholder={padrao}
          maxLength={7}
          onChange={(e) => {
            setTexto(e.target.value);
            const v = e.target.value.trim();
            if (/^#?[0-9a-fA-F]{6}$/.test(v)) aoMudar(v.startsWith("#") ? v : `#${v}`);
            if (!v) aoMudar(null);
          }}
        />
      </div>
      <span className="text-xs text-ink-3">{ajuda}</span>
    </div>
  );
}

/** Mini-tela que veste o tema do rascunho (classes reais do design system). */
function Previa({ marca, tema, css, fontes }: { marca: Marca; tema: Tema; css: string; fontes: string[] }) {
  const logo = marca.assets?.find((a) => a.tipo === "logo")?.url;
  const nome = tema.nome_exibicao || marca.nome;
  return (
    <div className="marca-preview flex flex-col overflow-hidden rounded-[var(--radius-card)] border border-hairline bg-surface text-ink">
      {fontes.map((href) => (
        <link key={href} rel="stylesheet" href={href} />
      ))}
      {css && <style dangerouslySetInnerHTML={{ __html: css.replace(/<\/(style)/gi, "<\\/$1") }} />}
      <div className="flex min-h-[320px]">
        <div className="hidden w-40 shrink-0 flex-col gap-1 border-r border-hairline p-3 sm:flex" style={{ background: "var(--nav-bg)" }}>
          <span className="sidebar-brand mb-2 text-sm" style={{ color: "var(--nav-brand-ink)" }}>
            {logo ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={logo} alt="" style={{ height: 22, width: "auto" }} />
            ) : (
              <span className="brand-dot" aria-hidden />
            )}
            {(!logo || tema.nome_com_logo) && nome}
          </span>
          <span className="nav-item nav-item-active text-[13px]">Meu painel</span>
          <span className="nav-item text-[13px]">Propostas</span>
          <span className="nav-item text-[13px]">Alertas</span>
        </div>
        <div className="flex flex-1 flex-col gap-3 p-4">
          <h3 className="page-title">Captação</h3>
          <div className="card flex flex-col gap-3 p-4">
            <p className="stat-label">Empenhado</p>
            <p className="num text-2xl">R$ 1,2 mi</p>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: "62%" }} />
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="chip chip-active">Disponíveis</span>
              <span className="chip">Cadastradas</span>
            </div>
            <input className="input" placeholder="Buscar proposta…" readOnly />
            <div className="flex flex-wrap gap-2">
              <span className="btn btn-primary btn-sm">Salvar</span>
              <span className="btn btn-ghost btn-sm">Cancelar</span>
              <a className="link-soft text-sm" href="#previa" onClick={(e) => e.preventDefault()}>
                Ver detalhes
              </a>
            </div>
          </div>
          <p className="text-xs text-ink-3">
            {tema.nome_assistente || "Copiloto"} · {tema.rodape || `© ${nome}`}
          </p>
        </div>
      </div>
    </div>
  );
}

export function EditorMarca({
  marcaId,
  admin = false,
  aoExcluir,
}: {
  marcaId: string;
  admin?: boolean;
  aoExcluir?: () => void;
}) {
  const [marca, setMarca] = useState<Marca | null>(null);
  const [opcoes, setOpcoes] = useState<Opcoes | null>(null);
  const [tema, setTema] = useState<Tema | null>(null);
  const [nome, setNome] = useState("");
  const [preview, setPreview] = useState<{ css: string; fontes: string[]; avisos: string[] }>({
    css: "",
    fontes: [],
    avisos: [],
  });
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tom: "ok" | "erro"; texto: string } | null>(null);
  const [dominio, setDominio] = useState("");
  const [ocupado, setOcupado] = useState<string | null>(null);
  const [membros, setMembros] = useState<Membro[]>([]);
  const [convites, setConvites] = useState<Convite[]>([]);
  const [emailConvite, setEmailConvite] = useState("");
  const [planos, setPlanos] = useState<{ id: string; nome: string }[]>([]);
  const [admSlug, setAdmSlug] = useState("");
  const [admDono, setAdmDono] = useState("");

  const aplicar = useCallback((m: Marca) => {
    setMarca(m);
    setTema(m.tema);
    setNome(m.nome);
    setDominio(m.dominio ?? "");
    setAdmSlug(m.slug);
    setAdmDono(m.dono_email ?? "");
  }, []);

  const carregarEquipe = useCallback(async () => {
    const [m, c] = await Promise.all([
      api.GET("/api/v1/brands/{marca_id}/members", { params: { path: { marca_id: marcaId } } }),
      api.GET("/api/v1/brands/{marca_id}/invites", { params: { path: { marca_id: marcaId } } }),
    ]);
    if (m.data) setMembros(m.data);
    if (c.data) setConvites(c.data);
  }, [marcaId]);

  useEffect(() => {
    void (async () => {
      const [m, o] = await Promise.all([
        api.GET("/api/v1/brands/{marca_id}", { params: { path: { marca_id: marcaId } } }),
        api.GET("/api/v1/brands/options"),
      ]);
      if (m.data) aplicar(m.data);
      else setMsg({ tom: "erro", texto: mensagemDaFalha(m.error, "Marca não encontrada.") });
      if (o.data) setOpcoes(o.data);
      await carregarEquipe();
      if (admin) {
        const p = await api.GET("/api/v1/plans", {
          params: { query: { incluir_inativos: true } } as never,
        });
        if (Array.isArray(p.data)) setPlanos(p.data as { id: string; nome: string }[]);
      }
    })();
  }, [marcaId, admin, aplicar, carregarEquipe]);

  // pré-visualização ao vivo (debounce: uma chamada por pausa na digitação)
  const temaJson = useMemo(() => JSON.stringify(tema ?? {}), [tema]);
  const ultima = useRef(0);
  useEffect(() => {
    if (!tema) return;
    const id = ++ultima.current;
    const t = window.setTimeout(async () => {
      const { data } = await api.POST("/api/v1/branding/preview", {
        body: { tema, marca_id: marcaId },
      });
      if (data && id === ultima.current) {
        setPreview({ css: data.css, fontes: data.fontes_urls ?? [], avisos: data.avisos ?? [] });
      }
    }, 350);
    return () => window.clearTimeout(t);
    // temaJson captura o conteúdo do rascunho (o objeto muda de identidade a cada tecla)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [temaJson, marcaId]);

  const mudar = useCallback(<K extends keyof Tema>(chave: K, valor: Tema[K]) => {
    setTema((t) => (t ? { ...t, [chave]: valor } : t));
  }, []);
  const mudarCor = useCallback((chave: "acento" | "escuro" | "acao", valor: string | null) => {
    setTema((t) => (t ? { ...t, cores: { ...(t.cores ?? {}), [chave]: valor } } : t));
  }, []);

  const sujo = useMemo(
    () => marca !== null && (JSON.stringify(marca.tema) !== temaJson || marca.nome !== nome),
    [marca, temaJson, nome],
  );

  async function salvar() {
    if (!tema) return;
    setSalvando(true);
    setMsg(null);
    try {
      const { data, error } = await api.PATCH("/api/v1/brands/{marca_id}", {
        params: { path: { marca_id: marcaId } },
        body: { nome, tema },
      });
      if (error || !data) {
        setMsg({ tom: "erro", texto: mensagemDaFalha(error, "Não foi possível salvar.") });
        return;
      }
      aplicar(data);
      setMsg({ tom: "ok", texto: "Marca salva. O site da marca reflete em até um minuto." });
    } catch (e) {
      setMsg({ tom: "erro", texto: mensagemDaFalha(e, "Não foi possível salvar.") });
    } finally {
      setSalvando(false);
    }
  }

  async function acao(rotulo: string, fn: () => Promise<{ data?: Marca; error?: unknown }>) {
    setOcupado(rotulo);
    setMsg(null);
    try {
      const { data, error } = await fn();
      if (error || !data) {
        setMsg({ tom: "erro", texto: mensagemDaFalha(error, "Não foi possível concluir.") });
        return;
      }
      setMarca(data);
      setDominio(data.dominio ?? "");
      setAdmSlug(data.slug);
      setAdmDono(data.dono_email ?? "");
    } catch (e) {
      setMsg({ tom: "erro", texto: mensagemDaFalha(e, "Não foi possível concluir.") });
    } finally {
      setOcupado(null);
    }
  }

  async function recarregar() {
    const { data } = await api.GET("/api/v1/brands/{marca_id}", {
      params: { path: { marca_id: marcaId } },
    });
    if (data) setMarca(data);
  }

  async function enviarArquivo(tipo: string, arquivo: File | undefined) {
    if (!arquivo) return;
    setOcupado(`arquivo:${tipo}`);
    setMsg(null);
    try {
      await enviarArquivoMarca(marcaId, tipo, arquivo);
      await recarregar();
    } catch (e) {
      setMsg({ tom: "erro", texto: mensagemDaFalha(e, "Arquivo recusado") });
    } finally {
      setOcupado(null);
    }
  }

  async function removerArquivo(tipo: string) {
    setOcupado(`arquivo:${tipo}`);
    try {
      await api.DELETE("/api/v1/brands/{marca_id}/assets/{tipo}", {
        params: { path: { marca_id: marcaId, tipo } },
      });
      await recarregar();
    } finally {
      setOcupado(null);
    }
  }

  async function convidar(e: React.FormEvent) {
    e.preventDefault();
    setOcupado("convite");
    setMsg(null);
    try {
      const { error } = await api.POST("/api/v1/brands/{marca_id}/invites", {
        params: { path: { marca_id: marcaId } },
        body: { email: emailConvite },
      });
      if (error) {
        setMsg({ tom: "erro", texto: mensagemDaFalha(error, "Convite não enviado.") });
        return;
      }
      setEmailConvite("");
      await carregarEquipe();
    } finally {
      setOcupado(null);
    }
  }

  async function desvincular(m: Membro) {
    if (!window.confirm(`Tirar ${m.email} da marca? A conta continua existindo, sem a marca.`)) return;
    await api.DELETE("/api/v1/brands/{marca_id}/members/{usuario_id}", {
      params: { path: { marca_id: marcaId, usuario_id: m.id } },
    });
    await carregarEquipe();
  }

  async function excluir() {
    if (!marca) return;
    if (
      !window.confirm(
        `Excluir a marca "${marca.nome}"? As ${marca.membros} conta(s) vinculadas continuam ` +
          "existindo e voltam a usar o Hub Capture.",
      )
    )
      return;
    await api.DELETE("/api/v1/admin/brands/{marca_id}", {
      params: { path: { marca_id: marcaId } },
    });
    aoExcluir?.();
  }

  if (!marca || !tema || !opcoes) {
    return (
      <p className="text-sm text-ink-3">{msg?.texto ?? "Carregando marca…"}</p>
    );
  }

  const cores = tema.cores ?? {};
  const assets = new Map((marca.assets ?? []).map((a) => [a.tipo, a]));
  const st = marca.dominio_status ? STATUS_DOMINIO[marca.dominio_status] : null;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-xl">{marca.nome}</h1>
          <p className="text-sm text-ink-2">
            <a href={marca.url} target="_blank" rel="noreferrer" className="link-soft">
              {marca.url.replace("https://", "")} ↗
            </a>
            {!marca.ativo && <span className="ml-2 text-danger">· desativada</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {sujo && <span className="text-xs text-ink-3">Alterações não salvas</span>}
          <button type="button" className="btn btn-primary" disabled={salvando || !sujo} onClick={() => void salvar()}>
            {salvando ? "Salvando…" : "Salvar alterações"}
          </button>
        </div>
      </header>
      {msg && (
        <p className={msg.tom === "ok" ? "text-sm text-ok" : "text-sm text-danger"} role="status">
          {msg.texto}
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <div className="flex min-w-0 flex-col gap-6">
          <Secao titulo="Identidade" descricao="Como a plataforma se apresenta para quem entra pela marca.">
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo rotulo="Nome da marca">
                <input className="input" value={nome} maxLength={120} onChange={(e) => setNome(e.target.value)} />
              </Campo>
              <Campo rotulo="Nome exibido no site (opcional)" ajuda="Vazio = o nome da marca.">
                <input
                  className="input"
                  maxLength={60}
                  value={tema.nome_exibicao ?? ""}
                  onChange={(e) => mudar("nome_exibicao", e.target.value || null)}
                />
              </Campo>
              <Campo rotulo="Nome do assistente" ajuda="Substitui “Copiloto” no chat e na ilha.">
                <input
                  className="input"
                  maxLength={40}
                  placeholder="Copiloto"
                  value={tema.nome_assistente ?? ""}
                  onChange={(e) => mudar("nome_assistente", e.target.value || null)}
                />
              </Campo>
              <label className="flex items-center gap-2 self-end pb-2 text-sm text-ink-2">
                <input
                  type="checkbox"
                  checked={Boolean(tema.nome_com_logo)}
                  onChange={(e) => mudar("nome_com_logo", e.target.checked)}
                />
                Mostrar o nome ao lado do logo
              </label>
            </div>
          </Secao>

          <Secao
            titulo="Cores"
            descricao="Três cores bastam: o resto da paleta (tons claros, tema escuro, contraste do texto) é derivado delas."
          >
            <div className="grid gap-4 sm:grid-cols-3">
              <CampoCor
                rotulo="Acento"
                valor={cores.acento}
                padrao={PADRAO_CORES.acento}
                ajuda="Destaques: item ativo, foco, progresso."
                aoMudar={(v) => mudarCor("acento", v)}
              />
              <CampoCor
                rotulo="Tom escuro"
                valor={cores.escuro}
                padrao={PADRAO_CORES.escuro}
                ajuda="Trilho e fundo no tema escuro, e-mail e PDF."
                aoMudar={(v) => mudarCor("escuro", v)}
              />
              <CampoCor
                rotulo="Ação"
                valor={cores.acao}
                padrao={PADRAO_CORES.acao}
                ajuda="Botões e links no tema claro."
                aoMudar={(v) => mudarCor("acao", v)}
              />
            </div>
            {preview.avisos.length > 0 && (
              <ul className="flex flex-col gap-1 rounded-md bg-warn-bg p-3 text-sm text-warn">
                {preview.avisos.map((a) => (
                  <li key={a}>⚠ {a}</li>
                ))}
              </ul>
            )}
          </Secao>

          <Secao titulo="Forma, tipografia e ícones">
            <Campo rotulo="Cantos">
              <Segmentado rotulo="Cantos" valor={tema.forma ?? "padrao"} opcoes={opcoes.formas} aoMudar={(v) => mudar("forma", v as Tema["forma"])} />
            </Campo>
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo
                rotulo="Fonte do texto"
                ajuda={tema.fonte_corpo === "arquivo" ? "Envie o .woff2 em Arquivos." : undefined}
              >
                <select className="input" value={tema.fonte_corpo ?? "inter"} onChange={(e) => mudar("fonte_corpo", e.target.value)}>
                  {opcoes.fontes.map((f) => (
                    <option key={f.chave} value={f.chave}>
                      {f.rotulo}
                    </option>
                  ))}
                </select>
              </Campo>
              <Campo
                rotulo="Fonte dos títulos"
                ajuda={tema.fonte_titulo === "arquivo" ? "Envie o .woff2 em Arquivos." : undefined}
              >
                <select className="input" value={tema.fonte_titulo ?? "archivo"} onChange={(e) => mudar("fonte_titulo", e.target.value)}>
                  {opcoes.fontes.map((f) => (
                    <option key={f.chave} value={f.chave}>
                      {f.rotulo}
                    </option>
                  ))}
                </select>
              </Campo>
            </div>
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={tema.titulos_caixa_alta ?? true}
                onChange={(e) => mudar("titulos_caixa_alta", e.target.checked)}
              />
              Títulos em CAIXA ALTA
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo rotulo="Traço dos ícones">
                <Segmentado rotulo="Traço dos ícones" valor={tema.icones ?? "regular"} opcoes={opcoes.icones} aoMudar={(v) => mudar("icones", v as Tema["icones"])} />
              </Campo>
              <Campo rotulo="Pontas dos ícones">
                <Segmentado
                  rotulo="Pontas dos ícones"
                  valor={tema.icones_cantos ?? "arredondado"}
                  opcoes={[
                    { chave: "arredondado", rotulo: "Arredondadas" },
                    { chave: "reto", rotulo: "Retas" },
                  ]}
                  aoMudar={(v) => mudar("icones_cantos", v as Tema["icones_cantos"])}
                />
              </Campo>
            </div>
            <p className="text-xs text-ink-3">
              Fontes do catálogo (exceto Inter e Archivo) são carregadas do Google Fonts no navegador de quem acessa.
            </p>
          </Secao>

          <Secao titulo="Tela de login" descricao="A vitrine da marca: é a primeira tela de quem acessa o endereço dela.">
            <div className="grid gap-3 sm:grid-cols-2">
              <Campo rotulo="Título">
                <input className="input" maxLength={80} placeholder="Bem-vindo de volta" value={tema.login_titulo ?? ""} onChange={(e) => mudar("login_titulo", e.target.value || null)} />
              </Campo>
              <Campo rotulo="Frase sobre a imagem">
                <input className="input" maxLength={120} placeholder="Painel do território" value={tema.login_slogan ?? ""} onChange={(e) => mudar("login_slogan", e.target.value || null)} />
              </Campo>
              <Campo rotulo="Subtítulo">
                <input className="input" maxLength={200} placeholder="Entre para acompanhar o seu território." value={tema.login_subtitulo ?? ""} onChange={(e) => mudar("login_subtitulo", e.target.value || null)} />
              </Campo>
              <Campo rotulo="Rodapé">
                <input className="input" maxLength={120} placeholder={`© ${new Date().getFullYear()} ${marca.nome}`} value={tema.rodape ?? ""} onChange={(e) => mudar("rodape", e.target.value || null)} />
              </Campo>
            </div>
          </Secao>

          <Secao titulo="Arquivos" descricao="Logo e ícone em PNG/SVG (até 1 MB), imagem do login até 4 MB, fontes em .woff2. Valem na hora — não precisam de “Salvar”.">
            <ul className="flex flex-col divide-y divide-hairline">
              {opcoes.tipos_asset.map((t) => {
                const a = assets.get(t.chave);
                const imagem = a && a.content_type.startsWith("image/");
                return (
                  <li key={t.chave} className="flex flex-wrap items-center gap-3 py-3">
                    <div
                      className="flex h-12 w-20 shrink-0 items-center justify-center overflow-hidden rounded-md border border-hairline"
                      style={{ background: t.chave === "logo_escuro" ? "var(--color-brand-dark)" : "var(--surface-2)" }}
                    >
                      {imagem ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={a.url} alt="" className="max-h-10 max-w-[72px] object-contain" />
                      ) : (
                        <span className="text-[11px] text-ink-3">{a ? "fonte" : "—"}</span>
                      )}
                    </div>
                    <div className="min-w-0 flex-[1_1_12rem]">
                      <p className="text-sm">{t.rotulo}</p>
                      <p className="truncate text-xs text-ink-3">
                        {a ? `${a.nome_arquivo ?? a.tipo} · ${Math.ceil(a.tamanho / 1024)} KB` : "não enviado"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <label className="btn btn-ghost btn-sm cursor-pointer">
                        {ocupado === `arquivo:${t.chave}` ? "Enviando…" : a ? "Trocar" : "Enviar"}
                        <input
                          type="file"
                          className="sr-only"
                          accept={ACEITA[t.chave]}
                          disabled={ocupado !== null}
                          onChange={(e) => {
                            void enviarArquivo(t.chave, e.target.files?.[0]);
                            e.target.value = "";
                          }}
                        />
                      </label>
                      {a && (
                        <button type="button" className="btn btn-ghost btn-sm" disabled={ocupado !== null} onClick={() => void removerArquivo(t.chave)}>
                          Remover
                        </button>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </Secao>

          <Secao titulo="Endereço" descricao="O subdomínio funciona desde a criação. O domínio próprio é opcional.">
            <div className="flex flex-col gap-1">
              <span className="field-label">Endereço padrão</span>
              <a href={`https://${marca.host_padrao}`} target="_blank" rel="noreferrer" className="link-soft font-mono text-sm">
                {marca.host_padrao} ↗
              </a>
            </div>
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void acao("dominio", () =>
                  api.PUT("/api/v1/brands/{marca_id}/domain", {
                    params: { path: { marca_id: marcaId } },
                    body: { dominio: dominio.trim() || null },
                  }),
                );
              }}
            >
              <div className="min-w-0 flex-[1_1_16rem]">
                <Campo rotulo="Domínio próprio">
                  <input className="input font-mono" placeholder="painel.suaprefeitura.gov.br" value={dominio} onChange={(e) => setDominio(e.target.value)} />
                </Campo>
              </div>
              <button type="submit" className="btn btn-ghost" disabled={ocupado !== null || dominio.trim() === (marca.dominio ?? "")}>
                {dominio.trim() ? "Salvar domínio" : "Remover domínio"}
              </button>
            </form>
            {marca.dominio && (
              <div className="flex flex-col gap-3 rounded-md border border-hairline p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm">{marca.dominio}</span>
                  {st && <StatusBadge tone={st.tom}>{st.rotulo}</StatusBadge>}
                </div>
                <ol className="list-decimal space-y-1 pl-5 text-sm text-ink-2">
                  <li>
                    No provedor do domínio, crie um registro <b>CNAME</b> de{" "}
                    <code className="font-mono">{marca.dominio}</code> apontando para{" "}
                    <code className="font-mono">{marca.cname_alvo}</code>.
                  </li>
                  <li>Remova registros A/AAAA antigos desse nome. Proxy da Cloudflare: desligado (nuvem cinza).</li>
                  <li>Aguarde a propagação (minutos a algumas horas) e clique em “Verificar DNS”.</li>
                </ol>
                {marca.dominio_detalhe && <p className="text-sm text-ink-2">{marca.dominio_detalhe}</p>}
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    disabled={ocupado !== null}
                    onClick={() =>
                      void acao("verificar", () =>
                        api.POST("/api/v1/brands/{marca_id}/domain/verify", {
                          params: { path: { marca_id: marcaId } },
                        }),
                      )
                    }
                  >
                    {ocupado === "verificar" ? "Verificando…" : "Verificar DNS"}
                  </button>
                  {admin && marca.dominio_status === "verificado" && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={ocupado !== null}
                      onClick={() =>
                        void acao("ativar", () =>
                          api.POST("/api/v1/admin/brands/{marca_id}/domain/activate", {
                            params: { path: { marca_id: marcaId } },
                          }),
                        )
                      }
                    >
                      Marcar como ativo (HTTPS pronto)
                    </button>
                  )}
                </div>
              </div>
            )}
          </Secao>

          <Secao titulo="Equipe" descricao="Contas vinculadas à marca recebem e-mails, alertas e PDFs com a identidade dela.">
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <input
                type="checkbox"
                checked={marca.cadastro_aberto}
                disabled={ocupado !== null}
                onChange={(e) =>
                  void acao("cadastro", () =>
                    api.PATCH("/api/v1/brands/{marca_id}", {
                      params: { path: { marca_id: marcaId } },
                      body: { cadastro_aberto: e.target.checked },
                    }),
                  )
                }
              />
              Cadastro aberto: quem cria conta pelo endereço da marca entra nela
            </label>
            <form onSubmit={convidar} className="flex flex-wrap items-end gap-2">
              <div className="min-w-0 flex-[1_1_16rem]">
                <Campo rotulo="Convidar por e-mail">
                  <input type="email" required className="input" value={emailConvite} onChange={(e) => setEmailConvite(e.target.value)} placeholder="pessoa@orgao.gov.br" />
                </Campo>
              </div>
              <button type="submit" className="btn btn-ghost" disabled={ocupado !== null}>
                {ocupado === "convite" ? "Enviando…" : "Enviar convite"}
              </button>
            </form>
            <ul className="flex flex-col divide-y divide-hairline">
              {membros.map((m) => (
                <li key={m.id} className="flex flex-wrap items-center gap-2 py-2.5">
                  <div className="min-w-0 flex-[1_1_14rem]">
                    <p className="truncate text-sm">{m.nome || m.email}</p>
                    {m.nome && <p className="truncate text-xs text-ink-3">{m.email}</p>}
                  </div>
                  {m.id === marca.dono_id ? (
                    <StatusBadge tone="info">Dono</StatusBadge>
                  ) : (
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => void desvincular(m)}>
                      Tirar da marca
                    </button>
                  )}
                </li>
              ))}
              {convites
                .filter((c) => c.status === "pendente")
                .map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center gap-2 py-2.5">
                    <p className="min-w-0 flex-[1_1_14rem] truncate text-sm text-ink-2">{c.email}</p>
                    <StatusBadge>Convite pendente</StatusBadge>
                  </li>
                ))}
              {membros.length === 0 && convites.length === 0 && (
                <li className="py-2 text-sm text-ink-3">Nenhuma conta vinculada ainda.</li>
              )}
            </ul>
          </Secao>

          {admin && (
            <Secao titulo="Operação (administração)">
              <div className="grid gap-3 sm:grid-cols-2">
                <Campo rotulo="Subdomínio (slug)" ajuda={`${admSlug || "slug"}.${opcoes.dominio_base}`}>
                  <input className="input font-mono" value={admSlug} onChange={(e) => setAdmSlug(e.target.value.toLowerCase())} />
                </Campo>
                <Campo rotulo="E-mail do dono" ajuda="A conta precisa existir.">
                  <input type="email" className="input" value={admDono} onChange={(e) => setAdmDono(e.target.value)} />
                </Campo>
                <Campo rotulo="Plano de quem entra pela marca">
                  <select
                    className="input"
                    value={marca.plano_id ?? ""}
                    onChange={(e) =>
                      void acao("plano", () =>
                        api.PATCH("/api/v1/brands/{marca_id}", {
                          params: { path: { marca_id: marcaId } },
                          body: e.target.value ? { plano_id: e.target.value } : { remover_plano: true },
                        }),
                      )
                    }
                  >
                    <option value="">— sem plano definido —</option>
                    {planos.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.nome}
                      </option>
                    ))}
                  </select>
                </Campo>
                <label className="flex items-center gap-2 self-end pb-2 text-sm text-ink-2">
                  <input
                    type="checkbox"
                    checked={marca.ativo}
                    onChange={(e) =>
                      void acao("ativo", () =>
                        api.PATCH("/api/v1/brands/{marca_id}", {
                          params: { path: { marca_id: marcaId } },
                          body: { ativo: e.target.checked },
                        }),
                      )
                    }
                  />
                  Marca ativa (desativada, os endereços dela mostram o Hub Capture)
                </label>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={ocupado !== null || (admSlug === marca.slug && admDono === (marca.dono_email ?? ""))}
                  onClick={() =>
                    void acao("operacao", () =>
                      api.PATCH("/api/v1/brands/{marca_id}", {
                        params: { path: { marca_id: marcaId } },
                        body: {
                          ...(admSlug !== marca.slug ? { slug: admSlug } : {}),
                          ...(admDono !== (marca.dono_email ?? "")
                            ? admDono
                              ? { dono_email: admDono }
                              : { remover_dono: true }
                            : {}),
                        },
                      }),
                    )
                  }
                >
                  Aplicar slug/dono
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  disabled={ocupado !== null}
                  onClick={() =>
                    void acao("provisionar", () =>
                      api.POST("/api/v1/admin/brands/{marca_id}/provision", {
                        params: { path: { marca_id: marcaId } },
                      }),
                    )
                  }
                >
                  Refazer HTTPS ({opcoes.provisionador})
                </button>
                <button type="button" className="btn btn-ghost btn-sm text-danger" onClick={() => void excluir()}>
                  Excluir marca
                </button>
              </div>
              {(marca.provisionamento ?? []).length > 0 && (
                <ul className="flex flex-col gap-1 text-xs text-ink-2">
                  {marca.provisionamento!.map((p) => (
                    <li key={p.host}>
                      <span className="font-mono">{p.host}</span> — {p.status}
                      {p.detalhe ? `: ${p.detalhe}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </Secao>
          )}
        </div>

        <aside className="flex min-w-0 flex-col gap-2 xl:sticky xl:top-20 xl:self-start">
          <p className="label-mono">Pré-visualização</p>
          <Previa marca={marca} tema={tema} css={preview.css} fontes={preview.fontes} />
          <p className="text-xs text-ink-3">
            Segue o tema claro/escuro escolhido no seu menu da conta — troque lá para conferir os dois.
          </p>
        </aside>
      </div>
    </div>
  );
}
