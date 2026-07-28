"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { BrandMark } from "@/components/AuthShell";
import { ChatBubble, TypingDots } from "@/components/Chat";
import { api, getToken } from "@/lib/api/client";

/**
 * Onboarding conversacional — o Copiloto pergunta o perfil (papel, território,
 * áreas e fontes) num chat guiado e configura a conta ao final. O 1º sync com
 * dados REAIS das fontes dispara em background na API; o usuário cai no painel
 * já vendo o feed se povoar.
 */

type Msg = { autor: "copiloto" | "user"; texto: string };
type Etapa =
  | "papel"
  | "municipios"
  | "areas"
  | "fontes"
  | "avisos"
  | "confirmar"
  | "salvando";

interface MunicipioBusca {
  ibge: string;
  nome: string;
  uf?: string | null;
}

const PAPEIS = [
  { value: "parlamentar", label: "Parlamentar" },
  { value: "executivo", label: "Prefeitura / Executivo" },
  { value: "equipe", label: "Equipe / Assessoria" },
];

const AREAS = [
  { value: "saude", label: "Saúde" },
  { value: "educacao", label: "Educação" },
  { value: "cultura", label: "Cultura" },
  { value: "infraestrutura", label: "Obras e infraestrutura" },
  { value: "assistencia_social", label: "Assistência social" },
  { value: "esporte", label: "Esporte" },
  { value: "meio_ambiente", label: "Meio ambiente" },
  { value: "agricultura", label: "Agricultura" },
];

const FONTES = [
  { value: "transferegov_ff", label: "TransfereGov (Fundo a Fundo)" },
  { value: "transferegov_esp", label: "TransfereGov (Especiais)" },
  { value: "transferegov_voluntarias", label: "TransfereGov (Voluntárias)" },
  { value: "fpm", label: "FPM (Tesouro)" },
  { value: "emendas", label: "Emendas parlamentares" },
  { value: "fns", label: "FNS — Fundo Nacional de Saúde" },
  { value: "fnde", label: "FNDE — Educação" },
];

// Sugestão de fontes a partir das áreas — o Copiloto pré-marca por você.
function fontesSugeridas(areas: string[]): string[] {
  const f = new Set(["transferegov_ff", "fpm", "emendas"]);
  if (areas.includes("saude")) f.add("fns");
  if (areas.includes("educacao")) f.add("fnde");
  if (
    areas.some((a) =>
      ["cultura", "esporte", "meio_ambiente", "agricultura"].includes(a),
    )
  )
    f.add("transferegov_voluntarias");
  if (areas.includes("infraestrutura")) f.add("transferegov_esp");
  return [...f];
}

const rotulo = (lista: { value: string; label: string }[], v: string) =>
  lista.find((o) => o.value === v)?.label ?? v;

