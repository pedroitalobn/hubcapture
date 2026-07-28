"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { SkeletonCards } from "@/components/Skeleton";

/** Envolve uma lente do painel cujo módulo pode estar desligado no painel admin.
 * A API do eixo responde 404 quando desativado; aqui evitamos a tela vazia e
 * explicamos o porquê (o menu já esconde o item — isto cobre o acesso direto). */
export function ModuloGate({
  modulo,
  titulo,
  children,
}: {
  modulo: string;
  titulo: string;
  children: React.ReactNode;
}) {
  const [ativo, setAtivo] = useState<boolean | null>(null);

  useEffect(() => {
    void (async () => {
      const { data } = await api.GET("/api/v1/perfil");
      const modulos = (data as { modulos?: string[] } | undefined)?.modulos ?? [];
      setAtivo(modulos.includes(modulo));
    })();
  }, [modulo]);

  if (ativo === null) return <SkeletonCards />;
  if (ativo) return <>{children}</>;

  return (
    <div className="rounded-lg border border-dashed border-gray-300 p-6 text-sm dark:border-gray-700">
      <p className="mb-2 font-medium">{titulo} está desativado.</p>
      <p className="mb-3 text-gray-500">
        Este módulo foi desligado pela administração da plataforma. Um
        administrador pode reativá-lo a qualquer momento.
      </p>
      <Link href="/painel" className="text-brand underline">
        Voltar ao meu painel
      </Link>
    </div>
  );
}
