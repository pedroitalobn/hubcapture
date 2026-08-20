"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthShell } from "@/components/AuthShell";
import { api, entrarDemo, login, uiInfo } from "@/lib/api/client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  // Acesso demo (apresentação/vendas): o botão só aparece quando a plataforma
  // diz que a conta demo está de pé (flag pública em GET /ui).
  const [demoDisponivel, setDemoDisponivel] = useState(false);
  const [entrandoDemo, setEntrandoDemo] = useState(false);

  useEffect(() => {
    void uiInfo().then((info) => setDemoDisponivel(Boolean(info?.demo)));
  }, []);

  async function verDemonstracao() {
    setErro(null);
    setEntrandoDemo(true);
    try {
      await entrarDemo();
      router.push("/panel");
    } catch (err) {
      setErro(
        err instanceof Error ? err.message : "A demonstração está indisponível",
      );
    } finally {
      setEntrandoDemo(false);
    }
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErro(null);
    setCarregando(true);
    try {
      await login(email, senha);
      // Sem território configurado → a porta de entrada é o onboarding
      // conversacional (o perfil é o ponto de partida da navegação).
      const { data } = await api.GET("/api/v1/profile");
      const temTerritorio = ((data?.municipios as unknown[]) ?? []).length > 0;
      router.push(temTerritorio ? "/panel" : "/onboarding");
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Erro ao entrar");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <AuthShell
      image
      title="Bem-vindo de volta"
      subtitle="Entre para acompanhar o seu território."
      footer={
        <div className="flex items-center justify-between">
          <span>
            Novo por aqui?{" "}
            <Link href="/signup" className="text-ink underline hover:no-underline">
              Criar conta
            </Link>
          </span>
          <Link href="/forgot-password" className="hover:text-ink">
            Esqueci a senha
          </Link>
        </div>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">E-mail</span>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input"
            placeholder="voce@exemplo.gov.br"
          />
        </label>
        {/* Campo de senha com alternância de visibilidade. Usa htmlFor em vez de
            envolver o input num <label>, como no campo de e-mail acima: com o
            botão dentro, o clique nele seria reencaminhado ao input pela
            ativação do label (controle interativo aninhado em label é
            anti-padrão de acessibilidade). */}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="senha" className="field-label">
            Senha
          </label>
          <div className="relative">
            <input
              id="senha"
              type={mostrarSenha ? "text" : "password"}
              required
              autoComplete="current-password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              // pr-11 reserva a área do botão pra senha longa não passar por baixo dele
              className="input pr-11"
              placeholder="••••••••"
            />
            <button
              type="button" // sem isto o botão herdaria type=submit e enviaria o form
              onClick={() => setMostrarSenha((v) => !v)}
              // O rótulo anuncia a AÇÃO e aria-pressed o estado atual, pra
              // leitor de tela não depender do ícone.
              aria-label={mostrarSenha ? "Ocultar senha" : "Mostrar senha"}
              aria-pressed={mostrarSenha}
              title={mostrarSenha ? "Ocultar senha" : "Mostrar senha"}
              className="absolute inset-y-0 right-0 flex items-center rounded-r-lg px-3 text-ink-3 transition-colors hover:text-ink focus-visible:outline-none focus-visible:text-ink"
            >
              <svg
                width="17"
                height="17"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                {mostrarSenha ? (
                  <>
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </>
                ) : (
                  <>
                    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z" />
                    <circle cx="12" cy="12" r="3" />
                  </>
                )}
              </svg>
            </button>
          </div>
        </div>
        {erro && <p className="text-sm text-danger">{erro}</p>}
        <button type="submit" disabled={carregando} className="btn btn-primary mt-2">
          {carregando ? "Entrando…" : "Entrar"}
        </button>
        {demoDisponivel && (
          <button
            type="button"
            onClick={verDemonstracao}
            disabled={entrandoDemo || carregando}
            className="btn btn-ghost"
          >
            {entrandoDemo ? "Preparando a demonstração…" : "Ver demonstração"}
          </button>
        )}
      </form>
    </AuthShell>
  );
}
