"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, islandStream } from "@/lib/api/client";
import { paramMunicipio, useTerritorio } from "@/lib/territorio";

/**
 * Dynamic Island do Copiloto — pill flutuante que PERSISTE em todas as telas do
 * painel (montada no layout, pós-onboarding). Fechada, é uma cápsula discreta —
 * que MORFA para o estado de alerta quando há atualização de proposta não lida
 * (badge âmbar com a contagem). Expandida, vira um chat com o agente de tool
 * calling do backend, mostrando em tempo real qual ferramenta está sendo
 * consultada e pintando a resposta em streaming. Aceita DITADO por voz
 * (Web Speech API) e lê as respostas em voz alta quando o modo voz está ligado.
 * Histórico em sessionStorage — sobrevive à navegação entre telas.
 */

type Msg = { autor: "user" | "copiloto"; texto: string; tools?: string[] };

type Alerta = {
  id: string;
  tipo?: string | null;
  payload?: Record<string, unknown> | null;
  lido: boolean;
  created_at: string;
};

const HISTORICO_KEY = "hub_island_msgs";
const VOZ_KEY = "hub_island_voz";

const TOOL_LABEL: Record<string, string> = {
  repasses_visao_geral: "consultando repasses…",
  propostas_listar: "consultando fundos e propostas…",
  minhas_propostas: "abrindo Minhas propostas…",
  proposta_detalhe: "abrindo o detalhe da proposta…",
  captacao_resumo: "somando a execução financeira…",
  propostas_prazos: "verificando prazos…",
  pareceres_plano: "consultando pareceres do plano…",
  conformidade_resumo: "checando conformidade fiscal…",
  obras_resumo: "consultando obras…",
  emendas_resumo: "consultando emendas parlamentares…",
  alertas_atualizacoes: "lendo alertas de atualização…",
  alertas_varredura: "varrendo novidades…",
  alertas_marcar_lidos: "marcando alertas como lidos…",
  favoritar_proposta: "favoritando a proposta…",
  monitoramentos_listar: "listando monitoramentos…",
  pastas_listar: "abrindo suas pastas…",
  contatos_buscar: "buscando na agenda…",
  perfil_visao_geral: "montando a visão geral…",
  municipios_buscar: "buscando municípios…",
  class_buscar: "procurando no Class…",
  noticias_transferegov: "lendo notícias do TransfereGov…",
  pesquisar_propostas: "pesquisando propostas…",
};

const TOOL_CHIP: Record<string, string> = {
  repasses_visao_geral: "repasses",
  propostas_listar: "fundos/propostas",
  minhas_propostas: "minhas propostas",
  proposta_detalhe: "detalhe",
  captacao_resumo: "execução",
  propostas_prazos: "prazos",
  pareceres_plano: "pareceres",
  conformidade_resumo: "conformidade",
  obras_resumo: "obras",
  emendas_resumo: "emendas",
  alertas_atualizacoes: "alertas",
  alertas_varredura: "varredura",
  alertas_marcar_lidos: "lidos",
  favoritar_proposta: "favoritar",
  monitoramentos_listar: "monitoramentos",
  pastas_listar: "pastas",
  contatos_buscar: "contatos",
  perfil_visao_geral: "visão geral",
  municipios_buscar: "municípios",
  class_buscar: "class",
  noticias_transferegov: "notícias",
  pesquisar_propostas: "pesquisa",
};

// Rótulo curto do morph. As chaves são os CRITÉRIOS de alerta (§53) — critério
// novo sem entrada aqui cai em "atualização", nunca em chave crua na tela.
const TIPO_ALERTA: Record<string, string> = {
  status: "situação mudou", // legado (alertas anteriores ao registro)
  situacao: "situação mudou",
  prazo: "prazo alterado",
  pendencia: "nova pendência",
  parecer_novo: "novo parecer",
  parecer: "parecer atualizado",
  empenho: "empenho atualizado",
  empenho_pago: "empenho pago",
  pagamento: "pagamento",
  emenda: "emenda aplicada",
  publicacao: "proposta publicada",
  vencimento: "convênio vencendo",
  nova_proposta: "novo alerta",
  oportunidade: "oportunidade",
};

