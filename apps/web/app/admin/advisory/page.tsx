"use client";

import { useCallback, useEffect, useState } from "react";
import { Skeleton } from "@/components/Skeleton";
import { api } from "@/lib/api/client";

interface ContatoForm {
  nome: string;
  telefone: string;
  descricao: string;
}

interface ContatoRead {
  nome: string;
  telefone: string;
  descricao?: string | null;
  whatsapp_url: string;
}

function paraForm(lista: ContatoRead[]): ContatoForm[] {
  return lista.map((c) => ({
    nome: c.nome,
    telefone: c.telefone,
    descricao: c.descricao ?? "",
  }));
}

export default function AdminAssessoriaPage() {
  const [contatos, setContatos] = useState<ContatoForm[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/admin/advisory/contacts", {});
    if (error) {
      setMsg("Acesso negado — é necessário ser administrador.");
      setContatos([]);
      return;
    }
    setContatos(paraForm((data as ContatoRead[]) ?? []));
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  function alterar(i: number, campo: keyof ContatoForm, valor: string) {
    setContatos((atual) =>
      (atual ?? []).map((c, j) => (j === i ? { ...c, [campo]: valor } : c))
    );
  }

  function adicionar() {
    setContatos((atual) => [
      ...(atual ?? []),
      { nome: "", telefone: "", descricao: "" },
    ]);
  }

  function remover(i: number) {
    setContatos((atual) => (atual ?? []).filter((_, j) => j !== i));
  }

  async function salvar() {
    if (!contatos) return;
    setMsg(null);
    const incompleto = contatos.some((c) => !c.nome.trim() || !c.telefone.trim());
    if (incompleto) {
      setMsg("Preencha nome e telefone (com DDD) de todos os contatos.");
      return;
    }
    setSalvando(true);
    const { data, error } = await api.PUT("/api/v1/admin/advisory/contacts", {
      body: {
        contatos: contatos.map((c) => ({
          nome: c.nome.trim(),
          telefone: c.telefone.trim(),
          descricao: c.descricao.trim() || null,
        })),
      },
    });
    setSalvando(false);
    if (error) {
      setMsg("Falha ao salvar — confira os telefones (DDD + número).");
      return;
    }
    setContatos(paraForm((data as ContatoRead[]) ?? []));
    setMsg("Contatos salvos. A aba Assessoria já mostra a lista nova.");
  }

  return (
    <>
      <header>
        <h1 className="page-title">Assessoria</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Contatos exibidos na aba Assessoria do painel — cada um vira um botão
          que abre a conversa no WhatsApp. A mudança vale na hora, sem
          redeploy. O módulo pode ser desligado em Módulos.
        </p>
      </header>

      {msg && <p className="text-sm text-warn">{msg}</p>}

      {contatos === null ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : (
        <section className="flex flex-col gap-3">
          {contatos.map((c, i) => (
            <div key={i} className="card flex flex-wrap items-end gap-3 p-5">
              <label className="flex min-w-40 flex-1 flex-col gap-1 text-xs text-ink-3">
                Nome
                <input
                  className="input"
                  value={c.nome}
                  onChange={(e) => alterar(i, "nome", e.target.value)}
                  placeholder="Nome do assessor"
                />
              </label>
              <label className="flex min-w-44 flex-1 flex-col gap-1 text-xs text-ink-3">
                Telefone (WhatsApp)
                <input
                  className="input"
                  value={c.telefone}
                  onChange={(e) => alterar(i, "telefone", e.target.value)}
                  placeholder="+55 61 98288-1163"
                />
              </label>
              <label className="flex min-w-44 flex-1 flex-col gap-1 text-xs text-ink-3">
                Descrição (opcional)
                <input
                  className="input"
                  value={c.descricao}
                  onChange={(e) => alterar(i, "descricao", e.target.value)}
                  placeholder="Assessoria orçamentária"
                />
              </label>
              <button onClick={() => remover(i)} className="btn btn-ghost">
                Remover
              </button>
            </div>
          ))}

          <div className="flex flex-wrap items-center gap-3">
            <button onClick={adicionar} className="btn btn-ghost">
              + Adicionar contato
            </button>
            <button
              onClick={salvar}
              disabled={salvando}
              className="btn btn-primary"
            >
              {salvando ? "Salvando…" : "Salvar contatos"}
            </button>
          </div>
        </section>
      )}
    </>
  );
}
