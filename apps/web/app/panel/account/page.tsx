"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/StatusBadge";
import { api, atualizarPerfil, meProfile, zerarPerfil } from "@/lib/api/client";
import { limparTerritorioSalvo } from "@/lib/territorio";

interface Membro {
  convite_id: string;
  email: string;
  papel?: string | null;
  status: string;
  nome?: string | null;
}

interface PlanoDoPerfil {
  nome?: string | null;
  membros_max?: number | null;
}

/** Palavra que o usuário digita para liberar a zeragem — clique só não basta. */
const CONFIRMACAO = "ZERAR";

export default function ContaPage() {
  const [nome, setNome] = useState("");
  const [telefone, setTelefone] = useState("");
  const [optin, setOptin] = useState(false);
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [confirmacao, setConfirmacao] = useState("");
  const [zerando, setZerando] = useState(false);
  const [erroZerar, setErroZerar] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const me = (await meProfile()) as {
          nome?: string | null;
          telefone_wpp?: string | null;
          optin_wpp?: boolean;
          email: string;
        };
        setNome(me.nome ?? "");
        setTelefone(me.telefone_wpp ?? "");
        setOptin(Boolean(me.optin_wpp));
        setEmail(me.email);
      } catch {
        /* layout já trata sessão */
      }
    })();
  }, []);

  async function salvarPerfil(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setSalvando(true);
    try {
      await atualizarPerfil({
        nome,
        telefone_wpp: telefone,
        optin_wpp: optin,
      });
      setMsg("Perfil atualizado.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Erro ao salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function trocarSenha(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (senha.length < 8) {
      setMsg("A senha precisa ter ao menos 8 caracteres.");
      return;
    }
    setSalvando(true);
    try {
      await atualizarPerfil({ password: senha });
      setSenha("");
      setMsg("Senha alterada.");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Erro ao alterar senha");
    } finally {
      setSalvando(false);
    }
  }

  async function zerar() {
    setErroZerar(null);
    setZerando(true);
    try {
      await zerarPerfil();
      // o recorte salvo aponta para um território que não existe mais
      limparTerritorioSalvo();
      // recarga dura: perfil, menu e caches de tela nascem de novo no onboarding
      window.location.href = "/onboarding";
    } catch (err) {
      setErroZerar(err instanceof Error ? err.message : "Erro ao zerar o perfil");
      setZerando(false);
    }
  }

  return (
    <>
      <header>
        <h1 className="page-title">Minha conta</h1>
        <p className="mt-1 text-sm text-ink-2">{email}</p>
      </header>

      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      <form onSubmit={salvarPerfil} className="card flex max-w-md flex-col gap-4 p-6">
        <h2 className="label-mono">
          Perfil
        </h2>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Nome</span>
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            className="input"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Telefone (WhatsApp)</span>
          <input
            value={telefone}
            onChange={(e) => setTelefone(e.target.value)}
            placeholder="+5511999999999"
            className="input"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            checked={optin}
            onChange={(e) => setOptin(e.target.checked)}
            className="accent-brand"
          />
          Receber alertas por WhatsApp
        </label>
        <button type="submit" disabled={salvando} className="btn btn-primary self-start">
          Salvar perfil
        </button>
      </form>

      <form onSubmit={trocarSenha} className="card flex max-w-md flex-col gap-4 p-6">
        <h2 className="label-mono">
          Trocar senha
        </h2>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Nova senha</span>
          <input
            type="password"
            minLength={8}
            value={senha}
            onChange={(e) => setSenha(e.target.value)}
            className="input"
          />
        </label>
        <button
          type="submit"
          disabled={salvando || !senha}
          className="btn btn-primary self-start"
        >
          Alterar senha
        </button>
      </form>

      <MembrosDaConta />

      <section className="card flex max-w-md flex-col gap-4 border-danger/40 p-6">
        <h2 className="label-mono text-danger">Zona de perigo</h2>
        <div className="flex flex-col gap-2 text-sm text-ink-2">
          <p>
            <strong className="text-ink">Zerar perfil</strong> devolve a conta ao
            estado anterior ao onboarding: você escolhe município, áreas e fontes
            de novo, e os dados do território voltam a ser coletados do zero.
          </p>
          <p>
            Apaga <strong>todos os municípios</strong> que você acompanha (inclusive
            se for mais de um), suas áreas e fontes, e a curadoria: favoritos,
            pastas, monitoramentos e alertas. As propostas do seu território saem
            do painel e serão recoletadas na próxima busca.
          </p>
          <p>
            Continuam intactos: seu login e dados de conta, e a agenda de contatos.
            Zerar o perfil não exclui a conta. <strong>Não dá para desfazer.</strong>
          </p>
        </div>
        <label className="flex flex-col gap-1.5">
          <span className="field-label">
            Digite {CONFIRMACAO} para liberar o botão
          </span>
          <input
            value={confirmacao}
            onChange={(e) => setConfirmacao(e.target.value)}
            placeholder={CONFIRMACAO}
            className="input"
          />
        </label>
        {erroZerar && <p className="text-sm text-danger">{erroZerar}</p>}
        <button
          type="button"
          onClick={zerar}
          disabled={zerando || confirmacao.trim().toUpperCase() !== CONFIRMACAO}
          className="btn self-start border border-danger/50 text-danger hover:bg-danger/10"
        >
          {zerando ? "Zerando…" : "Zerar perfil"}
        </button>
      </section>
    </>
  );
}

