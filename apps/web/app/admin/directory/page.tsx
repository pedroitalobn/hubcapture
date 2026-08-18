"use client";

/**
 * Diretório institucional (ponto 19) — a lista que o gestor consulta na aba
 * Agenda de contatos: gabinetes de ministros, chefias de gabinete, assessorias
 * parlamentares e os SEIs dos protocolos.
 *
 * É curadoria da administração, igual para todos os clientes (nível-plataforma,
 * sem RLS), então mora aqui e não na agenda pessoal de ninguém. Salvar substitui
 * a lista inteira — é o mesmo gesto da tela de Assessoria.
 */

import { useCallback, useEffect, useState } from "react";
import { Skeleton } from "@/components/Skeleton";
import { api } from "@/lib/api/client";

interface Linha {
  nome: string;
  orgao: string;
  cargo: string;
  categoria: string;
  email: string;
  telefone: string;
  sei: string;
  sei_url: string;
  observacao: string;
}

interface ContatoRead {
  nome: string;
  orgao?: string | null;
  cargo?: string | null;
  categoria: string;
  email?: string | null;
  telefone?: string | null;
  sei?: string | null;
  sei_url?: string | null;
  observacao?: string | null;
}

const VAZIA: Linha = {
  nome: "",
  orgao: "",
  cargo: "",
  categoria: "gabinete_ministro",
  email: "",
  telefone: "",
  sei: "",
  sei_url: "",
  observacao: "",
};

function paraForm(lista: ContatoRead[]): Linha[] {
  return lista.map((c) => ({
    nome: c.nome ?? "",
    orgao: c.orgao ?? "",
    cargo: c.cargo ?? "",
    categoria: c.categoria ?? "outros",
    email: c.email ?? "",
    telefone: c.telefone ?? "",
    sei: c.sei ?? "",
    sei_url: c.sei_url ?? "",
    observacao: c.observacao ?? "",
  }));
}