const SUGESTOES = [
  "Quanto meu município recebeu?",
  "O que mudou nas minhas propostas?",
  "Quais propostas vencem este mês?",
];

// as ferramentas de AÇÃO mudam o estado dos alertas — o badge é recarregado
const TOOLS_QUE_MUDAM_ALERTAS = new Set([
  "alertas_varredura",
  "alertas_marcar_lidos",
  "favoritar_proposta",
]);

/* Web Speech API — o TS não traz os tipos por padrão (e `any` é proibido). */
type ResultadoVoz = {
  resultIndex: number;
  results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }>;
};
type ReconhecimentoVoz = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: ResultadoVoz) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
};
type JanelaComVoz = {
  SpeechRecognition?: new () => ReconhecimentoVoz;
  webkitSpeechRecognition?: new () => ReconhecimentoVoz;
};

function construtorDeVoz(): (new () => ReconhecimentoVoz) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as JanelaComVoz;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function historicoInicial(): Msg[] {
  if (typeof window !== "undefined") {
    try {
      const salvo = window.sessionStorage.getItem(HISTORICO_KEY);
      if (salvo) return JSON.parse(salvo) as Msg[];
    } catch {
      /* histórico corrompido → recomeça */
    }
  }
  return [];
}

function tituloDoAlerta(a: Alerta): string {
  const p = (a.payload ?? {}) as Record<string, string | undefined>;
  return (
    p.titulo ?? p.municipio_nome ?? p.municipio_ibge ?? "proposta do território"
  );
}

