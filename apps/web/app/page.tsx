import Link from "next/link";

const CICLO = [
  {
    titulo: "Captação",
    desc: "Propostas e editais das plataformas federais, curados por IA.",
    grad: "from-indigo-400 to-sky-400",
  },
  {
    titulo: "Recursos recebidos",
    desc: "FPM, emendas e repasses fundo a fundo, dia a dia.",
    grad: "from-emerald-400 to-teal-300",
  },
  {
    titulo: "Conformidade fiscal",
    desc: "CAUC e CAPAG sob controle antes que travem convênios.",
    grad: "from-amber-400 to-orange-300",
  },
  {
    titulo: "Obras",
    desc: "Execução física acompanhada do repasse à entrega.",
    grad: "from-fuchsia-400 to-violet-400",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col justify-center gap-12 px-6 py-16">
      <section className="flex flex-col items-start gap-6">
        <span className="chip animate-fade-up px-3 py-1 text-xs font-medium uppercase tracking-widest text-brand">
          <span className="glow-dot text-brand" />
          Hub Capture
        </span>
        <h1 className="animate-fade-up stagger-1 max-w-3xl text-4xl font-bold leading-tight tracking-tight sm:text-6xl">
          <span className="text-gradient">O ciclo do recurso público,</span>{" "}
          <span className="text-gradient-brand">num só painel.</span>
        </h1>
        <p className="animate-fade-up stagger-2 max-w-2xl text-lg text-gray-400">
          Seu território, do começo ao fim: captação, recursos recebidos,
          conformidade fiscal e obras — organizados a partir do seu perfil, não
          de abas por fonte de dados.
        </p>
        <div className="animate-fade-up stagger-3 flex flex-wrap gap-3">
          <Link href="/login" className="btn-primary px-6 py-2.5">
            Entrar
          </Link>
          <Link href="/cadastro" className="btn-ghost px-6 py-2.5">
            Criar conta
          </Link>
          <Link href="/onboarding" className="btn-ghost px-6 py-2.5">
            Configurar meu perfil
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {CICLO.map((c, i) => (
          <div
            key={c.titulo}
            className={`glass-card glass-hover animate-fade-up stagger-${i + 2} p-6`}
          >
            <div
              className={`mb-3 h-1 w-10 rounded-full bg-gradient-to-r ${c.grad}`}
            />
            <h2 className="font-semibold">{c.titulo}</h2>
            <p className="mt-1 text-sm text-gray-400">{c.desc}</p>
          </div>
        ))}
      </section>

      <footer className="flex flex-wrap gap-4 text-xs text-gray-500">
        <Link href="/admin/usuarios" className="transition hover:text-gray-300">
          Usuários (admin)
        </Link>
        <Link href="/admin/planos" className="transition hover:text-gray-300">
          Planos (admin)
        </Link>
        <Link href="/admin/config" className="transition hover:text-gray-300">
          Configuração (admin)
        </Link>
      </footer>
    </main>
  );
}
