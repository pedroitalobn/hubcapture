"use client";

import { useCallback, useEffect, useState } from "react";
import { Skeleton } from "@/components/Skeleton";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";

interface Modulo {
  chave: string;
  label: string;
  descricao?: string | null;
  padrao: boolean;
  ativo: boolean;
}

export default function AdminModulosPage() {
  const [modulos, setModulos] = useState<Modulo[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [salvando, setSalvando] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    const { data, error } = await api.GET("/api/v1/admin/modules", {});
    if (error) {
      setMsg("Acesso negado — é necessário ser administrador.");
      setModulos([]);
      return;
    }
    setModulos((data as Modulo[]) ?? []);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function alternar(m: Modulo) {
    setMsg(null);
    setSalvando(m.chave);
    const { data, error } = await api.PUT("/api/v1/admin/modules", {
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
    <>
      <header>
        <h1 className="page-title">Módulos</h1>
        <p className="mt-1 max-w-2xl text-sm text-ink-2">
          Liga e desliga cada eixo do produto em runtime. Módulo desativado some
          do menu e da visão geral do painel, e a API do eixo passa a responder
          404 — sem redeploy e sem perder nada do que já foi implementado.
        </p>
      </header>

      {msg && <p className="text-sm text-warn">{msg}</p>}

      {modulos === null ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      ) : (
        <section className="stagger flex flex-col gap-3">
          {modulos.map((m) => (
            <div
              key={m.chave}
              className="card flex flex-wrap items-center gap-4 p-5"
            >
              <div className="min-w-48 flex-1">
                <div className="flex items-center gap-2 text-sm tracking-tight">
                  {m.label}
                  <StatusBadge tone={m.ativo ? "success" : "neutral"}>
                    {m.ativo ? "ativo" : "desativado"}
                  </StatusBadge>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-ink-3">
                  {m.descricao}
                </p>
              </div>
              <button
                onClick={() => alternar(m)}
                disabled={salvando === m.chave}
                className={`btn ${m.ativo ? "btn-ghost" : "btn-primary"}`}
              >
                {salvando === m.chave
                  ? "Salvando…"
                  : m.ativo
                    ? "Desativar"
                    : "Ativar"}
              </button>
            </div>
          ))}
        </section>
      )}
    </>
  );
}
