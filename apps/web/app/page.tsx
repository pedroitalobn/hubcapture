import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6">
      <h1 className="text-3xl font-bold">Hub Capture</h1>
      <p className="text-gray-600 dark:text-gray-400">
        Seu território, do começo ao fim do ciclo do recurso público: captação e
        recursos recebidos hoje, conformidade fiscal e obras a seguir —
        organizados a partir do seu perfil, não de abas por fonte de dados.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link href="/login" className="rounded-md bg-brand px-4 py-2 text-brand-fg">
          Entrar
        </Link>
        <Link
          href="/cadastro"
          className="rounded-md border border-gray-300 px-4 py-2 dark:border-gray-700"
        >
          Criar conta
        </Link>
        <Link
          href="/onboarding"
          className="rounded-md border border-gray-300 px-4 py-2 dark:border-gray-700"
        >
          Configurar meu perfil
        </Link>
        <Link
          href="/painel"
          className="rounded-md border border-gray-300 px-4 py-2 dark:border-gray-700"
        >
          Meu painel
        </Link>
      </div>
      <div className="flex flex-wrap gap-4 text-sm text-gray-500">
        <Link href="/admin/usuarios" className="underline">
          Usuários (admin)
        </Link>
        <Link href="/admin/planos" className="underline">
          Planos (admin)
        </Link>
        <Link href="/admin/config" className="underline">
          Configuração (admin)
        </Link>
        <Link href="/admin/modulos" className="underline">
          Módulos (admin)
        </Link>
      </div>
    </main>
  );
}