/** Membros da conta: convites do próprio usuário, limitados pelo plano (§39).
 * O convidado aceita pelo link (/accept-invite) e entra com o plano da conta. */
function MembrosDaConta() {
  const [membros, setMembros] = useState<Membro[] | null>(null);
  const [plano, setPlano] = useState<PlanoDoPerfil | null>(null);
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(async () => {
    const [membrosRes, perfilRes] = await Promise.all([
      api.GET("/api/v1/account/members", {}),
      api.GET("/api/v1/profile"),
    ]);
    if (!membrosRes.error) setMembros((membrosRes.data as Membro[]) ?? []);
    const p = (perfilRes.data as { plano?: PlanoDoPerfil | null } | undefined)?.plano;
    setPlano(p ?? null);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const maximo = plano?.membros_max ?? null;
  const vivos = (membros ?? []).filter((m) => m.status !== "expirado").length;
  const esgotado = maximo != null && vivos >= maximo;

  async function convidar(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setEnviando(true);
    const { error } = await api.POST("/api/v1/account/members/invites", {
      body: { email, papel: "equipe", expires_em_dias: 7 },
    });
    setEnviando(false);
    if (error) {
      const detail = (error as { detail?: unknown })?.detail;
      setMsg(
        typeof detail === "string" && detail.startsWith("LIMITE_PLANO_MEMBROS")
          ? "Seu plano não permite mais membros — fale com a administração para fazer upgrade."
          : "Não foi possível enviar o convite."
      );
      return;
    }
    setEmail("");
    setMsg("Convite criado — o link foi enviado por e-mail.");
    await carregar();
  }

  async function revogar(m: Membro) {
    await api.DELETE("/api/v1/account/members/invites/{convite_id}", {
      params: { path: { convite_id: m.convite_id } },
    });
    await carregar();
  }

  if (maximo === 0 && vivos === 0) return null; // plano sem membros: seção some

  return (
    <section className="card flex max-w-md flex-col gap-4 p-6">
      <h2 className="label-mono">Membros da conta</h2>
      <p className="text-xs leading-relaxed text-ink-3">
        Convide sua equipe para acompanhar o mesmo território.
        {maximo != null &&
          ` Seu plano${plano?.nome ? ` (${plano.nome})` : ""} permite até ${maximo} membro(s) — ${vivos} em uso.`}
      </p>

      <form onSubmit={convidar} className="flex items-end gap-2">
        <label className="flex flex-1 flex-col gap-1.5">
          <span className="field-label">E-mail do membro</span>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input"
            disabled={esgotado}
          />
        </label>
        <button
          type="submit"
          disabled={enviando || esgotado}
          className="btn btn-primary"
        >
          Convidar
        </button>
      </form>
      {msg && <p className="text-sm text-ink-2">{msg}</p>}

      <ul className="flex flex-col divide-y divide-hairline">
        {(membros ?? []).map((m) => (
          <li key={m.convite_id} className="flex items-center gap-3 py-2.5 text-sm">
            <div className="min-w-0 flex-1">
              <p className="truncate">{m.nome || m.email}</p>
              {m.nome && <p className="truncate text-xs text-ink-3">{m.email}</p>}
            </div>
            <StatusBadge
              tone={
                m.status === "aceito"
                  ? "success"
                  : m.status === "pendente"
                    ? "neutral"
                    : "warning"
              }
            >
              {m.status}
            </StatusBadge>
            {m.status === "pendente" && (
              <button
                onClick={() => revogar(m)}
                className="font-mono text-[11px] uppercase tracking-[0.04em] text-ink-3 hover:text-ink"
              >
                Revogar
              </button>
            )}
          </li>
        ))}
        {membros !== null && membros.length === 0 && (
          <li className="py-2.5 text-sm text-ink-3">Nenhum membro convidado ainda.</li>
        )}
      </ul>
    </section>
  );
}
