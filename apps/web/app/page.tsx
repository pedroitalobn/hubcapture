import Link from "next/link";
import { BrandMark } from "@/components/AuthShell";

const DIMENSOES = [
  { titulo: "Captação", texto: "Propostas e editais abertos para o seu território." },
  { titulo: "Recursos recebidos", texto: "FPM, emendas e repasses, dia a dia." },
  { titulo: "Conformidade fiscal", texto: "CAUC e CAPAG sem surpresa na hora de captar." },
  { titulo: "Obras", texto: "Execução no mapa: SISMOB, SIMEC e CAIXA." },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-6 py-6">
      <header className="flex items-center justify-between">
        <BrandMark />
        <nav className="flex items-center gap-2">
          <Link href="/login" className="btn btn-ghost btn-sm">
            Entrar
          </Link>
          <Link href="/cadastro" className="btn btn-primary btn-sm">
            Criar conta
          </Link>
        </nav>
      </header>

      <section className="flex flex-1 flex-col items-center justify-center py-20 text-center">
        <span className="chip pointer-events-none mb-6">
          <span className="brand-dot" aria-hidden />
          Curadoria por IA + alertas no WhatsApp
        </span>
        <h1 className="text-display max-w-2xl text-5xl leading-[1.05] sm:text-6xl">
          O ciclo do recurso público,{" "}
          <span className="text-brand-deep dark:text-brand">num só painel.</span>
        </h1>
        <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-2">
          Captação, recebimentos, conformidade fiscal e obras do seu território —
          organizados a partir do seu perfil, não de abas por fonte de dados.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Link href="/cadastro" className="btn btn-primary">
            Começar agora
          </Link>
          <Link href="/painel" className="btn btn-ghost">
            Meu painel
          </Link>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 pb-16 sm:grid-cols-2 lg:grid-cols-4">
        {DIMENSOES.map((d) => (
          <div key={d.titulo} className="card card-hover p-5">
            <h2 className="font-semibold tracking-tight">{d.titulo}</h2>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-2">{d.texto}</p>
          </div>
        ))}
      </section>

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline py-6 text-xs text-ink-3">
        <span>© {new Date().getFullYear()} Hub Capture</span>
        <span className="flex gap-4">
          <Link href="/admin/usuarios" className="hover:text-ink">
            Usuários (admin)
          </Link>
          <Link href="/admin/planos" className="hover:text-ink">
            Planos (admin)
          </Link>
          <Link href="/admin/config" className="hover:text-ink">
            Configuração (admin)
          </Link>
        </span>
      </footer>
    </main>
  );
}
