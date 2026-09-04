"use client";

/**
 * Ano (ano) ativa do painel — o terceiro recorte global, ao lado do
 * território (§33) e da origem do recurso (§33b).
 *
 * Ele já era um recorte de PÁGINA inteira (cards das dimensões, panorama
 * financeiro e feed pedem a mesma ano à API) e já persistia por navegador,
 * mas morava sozinho no canto do cabeçalho do Meu painel — longe dos outros
 * dois, que ficam na barra de recorte. Três filtros do mesmo alcance em dois
 * lugares diferentes é o que a §58 tirou do menu; deixar um deles de fora
 * repetia o problema. Aqui a seleção vira contexto e a barra a desenha junto
 * dos irmãos.
 *
 * `anos` vazio = TODOS os anos (o padrão). As OPÇÕES não são fixas: quem sabe
 * quais anos existem no território é a tela que carrega o feed, e ela as
 * publica com `definirOpcoes` — a barra só se desenha quando há mais de uma
 * (filtro com uma opção só não recorta nada).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export interface OpcaoAno {
  ano: string;
  total: number;
}

const CHAVE = "hub_painel_ano";

interface AnoCtx {
  /** Anos escolhidas; vazio = todos os anos. */
  anos: string[];
  /** Anos que EXISTEM no território, da mais recente à mais antiga. */
  opcoes: OpcaoAno[];
  /** A tela publica o catálogo que veio da API (o feed sabe, o layout não). */
  definirOpcoes: (opcoes: OpcaoAno[]) => void;
  alternar: (ano: string) => void;
  todos: () => void;
}

const Ctx = createContext<AnoCtx>({
  anos: [],
  opcoes: [],
  definirOpcoes: () => {},
  alternar: () => {},
  todos: () => {},
});

/** Preferência salva ([] = todos os anos). O valor é uma lista separada por
 *  vírgula; o formato antigo (um ano só) continua lendo. */
function lerSalvos(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const salvo = window.localStorage.getItem(CHAVE) ?? "";
    return salvo.split(",").filter((a) => /^\d{4}$/.test(a));
  } catch {
    return []; // preferência corrompida/indisponível → todos os anos
  }
}

export function AnoProvider({ children }: { children: React.ReactNode }) {
  // Ler o localStorage já no initializer divergiria do HTML do servidor, que
  // não tem acesso a ele — erro de hidratação; a restauração vem no efeito.
  const [anos, setAnos] = useState<string[]>([]);
  const [opcoes, setOpcoes] = useState<OpcaoAno[]>([]);
  const restaurada = useRef(false);

  useEffect(() => {
    const salvos = lerSalvos();
    if (salvos.length) setAnos(salvos);
    restaurada.current = true;
  }, []);

  // Persiste a escolha. O guard evita o efeito rodar ANTES da restauração e
  // gravar o padrão por cima do que o usuário já tinha escolhido.
  useEffect(() => {
    if (!restaurada.current) return;
    try {
      window.localStorage.setItem(CHAVE, anos.join(","));
    } catch {
      /* storage cheio/bloqueado: o filtro vale nesta sessão */
    }
  }, [anos]);

  const definirOpcoes = useCallback((lista: OpcaoAno[]) => {
    const ordenadas = [...lista].sort((a, b) => b.ano.localeCompare(a.ano));
    setOpcoes((prev) =>
      prev.length === ordenadas.length &&
      prev.every((o, i) => o.ano === ordenadas[i]!.ano && o.total === ordenadas[i]!.total)
        ? prev // mesma resposta do feed: não remonta a barra a cada carga
        : ordenadas,
    );
    // Ano salva que não existe mais no território (município trocado, cache
    // zerado) prenderia o painel num recorte vazio — sai do conjunto.
    if (ordenadas.length === 0) return;
    const existentes = new Set(ordenadas.map((o) => o.ano));
    setAnos((prev) => {
      const validos = prev.filter((a) => existentes.has(a));
      return validos.length === prev.length ? prev : validos;
    });
  }, []);

  const valor = useMemo<AnoCtx>(
    () => ({
      anos,
      opcoes,
      definirOpcoes,
      alternar: (ano) =>
        setAnos((prev) =>
          prev.includes(ano) ? prev.filter((a) => a !== ano) : [...prev, ano],
        ),
      todos: () => setAnos([]),
    }),
    [anos, opcoes, definirOpcoes],
  );

  return <Ctx.Provider value={valor}>{children}</Ctx.Provider>;
}

export function useAno(): AnoCtx {
  return useContext(Ctx);
}
