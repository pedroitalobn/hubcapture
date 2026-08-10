import {
  ArrowRight,
  HandCoins,
  HardHat,
  Landmark,
  LogIn,
  Settings,
  ShieldCheck,
  Target,
  Users,
  Wallet,
} from "lucide-react";
import Link from "next/link";

const CICLO = [
  {
    icon: Target,
    titulo: "Captação",
    texto: "Propostas e editais abertos para o seu município, curados por IA.",
    chip: "bg-brand-50 text-brand-700 ring-brand-100 dark:bg-brand-900/30 dark:text-brand-300 dark:ring-brand-900/50",
  },
  {
    icon: HandCoins,
    titulo: "Recursos recebidos",
    texto: "FPM, emendas, FNS e FNDE — cada repasse que entrou no caixa.",
    chip: "bg-green-50 text-green-700 ring-green-100 dark:bg-green-900/30 dark:text-green-300 dark:ring-green-900/50",
  },
  {
    icon: ShieldCheck,
    titulo: "Conformidade fiscal",
    texto: "Requisitos CAUC e CAPAG monitorados direto do Tesouro.",
    chip: "bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-900/50",
  },
  {
    icon: HardHat,
    titulo: "Obras",
    texto: "Execução física e financeira via SISMOB, SIMEC e CAIXA.",
    chip: "bg-purple-50 text-purple-700 ring-purple-100 dark:bg-purple-900/30 dark:text-purple-300 dark:ring-purple-900/50",
  },
];

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-10 px-6 py-16">
      <div className="flex flex-col gap-5 animate-fade-up">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-600 to-brand-800 text-white shadow-md">
          <Landmark className="h-7 w-7" aria-hidden />
        </span>
        <div>
          <h1 className="text-4xl font-bold tracking-tight">Hub Capture</h1>
          <p className="mt-3 max-w-xl text-lg text-gray-600 dark:text-gray-400">
            Seu território, do começo ao fim do ciclo do recurso público —
            organizado a partir do seu perfil, não de abas por fonte de dados.
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/login"
            className="inline-flex items-center gap-2 rounded-lg bg-brand px-5 py-2.5 text-sm font-medium text-brand-fg shadow-sm transition-all duration-150 hover:bg-brand-800 active:scale-[0.98]"
          >
            <LogIn className="h-4 w-4" aria-hidden />
            Entrar
          </Link>
          <Link
            href="/cadastro"
            className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-5 py-2.5 text-sm font-medium transition-all duration-150 hover:border-gray-400 hover:bg-gray-50 active:scale-[0.98] dark:border-gray-700 dark:bg-gray-900 dark:hover:bg-gray-800"
          >
            Criar conta
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
          <Link
            href="/painel"
            className="inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
          >
            Meu painel
          </Link>
        </div>
      </div>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 stagger">
        {CICLO.map((c) => {
          const Icon = c.icon;
          return (
            <div
              key={c.titulo}
              className="group rounded-2xl border border-gray-200 bg-white p-5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card-hover dark:border-gray-800 dark:bg-gray-900"
            >
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-xl ring-1 transition-transform duration-200 group-hover:scale-110 ${c.chip}`}
              >
                <Icon className="h-5 w-5" aria-hidden />
              </span>
              <h2 className="mt-3 font-semibold">{c.titulo}</h2>
              <p className="mt-1 text-sm text-gray-500">{c.texto}</p>
            </div>
          );
        })}
      </section>

      <footer className="flex flex-wrap items-center gap-4 border-t border-gray-200 pt-6 text-sm text-gray-500 dark:border-gray-800 animate-fade-in">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
          Administração
        </span>
        <Link
          href="/admin/usuarios"
          className="inline-flex items-center gap-1.5 transition-colors hover:text-brand-700 dark:hover:text-brand-400"
        >
          <Users className="h-3.5 w-3.5" aria-hidden />
          Usuários
        </Link>
        <Link
          href="/admin/planos"
          className="inline-flex items-center gap-1.5 transition-colors hover:text-brand-700 dark:hover:text-brand-400"
        >
          <Wallet className="h-3.5 w-3.5" aria-hidden />
          Planos
        </Link>
        <Link
          href="/admin/config"
          className="inline-flex items-center gap-1.5 transition-colors hover:text-brand-700 dark:hover:text-brand-400"
        >
          <Settings className="h-3.5 w-3.5" aria-hidden />
          Configuração
        </Link>
      </footer>
    </main>
  );
}