export default function OnboardingPage() {
  const router = useRouter();
  const [mensagens, setMensagens] = useState<Msg[]>([]);
  const [digitando, setDigitando] = useState(false);
  const [etapa, setEtapa] = useState<Etapa>("papel");

  const [papel, setPapel] = useState<string | null>(null);
  const [municipios, setMunicipios] = useState<MunicipioBusca[]>([]);
  const [areas, setAreas] = useState<string[]>([]);
  const [fontes, setFontes] = useState<string[]>([]);

  const [busca, setBusca] = useState("");
  const [sugestoes, setSugestoes] = useState<MunicipioBusca[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  // passo "ativar avisos": canais + WhatsApp opcional
  const [telefone, setTelefone] = useState("");
  const [canaisAlerta, setCanaisAlerta] = useState<string[]>(["painel"]);

  const fimRef = useRef<HTMLDivElement>(null);
  const timeouts = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, digitando, etapa]);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    falar([
      "Olá! Eu sou o Copiloto do Hub Capture. Vou montar seu painel em menos de um minuto.",
      "Pra começar: qual é o seu papel na gestão pública?",
    ]);
    return () => timeouts.current.forEach(clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Fala do Copiloto com efeito de digitação entre as frases. */
  function falar(textos: string[], aoTerminar?: () => void) {
    setDigitando(true);
    textos.forEach((texto, i) => {
      const t = setTimeout(() => {
        setMensagens((m) => [...m, { autor: "copiloto", texto }]);
        if (i === textos.length - 1) {
          setDigitando(false);
          aoTerminar?.();
        }
      }, 450 * (i + 1));
      timeouts.current.push(t);
    });
  }

  function responder(texto: string) {
    setMensagens((m) => [...m, { autor: "user", texto }]);
  }

  // ── Etapa 1: papel ────────────────────────────────────────────────────────
  function escolherPapel(v: string) {
    setPapel(v);
    responder(rotulo(PAPEIS, v));
    setEtapa("municipios");
    falar([
      "Perfeito. E qual município você quer acompanhar?",
      "Digite o nome (ou o código IBGE) e escolha na lista. Pode adicionar mais de um.",
    ]);
  }

  // ── Etapa 2: municípios (busca por nome via IBGE) ─────────────────────────
  useEffect(() => {
    if (etapa !== "municipios" || busca.trim().length < 2) {
      setSugestoes([]);
      return;
    }
    const t = setTimeout(async () => {
      const { data } = await api.GET("/api/v1/municipios", {
        params: { query: { q: busca.trim() } },
      });
      setSugestoes(((data ?? []) as MunicipioBusca[]).slice(0, 6));
    }, 300);
    return () => clearTimeout(t);
  }, [busca, etapa]);

  function adicionarMunicipio(m: MunicipioBusca) {
    if (municipios.some((x) => x.ibge === m.ibge)) return;
    setMunicipios((lista) => [...lista, m]);
    setBusca("");
    setSugestoes([]);
    responder(`${m.nome}${m.uf ? `/${m.uf}` : ""}`);
    falar([
      `Anotado: ${m.nome}${m.uf ? `/${m.uf}` : ""}. Quer adicionar outro município ou seguimos?`,
    ]);
  }

  function adicionarPorCodigo() {
    const codigo = busca.trim();
    if (/^\d{7}$/.test(codigo)) {
      adicionarMunicipio({ ibge: codigo, nome: `IBGE ${codigo}` });
    }
  }

  function concluirMunicipios() {
    if (municipios.length === 0) return;
    responder("Pode seguir!");
    setEtapa("areas");
    falar([
      "Ótimo. Quais ÁREAS interessam mais? Isso ajusta o que te mostro primeiro.",
      "Marque quantas quiser e toque em continuar.",
    ]);
  }

  // ── Etapa 3: áreas ────────────────────────────────────────────────────────
  function toggleArea(v: string) {
    setAreas((a) => (a.includes(v) ? a.filter((x) => x !== v) : [...a, v]));
  }

  function concluirAreas() {
    responder(
      areas.length
        ? areas.map((a) => rotulo(AREAS, a)).join(", ")
        : "Sem preferência — tudo me interessa",
    );
    setFontes(fontesSugeridas(areas));
    setEtapa("fontes");
    falar([
      "Fechado. E de quais FONTES oficiais você quer receber dados?",
      "Já marquei as que combinam com o seu perfil — ajuste se quiser.",
    ]);
  }

  // ── Etapa 4: fontes ───────────────────────────────────────────────────────
  function toggleFonte(v: string) {
    setFontes((f) => (f.includes(v) ? f.filter((x) => x !== v) : [...f, v]));
  }

  function concluirFontes() {
    if (fontes.length === 0) return;
    responder(fontes.map((f) => rotulo(FONTES, f)).join(", "));
    setEtapa("avisos");
    falar([
      "Última coisa: quer ser AVISADO quando aparecer proposta nova ou algo mudar?",
      "O painel sempre mostra os alertas. Se quiser, eu também aviso por e-mail — e no WhatsApp, é só deixar seu número.",
    ]);
  }

  // ── Etapa 5: ativar avisos (e conectar WhatsApp, se quiser) ───────────────
  function toggleCanal(v: string) {
    setCanaisAlerta((c) =>
      c.includes(v) ? c.filter((x) => x !== v) : [...c, v],
    );
  }

  function concluirAvisos() {
    const optinWpp = canaisAlerta.includes("wpp") && telefone.trim().length >= 10;
    const partes = ["painel"];
    if (canaisAlerta.includes("email")) partes.push("e-mail");
    if (optinWpp) partes.push(`WhatsApp (${telefone.trim()})`);
    responder(`Avisos por: ${partes.join(", ")}`);
    setEtapa("confirmar");
    falar([
      "Tudo pronto! Vou configurar seu painel assim:",
      resumo(),
      "Confirma? Assim que você confirmar, eu já começo a buscar os dados reais nas fontes.",
    ]);
  }

  function resumo(): string {
    const m = municipios
      .map((x) => `${x.nome}${x.uf ? `/${x.uf}` : ""}`)
      .join(", ");
    const a = areas.length
      ? areas.map((x) => rotulo(AREAS, x)).join(", ")
      : "todas";
    const optinWpp = canaisAlerta.includes("wpp") && telefone.trim().length >= 10;
    const avisos = [
      "painel",
      canaisAlerta.includes("email") ? "e-mail" : null,
      optinWpp ? "WhatsApp" : null,
    ]
      .filter(Boolean)
      .join(", ");
    return `• Papel: ${papel ? rotulo(PAPEIS, papel) : "—"}\n• Território: ${m}\n• Áreas: ${a}\n• Fontes: ${fontes.map((f) => rotulo(FONTES, f)).join(", ")}\n• Avisos: ${avisos}`;
  }

  // ── Etapa 6: confirmar → grava e dispara o 1º sync real ──────────────────
  async function confirmar() {
    responder("Confirmo!");
    setEtapa("salvando");
    setErro(null);
    falar(["Configurando seu painel e disparando a primeira coleta…"]);
    const optinWpp = canaisAlerta.includes("wpp") && telefone.trim().length >= 10;
    const { error } = await api.POST("/api/v1/onboarding", {
      body: {
        municipios: municipios.map((m) => ({
          ibge: m.ibge,
          nome: m.nome.startsWith("IBGE ") ? null : m.nome,
          uf: m.uf ?? null,
        })),
        fontes,
        areas,
        monitorar_ativo: true,
        papel: papel ?? undefined,
        disparar_sync: true,
        telefone_wpp: optinWpp ? telefone.trim() : null,
        optin_wpp: optinWpp,
        canais_alerta: canaisAlerta,
      },
    });
    if (error) {
      const detail = (error as { detail?: unknown }).detail;
      setErro(
        typeof detail === "string" && detail.startsWith("LIMITE_PLANO")
          ? "Seu plano não permite tantos municípios — remova algum ou fale com o suporte para mudar de plano."
          : "Não consegui salvar seu perfil. Tente confirmar novamente.",
      );
      setEtapa("confirmar");
      return;
    }
    falar(
      ["Perfil salvo! Te levando para o seu painel — os dados chegam em instantes."],
      () => router.push("/painel?sync=1"),
    );
  }

  const ETAPAS: Etapa[] = ["papel", "municipios", "areas", "fontes", "confirmar"];
  const progresso =
    ((etapa === "salvando" ? ETAPAS.length : ETAPAS.indexOf(etapa)) /
      ETAPAS.length) *
    100;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-4 px-4 py-8 sm:px-6">
      <div className="anim-fade-up flex items-center justify-between">
        <BrandMark />
        <span className="label-mono">Onboarding</span>
      </div>

      {/* Progresso da conversa — gradiente da marca preenchendo as etapas */}
      <div className="anim-fade-up progress-track" aria-hidden>
        <div className="progress-fill" style={{ width: `${progresso}%` }} />
      </div>

      <div className="card anim-fade-up flex flex-1 flex-col gap-3 p-5">
        {mensagens.map((m, i) => (
          <ChatBubble key={i} autor={m.autor === "user" ? "user" : "ai"}>
            {m.texto}
          </ChatBubble>
        ))}
        {digitando && <TypingDots />}
        <div ref={fimRef} />
      </div>

      {/* Área de resposta do usuário — muda conforme a etapa da conversa. */}
      {!digitando && etapa === "papel" && (
        <div className="stagger flex flex-wrap gap-2">
          {PAPEIS.map((p) => (
            <button
              key={p.value}
              onClick={() => escolherPapel(p.value)}
              className="chip"
            >
              {p.label}
            </button>
          ))}
        </div>
      )}

      {etapa === "municipios" && !digitando && (
        <div className="anim-fade-up flex flex-col gap-2">
          {municipios.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {municipios.map((m) => (
                <span key={m.ibge} className="chip chip-active">
                  {m.nome}
                  {m.uf ? `/${m.uf}` : ""}
                  <button
                    onClick={() =>
                      setMunicipios((l) => l.filter((x) => x.ibge !== m.ibge))
                    }
                    className="ml-2 opacity-70 hover:opacity-100"
                    aria-label={`Remover ${m.nome}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="relative">
            <input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && adicionarPorCodigo()}
              placeholder="Nome do município ou código IBGE…"
              className="input w-full"
              autoFocus
            />
            {sugestoes.length > 0 && (
              <div className="card anim-pop absolute inset-x-0 top-full z-10 mt-1 flex flex-col overflow-hidden p-1">
                {sugestoes.map((s) => (
                  <button
                    key={s.ibge}
                    onClick={() => adicionarMunicipio(s)}
                    className="rounded-lg px-3 py-2 text-left text-sm hover:bg-surface-2"
                  >
                    {s.nome}
                    {s.uf ? `/${s.uf}` : ""}{" "}
                    <span className="font-mono text-[11px] text-ink-3">
                      {s.ibge}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
          {municipios.length > 0 && (
            <button onClick={concluirMunicipios} className="btn btn-primary self-end">
              Continuar
            </button>
          )}
        </div>
      )}

      {etapa === "areas" && !digitando && (
        <div className="anim-fade-up flex flex-col gap-3">
          <div className="stagger flex flex-wrap gap-2">
            {AREAS.map((a) => (
              <button
                key={a.value}
                onClick={() => toggleArea(a.value)}
                className={`chip ${areas.includes(a.value) ? "chip-active" : ""}`}
              >
                {a.label}
              </button>
            ))}
          </div>
          <button onClick={concluirAreas} className="btn btn-primary self-end">
            Continuar
          </button>
        </div>
      )}

      {etapa === "fontes" && !digitando && (
        <div className="anim-fade-up flex flex-col gap-3">
          <div className="stagger flex flex-wrap gap-2">
            {FONTES.map((f) => (
              <button
                key={f.value}
                onClick={() => toggleFonte(f.value)}
                className={`chip ${fontes.includes(f.value) ? "chip-active" : ""}`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <button
            onClick={concluirFontes}
            disabled={fontes.length === 0}
            className="btn btn-primary self-end"
          >
            Continuar
          </button>
        </div>
      )}

      {etapa === "avisos" && !digitando && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap gap-2">
            <span className="chip chip-active">Painel (sempre)</span>
            <button
              onClick={() => toggleCanal("email")}
              className={`chip ${canaisAlerta.includes("email") ? "chip-active" : ""}`}
            >
              E-mail
            </button>
            <button
              onClick={() => toggleCanal("wpp")}
              className={`chip ${canaisAlerta.includes("wpp") ? "chip-active" : ""}`}
            >
              WhatsApp
            </button>
          </div>
          {canaisAlerta.includes("wpp") && (
            <input
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="Seu WhatsApp com DDD, ex.: 11 91234-5678"
              className="input w-full"
              inputMode="tel"
              autoFocus
            />
          )}
          <button onClick={concluirAvisos} className="btn btn-primary self-end">
            Continuar
          </button>
        </div>
      )}

      {etapa === "confirmar" && !digitando && (
        <div className="anim-fade-up flex flex-col gap-2">
          {erro && <p className="text-sm text-red-500">{erro}</p>}
          <div className="flex justify-end gap-2">
            <button onClick={() => setEtapa("papel")} className="chip">
              Recomeçar
            </button>
            <button onClick={confirmar} className="btn btn-primary">
              Confirmar e buscar dados
            </button>
          </div>
        </div>
      )}
    </main>
  );
}