export default function DynamicIsland() {
  // o island flutua sobre o painel: pergunta sempre no recorte que está em tela
  const { selecionados } = useTerritorio();
  const [aberta, setAberta] = useState(false);
  const [mensagens, setMensagens] = useState<Msg[]>(historicoInicial);
  const [pergunta, setPergunta] = useState("");
  const [pensando, setPensando] = useState(false);
  const [statusTool, setStatusTool] = useState<string | null>(null);
  // resposta em STREAMING (pinta enquanto chega — a fluidez vem daqui)
  const [parcial, setParcial] = useState<string | null>(null);
  // morph de atualização: alertas não lidos de proposta do território
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [varrendo, setVarrendo] = useState(false);
  // voz: ditado (speech→texto) e leitura em voz alta (texto→speech)
  const [ouvindo, setOuvindo] = useState(false);
  const [suportaDitado, setSuportaDitado] = useState(false);
  const [vozAtiva, setVozAtiva] = useState(false);
  const reconhecimentoRef = useRef<ReconhecimentoVoz | null>(null);
  const fimRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    window.sessionStorage.setItem(HISTORICO_KEY, JSON.stringify(mensagens));
  }, [mensagens]);

  useEffect(() => {
    setSuportaDitado(construtorDeVoz() !== null);
    try {
      setVozAtiva(window.localStorage.getItem(VOZ_KEY) === "on");
    } catch {
      /* sem localStorage → voz desligada */
    }
  }, []);

  useEffect(() => {
    if (aberta) fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, statusTool, parcial, aberta]);

  const carregarAlertas = useCallback(async () => {
    try {
      const { data } = await api.GET("/api/v1/alerts", {
        params: {
          query: { nao_lidos: true, municipio: paramMunicipio(selecionados) },
        },
      });
      if (data) setAlertas(data as Alerta[]);
    } catch {
      /* sem rede/módulo → badge some, o chat continua */
    }
  }, [selecionados]);

  // badge de atualização: carrega ao montar e re-verifica periodicamente
  useEffect(() => {
    void carregarAlertas();
    const timer = window.setInterval(() => {
      if (!document.hidden) void carregarAlertas();
    }, 90_000);
    return () => window.clearInterval(timer);
  }, [carregarAlertas]);

  // fala a resposta quando o modo voz está ligado (ou a pergunta foi ditada)
  const falarTexto = useCallback((texto: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    try {
      const fala = new SpeechSynthesisUtterance(
        texto
          .replace(/[•*_#`→]/g, " ")
          .replace(/\s+/g, " ")
          .slice(0, 600),
      );
      fala.lang = "pt-BR";
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(fala);
    } catch {
      /* voz indisponível — resposta segue no texto */
    }
  }, []);

  function alternarVoz() {
    const nova = !vozAtiva;
    setVozAtiva(nova);
    try {
      window.localStorage.setItem(VOZ_KEY, nova ? "on" : "off");
    } catch {
      /* preferências não persistem sem localStorage */
    }
    if (!nova && typeof window !== "undefined" && "speechSynthesis" in window)
      window.speechSynthesis.cancel();
  }

  const perguntar = useCallback(
    async (texto: string, opts?: { porVoz?: boolean }) => {
      const q = texto.trim();
      if (!q || pensando) return;
      setPergunta("");
      setPensando(true);
      setParcial(null);
      setMensagens((m) => [...m, { autor: "user", texto: q }]);
      const tools: string[] = [];
      let resposta = "";
      try {
        await islandStream(
          q,
          (ev) => {
            if (ev.tool) {
              tools.push(ev.tool);
              setStatusTool(ev.tool);
            }
            if (ev.delta) {
              resposta += ev.delta;
              setStatusTool(null);
              setParcial(resposta);
            }
          },
          selecionados,
        );
        const texto_final =
          resposta || "Não consegui responder agora — tente de novo.";
        setMensagens((m) => [
          ...m,
          { autor: "copiloto", texto: texto_final, tools: [...new Set(tools)] },
        ]);
        if (vozAtiva || opts?.porVoz) falarTexto(texto_final);
        if (tools.some((t) => TOOLS_QUE_MUDAM_ALERTAS.has(t)))
          void carregarAlertas();
      } catch {
        setMensagens((m) => [
          ...m,
          {
            autor: "copiloto",
            texto: "Falha ao falar com o Copiloto. Tente de novo.",
          },
        ]);
      } finally {
        setStatusTool(null);
        setParcial(null);
        setPensando(false);
      }
    },
    [pensando, selecionados, vozAtiva, falarTexto, carregarAlertas],
  );

  // ditado: preenche o campo enquanto fala e envia quando a frase fecha
  function alternarDitado() {
    if (ouvindo) {
      reconhecimentoRef.current?.stop();
      return;
    }
    const Construtor = construtorDeVoz();
    if (!Construtor) return;
    const rec = new Construtor();
    rec.lang = "pt-BR";
    rec.interimResults = true;
    rec.continuous = false;
    let transcricao = "";
    rec.onresult = (e) => {
      const partes: string[] = [];
      for (let i = 0; i < e.results.length; i += 1) {
        const r = e.results[i];
        if (r) partes.push(r[0].transcript);
      }
      transcricao = partes.join(" ");
      setPergunta(transcricao);
    };
    rec.onend = () => {
      setOuvindo(false);
      reconhecimentoRef.current = null;
      if (transcricao.trim()) void perguntar(transcricao, { porVoz: true });
    };
    rec.onerror = () => {
      setOuvindo(false);
      reconhecimentoRef.current = null;
    };
    reconhecimentoRef.current = rec;
    setOuvindo(true);
    rec.start();
  }

  // varredura sob demanda: detecta atualizações e alimenta o morph de alerta
  async function varrer() {
    if (varrendo) return;
    setVarrendo(true);
    try {
      await api.POST("/api/v1/alerts/scan");
      await carregarAlertas();
    } finally {
      setVarrendo(false);
    }
  }

  async function marcarTodasLidas() {
    const pendentes = alertas.slice(0, 20);
    for (const a of pendentes) {
      await api.POST("/api/v1/alerts/{alerta_id}/read", {
        params: { path: { alerta_id: a.id } },
      });
    }
    await carregarAlertas();
  }

  function abrir() {
    setAberta(true);
    void carregarAlertas();
  }

  const temAtualizacao = alertas.length > 0;

  return (
    <div className="pointer-events-none fixed inset-x-0 top-3 z-50 flex justify-center px-3">
      <div
        className={`island pointer-events-auto relative overflow-hidden bg-abyss text-white shadow-2xl ring-1 ${
          temAtualizacao && !aberta ? "ring-amber-300/40" : "ring-white/10"
        } ${
          aberta
            ? "w-full max-w-md rounded-3xl"
            : "island-fechada w-auto cursor-pointer rounded-full hover:ring-white/25"
        }`}
      >
        {!aberta ? (
          <button
            onClick={abrir}
            className="anim-fade-in flex items-center gap-2.5 px-4 py-2 text-sm"
            aria-label={
              temAtualizacao
                ? `Abrir Copiloto — ${alertas.length} atualização(ões) de proposta`
                : "Abrir Copiloto"
            }
          >
            <span className="relative flex h-2 w-2">
              <span
                className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  temAtualizacao ? "animate-ping bg-amber-400" : "bg-lime"
                } ${pensando ? "animate-ping" : ""}`}
              />
              <span
                className={`relative inline-flex h-2 w-2 rounded-full ${
                  temAtualizacao ? "bg-amber-400" : "bg-lime"
                }`}
              />
            </span>
            <span className="font-medium">Copiloto</span>
            {/* morph de ATUALIZAÇÃO: proposta mudou → a cápsula avisa */}
            {temAtualizacao && (
              <span className="rounded-full bg-amber-400/15 px-2 py-0.5 text-xs font-medium text-amber-300">
                {alertas.length}{" "}
                {alertas.length === 1 ? "atualização" : "atualizações"}
              </span>
            )}
            {pensando && statusTool && (
              <span className="text-xs text-white/60">
                {TOOL_LABEL[statusTool] ?? "consultando…"}
              </span>
            )}
          </button>
        ) : (
          <div className="anim-fade-in flex max-h-[70vh] flex-col">
            <div className="flex items-center justify-between px-4 py-2.5">
              <div className="flex items-center gap-2.5">
                <span className="relative flex h-2 w-2">
                  <span
                    className={`absolute inline-flex h-full w-full rounded-full bg-lime opacity-75 ${
                      pensando ? "animate-ping" : ""
                    }`}
                  />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-lime" />
                </span>
                <span className="text-sm font-medium">Copiloto</span>
                <span className="font-mono text-[10px] uppercase tracking-wider text-white/40">
                  seu território, ao vivo
                </span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => void varrer()}
                  disabled={varrendo}
                  title="Atualizar — varrer novidades das propostas"
                  aria-label="Atualizar alertas"
                  className={`pressable rounded-full px-2 py-0.5 text-white/60 hover:bg-white/10 hover:text-white ${
                    varrendo ? "animate-spin" : ""
                  }`}
                >
                  ⟳
                </button>
                <button
                  onClick={alternarVoz}
                  title={
                    vozAtiva
                      ? "Desligar leitura em voz alta"
                      : "Ler respostas em voz alta"
                  }
                  aria-label="Alternar voz"
                  className={`pressable rounded-full px-2 py-0.5 hover:bg-white/10 ${
                    vozAtiva ? "text-lime" : "text-white/40 hover:text-white"
                  }`}
                >
                  {vozAtiva ? "🔊" : "🔇"}
                </button>
                <button
                  onClick={() => setAberta(false)}
                  className="pressable rounded-full px-2 py-0.5 text-white/60 hover:bg-white/10 hover:text-white"
                  aria-label="Recolher Copiloto"
                >
                  —
                </button>
              </div>
            </div>

            {/* morph de atualização expandido: o que mudou nas propostas */}
            {temAtualizacao && (
              <div className="mx-3 mb-1.5 rounded-2xl bg-amber-400/10 px-3 py-2 ring-1 ring-amber-300/20">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-amber-200">
                    {alertas.length}{" "}
                    {alertas.length === 1
                      ? "atualização de proposta"
                      : "atualizações de proposta"}
                  </span>
                  <button
                    onClick={() => void marcarTodasLidas()}
                    className="text-[10px] uppercase tracking-wider text-amber-300/80 hover:text-amber-200"
                  >
                    marcar lidas
                  </button>
                </div>
                <ul className="mt-1 space-y-0.5">
                  {alertas.slice(0, 3).map((a) => (
                    <li key={a.id} className="truncate text-xs text-white/75">
                      <span className="text-amber-300/90">
                        {TIPO_ALERTA[a.tipo ?? ""] ?? "atualização"}
                      </span>{" "}
                      — {tituloDoAlerta(a)}
                    </li>
                  ))}
                </ul>
                <Link
                  href="/panel/alerts"
                  className="mt-1 inline-block text-[11px] text-amber-200/90 underline-offset-2 hover:underline"
                >
                  ver central de alertas →
                </Link>
              </div>
            )}

            <div className="flex-1 space-y-2.5 overflow-y-auto px-4 pb-2">
              {mensagens.length === 0 && (
                <div className="space-y-1.5 pb-1">
                  <p className="text-xs text-white/50">
                    Pergunte sobre repasses, fundos, prazos, obras, alertas ou
                    suas propostas favoritas — eu consulto os dados reais do seu
                    território. Dá para ditar 🎙 e ouvir 🔊.
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {SUGESTOES.map((s) => (
                      <button
                        key={s}
                        onClick={() => void perguntar(s)}
                        className="pressable rounded-full border border-white/15 px-2.5 py-1 text-xs text-white/80 hover:border-lime/40 hover:bg-white/10"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {mensagens.map((m, i) => (
                <div
                  key={i}
                  className={`anim-pop max-w-[90%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm leading-relaxed ${
                    m.autor === "user"
                      ? "ml-auto rounded-br-md bg-lime text-abyss"
                      : "rounded-bl-md bg-white/10"
                  }`}
                >
                  {m.texto}
                  {m.autor === "copiloto" && (m.tools ?? []).length > 0 && (
                    <span className="mt-1.5 flex flex-wrap gap-1">
                      {m.tools!.map((t) => (
                        <span
                          key={t}
                          className="rounded-full bg-white/10 px-1.5 py-px font-mono text-[9px] uppercase tracking-wider text-white/50"
                        >
                          {TOOL_CHIP[t] ?? t}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
              ))}
              {pensando && (
                <div className="anim-pop max-w-[90%] whitespace-pre-wrap rounded-2xl rounded-bl-md bg-white/10 px-3 py-2 text-sm leading-relaxed">
                  {parcial ? (
                    <>
                      {parcial}
                      <span className="ml-0.5 inline-block h-3 w-1 animate-pulse bg-lime align-baseline" />
                    </>
                  ) : (
                    <span className="flex items-center gap-2 text-white/60">
                      <span className="flex items-center gap-1" aria-hidden>
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                        <span className="typing-dot" />
                      </span>
                      {statusTool
                        ? (TOOL_LABEL[statusTool] ?? "consultando…")
                        : "pensando…"}
                    </span>
                  )}
                </div>
              )}
              <div ref={fimRef} />
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void perguntar(pergunta);
              }}
              className="flex items-center gap-2 border-t border-white/10 px-3 py-2.5"
            >
              {suportaDitado && (
                <button
                  type="button"
                  onClick={alternarDitado}
                  title={ouvindo ? "Parar de ouvir" : "Ditar pergunta"}
                  aria-label={ouvindo ? "Parar ditado" : "Ditar pergunta"}
                  className={`pressable rounded-full px-2 py-1 text-sm ${
                    ouvindo
                      ? "animate-pulse bg-lime text-abyss"
                      : "text-white/50 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  🎙
                </button>
              )}
              <input
                value={pergunta}
                onChange={(e) => setPergunta(e.target.value)}
                placeholder={ouvindo ? "ouvindo…" : "Pergunte ao Copiloto…"}
                className="flex-1 rounded-full bg-white/[0.06] px-3 py-1.5 text-sm text-white placeholder-white/40 outline-none ring-1 ring-white/10 transition-all duration-200 focus:bg-white/[0.1] focus:ring-lime/40"
                autoFocus
              />
              <button
                type="submit"
                disabled={pensando || !pergunta.trim()}
                className="pressable rounded-full bg-[image:var(--grad-brand)] px-3 py-1 text-sm font-medium text-abyss shadow-[0_2px_12px_color-mix(in_srgb,var(--color-lime)_35%,transparent)] disabled:opacity-40 disabled:shadow-none"
              >
                →
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
