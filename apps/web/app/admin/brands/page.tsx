"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { components } from "@hub/api-client";
import { StatusBadge } from "@/components/StatusBadge";
import { api, mensagemDaFalha } from "@/lib/api/client";

type Marca = components["schemas"]["MarcaRead"];

/** Admin → Marcas (white label, §69): cada marca é uma organização com
 *  subdomínio próprio (marca.<domínio-base>), domínio próprio opcional e a
 *  identidade visual dela. O dono edita o visual pelo painel dele. */
export default function AdminMarcasPage() {
  const router = useRouter();
  const [marcas, setMarcas] = useState<Marca[] | null>(null);
  const [base, setBase] = useState("hubcapture.com.br");
  const [nome, setNome] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTocado, setSlugTocado] = useState(false);
  const [dono, setDono] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(async () => {
    const [m, o] = await Promise.all([
      api.GET("/api/v1/admin/brands"),
      api.GET("/api/v1/brands/options"),
    ]);
    if (m.data) setMarcas(m.data);
    if (o.data) setBase(o.data.dominio_base);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  function sugerirSlug(texto: string): string {
    return texto
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40);
  }

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setEnviando(true);
    try {
      const { data, error } = await api.POST("/api/v1/admin/brands", {
        body: { nome, slug, dono_email: dono || null },
      });
      if (error || !data) {
        setMsg(mensagemDaFalha(error, "Não foi possível criar a marca."));
        return;
      }
      router.push(`/admin/brands/${data.id}`);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl">Marcas (white label)</h1>
        <p className="max-w-2xl text-sm text-ink-2">
          Cada marca veste a plataforma com logo, cores, tipografia e tela de login próprias, num
          endereço dela — <code className="font-mono">marca.{base}</code> ou um domínio próprio
          via CNAME. Quem se cadastra pelo endereço da marca (ou aceita um convite dela) entra
          vinculado a ela, e e-mails, alertas, PDFs e o assistente saem com a identidade dela.
        </p>
      </header>

      <section className="card flex max-w-3xl flex-col gap-4 p-6">
        <h2 className="label-mono">Nova marca</h2>
        <form onSubmit={criar} className="grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Nome</span>
            <input
              required
              minLength={2}
              className="input"
              value={nome}
              placeholder="Gabinete Digital"
              onChange={(e) => {
                setNome(e.target.value);
                if (!slugTocado) setSlug(sugerirSlug(e.target.value));
              }}
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="field-label">Subdomínio</span>
            <input
              required
              minLength={3}
              className="input font-mono"
              value={slug}
              onChange={(e) => {
                setSlugTocado(true);
                setSlug(e.target.value.toLowerCase());
              }}
            />
            <span className="text-xs text-ink-3">
              {slug || "slug"}.{base}
            </span>
          </label>
          <label className="flex flex-col gap-1.5 sm:col-span-2">
            <span className="field-label">E-mail do dono (opcional)</span>
            <input
              type="email"
              className="input"
              value={dono}
              placeholder="responsavel@organizacao.com.br"
              onChange={(e) => setDono(e.target.value)}
            />
            <span className="text-xs text-ink-3">
              A conta precisa existir. O dono edita o visual e convida a equipe pelo menu da conta → Minha marca.
            </span>
          </label>
          <div className="sm:col-span-2">
            <button type="submit" className="btn btn-primary" disabled={enviando}>
              {enviando ? "Criando…" : "Criar marca"}
            </button>
          </div>
        </form>
        {msg && <p className="text-sm text-danger">{msg}</p>}
      </section>

      <section className="card flex max-w-3xl flex-col gap-2 p-6">
        <h2 className="label-mono">Marcas</h2>
        {marcas === null ? (
          <p className="text-sm text-ink-3">Carregando…</p>
        ) : marcas.length === 0 ? (
          <p className="text-sm text-ink-3">Nenhuma marca criada.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-hairline">
            {marcas.map((m) => (
              <li key={m.id}>
                <Link
                  href={`/admin/brands/${m.id}`}
                  className="flex flex-wrap items-center gap-3 py-3 hover:text-ink"
                >
                  <span
                    aria-hidden
                    className="h-6 w-6 shrink-0 rounded-full border border-hairline"
                    style={{ background: m.tema.cores?.acento ?? "var(--color-accent)" }}
                  />
                  <span className="min-w-0 flex-[1_1_14rem]">
                    <span className="block truncate text-sm">{m.nome}</span>
                    <span className="block truncate font-mono text-xs text-ink-3">
                      {m.url.replace("https://", "")} · {m.membros} conta(s)
                    </span>
                  </span>
                  {!m.ativo && <StatusBadge tone="danger">Desativada</StatusBadge>}
                  {m.dominio && m.dominio_status !== "ativo" && (
                    <StatusBadge tone="warning">Domínio pendente</StatusBadge>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
