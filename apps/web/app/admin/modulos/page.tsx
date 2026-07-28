"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, getToken } from "@/lib/api/client";

interface Modulo {
  chave: string;
  label: string;
  descricao?: string | null;
  padrao: boolean;
  ativo: boolean;
}

export default function AdminModulosPage() {
  const [modulos, setModulos] = useState<Modulo[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [salvando, setSalvando] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/admin/modulos", {});
    if (error) {
      setMsg("Acesso negado — é necessário ser administrador.");
      return;
    }
    setModulos((data as Modulo[]) ?? []);
  }, []);

  useEffect(() => {
    if (!getToken()) {
      setMsg("Faça login como administrador.");
      return;
    }
    void carregar();
  }, [carregar]);

  async function alternar(m: Modulo) {
    setMsg(null);
    setSalvando(m.chave);
    const { data, error } = await api.PUT("/api/v1/admin/modulos", {
      body: { chave: m.chave, ativo: !m.ativo },
    });
    setSalvando(null);
    if (error) {
      setMsg("Falha ao salvar (é necessário ser administrador).");
      return;
    }
    setModulos((data as Modulo[]) ?? []);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-6 py-8">
      <header>
        <h1 className="text-2xl font-bold">Módulos da plataforma</h1>
        <p className="text-sm text-gray-500">
          Ative ou desative os eixos do painel em runtime. Módulo desativado some
          do menu e da visão geral, e a API do eixo responde 404.
        </p>
      </header>
      {msg && <p className="text-sm text-amber-600">{msg}</p>}

      <section className="flex flex-col gap-3">
        {modulos.map((m) => (
          <div
            key={m.chave}
            className="flex flex-wrap items-center gap-3 rounded-md border border-gray-200 p-3 dark:border-gray-800"
          >
            <div className="min-w-40 flex-1">
              <div className="text-sm font-medium">{m.label}</div>
              <div className="text-xs text-gray-500">
                {m.chave}
                {m.descricao ? ` · ${m.descricao}` : ""}
              </div>
            </div>
            <StatusBadge tone={m.ativo ? "success" : "neutral"}>
              {m.ativo ? "ativo" : "desativado"}
            </StatusBadge>
            <button
              onClick={() => alternar(m)}
              disabled={salvando === m.chave}
              className={`rounded-md px-3 py-1.5 text-sm disabled:opacity-50 ${
                m.ativo
                  ? "border border-gray-300 text-gray-700 dark:border-gray-700 dark:text-gray-300"
                  : "bg-brand text-brand-fg"
              }`}
            >
              {m.ativo ? "Desativar" : "Ativar"}
            </button>
          </div>
        ))}
      </section>
    </main>
  );
}
