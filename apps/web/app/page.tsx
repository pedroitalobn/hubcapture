import Link from "next/link";

const CICLO = [
  { titulo: "Captação", texto: "Propostas e editais abertos, com pendências e prazos à vista." },
  { titulo: "Recursos recebidos", texto: "O que já entrou no caixa, por fonte e por dia." },
  { titulo: "Conformidade fiscal", texto: "CAUC e CAPAG — o que trava a assinatura de um convênio." },
  { titulo: "Obras", texto: "Execução no território, do planejamento à entrega." },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-3xl flex-col justify-center gap-8 px-6 py-16">
      <div className="flex flex-col gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-muted">
          Hub Capture
        </span>
        <h1 className="max-w-2xl text-3xl font-bold tracking-tight text-ink text-balance">
          Seu território, do começo ao fim do ciclo do recurso público.
        </h1>
        <p className="max-w-prose text-ink-2">
          Captação, recursos recebidos, conformidade fiscal e obras — organizados a partir do
          seu perfil, não de abas por fonte de dados.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Link
          href="/login"
          className="rounded-md border border-brand bg-brand px-4 py-2 text-sm font-medium text-brand-fg transition hover:bg-brand-700"
        >
          Entrar
        </Link>
        <Link
          href="/cadastro"
          className="rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-ink-2 transition hover:bg-surface hover:text-ink"
        >
          Criar conta
        </Link>
        <Link
          href="/painel"
          className="rounded-md border border-line-strong px-4 py-2 text-sm font-medium text-ink-2 transition hover:bg-surface hover:text-ink"
        >
          Meu painel
        </Link>
      </div>

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {CICLO.map((c) => (
          <li key={c.titulo} className="rounded-xl border border-line bg-bg p-4 shadow-card">
            <p className="font-semibold text-ink">{c.titulo}</p>
            <p className="mt-0.5 text-sm text-muted">{c.texto}</p>
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap gap-4 border-t border-line pt-5 text-sm text-muted">
        <Link href="/admin/usuarios" className="underline underline-offset-2 hover:text-ink">
          Usuários (admin)
        </Link>
        <Link href="/admin/planos" className="underline underline-offset-2 hover:text-ink">
          Planos (admin)
        </Link>
        <Link href="/admin/config" className="underline underline-offset-2 hover:text-ink">
          Configuração (admin)
        </Link>
      </div>
    </main>
  );
}
