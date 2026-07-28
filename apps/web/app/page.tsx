"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { getToken } from "@/lib/api/client";

/** Sem landing page: a raiz manda direto para o login (ou painel, se já logado). */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getToken() ? "/painel" : "/login");
  }, [router]);

  return null;
}