export default function AdminDiretorioPage() {
  const [linhas, setLinhas] = useState<Linha[] | null>(null);
  const [categorias, setCategorias] = useState<{ chave: string; rotulo: string }[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/admin/contacts/institutional", {});
    if (error) {
      setMsg("Acesso negado — é necessário ser administrador.");
      setLinhas([]);
      return;
    }
    setLinhas(paraForm((data as ContatoRead[]) ?? []));
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  useEffect(() => {
    void api.GET("/api/v1/contacts/institutional/categories").then(({ data }) => {
      if (data) setCategorias(data as { chave: string; rotulo: string }[]);
    });
  }, []);

  function alterar(i: number, campo: keyof Linha, valor: string) {
    setLinhas((atual) => (atual ?? []).map((c, j) => (j === i ? { ...c, [campo]: valor } : c)));
  }

  async function salvar() {
    if (!linhas) return;
    setMsg(null);
    // nome OU órgão basta: parte das linhas é o próprio gabinete, sem pessoa
    if (linhas.some((c) => !c.nome.trim() && !c.orgao.trim())) {
      setMsg("Cada linha precisa de um nome ou de um órgão.");
      return;
    }
    setSalvando(true);
    const { data, error } = await api.PUT("/api/v1/admin/contacts/institutional", {
      body: {
        contatos: linhas.map((c) => ({
          nome: c.nome.trim(),
          orgao: c.orgao.trim() || null,
          cargo: c.cargo.trim() || null,
          categoria: c.categoria,
          email: c.email.trim() || null,
          telefone: c.telefone.trim() || null,
          sei: c.sei.trim() || null,
          sei_url: c.sei_url.trim() || null,
          observacao: c.observacao.trim() || null,
        })),
      },
    });
    setSalvando(false);
    if (error) {
      setMsg("Falha ao salvar o diretório.");
      return;
    }
    setLinhas(paraForm((data as ContatoRead[]) ?? []));
    setMsg("Diretório salvo. A Agenda de contatos já mostra a lista nova.");
  }

  return (
    <>
      <header>
        <h1 className="page-title">Diretório institucional</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Gabinetes de ministros, chefias de gabinete, assessorias parlamentares
          e os SEIs dos protocolos. A lista aparece na Agenda de contatos de
          todos os clientes, só para consulta, e vale na hora — sem redeploy.
        </p>
      </header>

      {msg && <p className="text-sm text-warn">{msg}</p>}

      {linhas === null ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : (
        <section className="flex flex-col gap-3">
          {linhas.length === 0 && (
            <p className="text-sm text-ink-3">
              Diretório vazio — a aba do painel avisa que ainda não foi
              publicado. Adicione a primeira linha abaixo.
            </p>
          )}

          {linhas.map((c, i) => (
            <div key={i} className="card flex flex-col gap-3 p-5">
              <div className="flex flex-wrap gap-3">
                <label className="flex min-w-48 flex-1 flex-col gap-1 text-xs text-ink-3">
                  Órgão
                  <input
                    className="input"
                    value={c.orgao}
                    onChange={(e) => alterar(i, "orgao", e.target.value)}
                    placeholder="Ministério da Saúde"
                  />
                </label>
                <label className="flex min-w-48 flex-1 flex-col gap-1 text-xs text-ink-3">
                  Nome / gabinete
                  <input
                    className="input"
                    value={c.nome}
                    onChange={(e) => alterar(i, "nome", e.target.value)}
                    placeholder="Gabinete do Ministro"
                  />
                </label>
                <label className="flex min-w-40 flex-1 flex-col gap-1 text-xs text-ink-3">
                  Cargo
                  <input
                    className="input"
                    value={c.cargo}
                    onChange={(e) => alterar(i, "cargo", e.target.value)}
                    placeholder="Chefe de Gabinete"
                  />
                </label>
                <label className="flex min-w-44 flex-col gap-1 text-xs text-ink-3">
                  Categoria
                  <select
                    className="input"
                    value={c.categoria}
                    onChange={(e) => alterar(i, "categoria", e.target.value)}
                  >
                    {categorias.map((k) => (
                      <option key={k.chave} value={k.chave}>
                        {k.rotulo}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="flex flex-wrap gap-3">
                <label className="flex min-w-48 flex-1 flex-col gap-1 text-xs text-ink-3">
                  E-mail
                  <input
                    className="input"
                    value={c.email}
                    onChange={(e) => alterar(i, "email", e.target.value)}
                    placeholder="gabinete@orgao.gov.br"
                  />
                </label>
                <label className="flex min-w-44 flex-1 flex-col gap-1 text-xs text-ink-3">
                  Telefone
                  <input
                    className="input"
                    value={c.telefone}
                    onChange={(e) => alterar(i, "telefone", e.target.value)}
                    placeholder="+55 61 3315-2425"
                  />
                </label>
                <label className="flex min-w-44 flex-1 flex-col gap-1 text-xs text-ink-3">
                  Nº do SEI
                  <input
                    className="input"
                    value={c.sei}
                    onChange={(e) => alterar(i, "sei", e.target.value)}
                    placeholder="25000.123456/2026-11"
                  />
                </label>
                <label className="flex min-w-48 flex-1 flex-col gap-1 text-xs text-ink-3">
                  Link do processo (opcional)
                  <input
                    className="input"
                    value={c.sei_url}
                    onChange={(e) => alterar(i, "sei_url", e.target.value)}
                    placeholder="https://sei.orgao.gov.br/..."
                  />
                </label>
              </div>

              <div className="flex flex-wrap items-end gap-3">
                <label className="flex min-w-64 flex-1 flex-col gap-1 text-xs text-ink-3">
                  Observação
                  <input
                    className="input"
                    value={c.observacao}
                    onChange={(e) => alterar(i, "observacao", e.target.value)}
                    placeholder="Atende demandas de emendas de bancada"
                  />
                </label>
                <button
                  type="button"
                  onClick={() =>
                    setLinhas((atual) => (atual ?? []).filter((_, j) => j !== i))
                  }
                  className="btn btn-ghost btn-sm"
                >
                  Remover linha
                </button>
              </div>
            </div>
          ))}

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setLinhas((atual) => [...(atual ?? []), { ...VAZIA }])}
              className="btn btn-ghost"
            >
              + Adicionar contato
            </button>
            <button
              type="button"
              onClick={() => void salvar()}
              disabled={salvando}
              className="btn btn-primary"
            >
              {salvando ? "Salvando…" : "Salvar diretório"}
            </button>
          </div>
        </section>
      )}
    </>
  );
}
