import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6">
      <h1 className="text-3xl font-bold">Hub Capture</h1>
      <p className="text-gray-600 dark:text-gray-400">
        Concentrador de propostas, editais e repasses do governo brasileiro.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link href="/login" className="rounded-md bg-brand px-4 py-2 text-brand-fg">
          Entrar
        </Link>
        <Link
          href="/onboarding"
          className="rounded-md border border-gray-300 px-4 py-2 dark:border-gray-700"
        >
          Configurar
        </Link>
        <Link
          href="/painel/repasses"
          className="rounded-md border border-gray-300 px-4 py-2 dark:border-gray-700"
        >
          Recursos recebidos
        </Link>
        <Link
          href="/painel"
          className="rounded-md border border-gray-300 px-4 py-2 dark:border-gray-700"
        >
          Propostas
        </Link>
        <Link
          href="/admin/planos"
          className="rounded-md border border-gray-300 px-4 py-2 dark:border-gray-700"
        >
          Planos (admin)
        </Link>
      </div>
    </main>
  );
}
