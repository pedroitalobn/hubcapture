"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import { SkeletonCards } from "@/components/Skeleton";
import { IconeAcao } from "@/components/icons";

/** Envolve uma lente do painel cujo módulo pode estar desligado no painel admin
 * OU fora do plano do usuário (§39). A API do eixo responde 404 (plataforma) ou
 * 403 (plano); aqui evitamos a tela vazia e explicamos o porquê certo — o menu
 * já esconde o item, isto cobre o acesso direto por URL. */
export function ModuloGate({
  modulo,
  titulo,
  children,
}: {
  modulo: string;
  titulo: string;
  children: React.ReactNode;
}) {
  // null = carregando · "ok" = liberado · "plano" = fora do plano ·
  // "plataforma" = desligado pela administração
  const [estado, setEstado] = useState<"ok" | "plano" | "plataforma" | null>(
    null
  );

  useEffect(() => {
    void (async () => {
      const { data } = await api.GET("/api/v1/profile");
      const perfil = data as
        | { modulos?: string[]; plano?: { modulos?: string[] | null } | null }
        | undefined;
      const efetivos = perfil?.modulos ?? [];
      if (efetivos.includes(modulo)) {
        setEstado("ok");
        return;
      }
      const doPlano = perfil?.plano?.modulos;
      // o plano restringe módulos e este não está na lista → é gate de plano
      setEstado(doPlano != null && !doPlano.includes(modulo) ? "plano" : "plataforma");
    })();
  }, [modulo]);

  if (estado === null) return <SkeletonCards />;
  if (estado === "ok") return <>{children}</>;

  return (
    <div className="card p-8 text-sm">
      <p className="mb-2 text-base tracking-tight">
        {estado === "plano"
          ? `${titulo} não está incluído no seu plano.`
          : `${titulo} está desativado.`}
      </p>
      <p className="mb-5 max-w-md leading-relaxed text-ink-2">
        {estado === "plano"
          ? "Este módulo faz parte de planos superiores. Fale com a administração para fazer o upgrade da sua assinatura."
          : "Este módulo foi desligado pela administração da plataforma. Um administrador pode reativá-lo a qualquer momento."}
      </p>
      <Link href="/panel" className="btn btn-primary">
        <IconeAcao nome="voltar" />
        Voltar ao meu painel
      </Link>
    </div>
  );
}
