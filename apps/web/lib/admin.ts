"use client";

/**
 * "Quem está olhando é da administração?" — a pergunta que decide se um texto
 * de diagnóstico (rota do connector, exceção, parâmetro a calibrar) pode
 * aparecer na tela.
 *
 * Falha de fonte tem DUAS leituras: para o gestor é "não consegui consultar
 * agora"; para quem calibra é a mensagem crua do connector. Misturar as duas
 * põe plumbing de integração na página que o gestor encaminha — foi o que o
 * "Detalhe técnico (para a administração)" fez ao aparecer para todo mundo.
 *
 * A resposta é a MESMA enquanto a sessão for a mesma, então a promessa é
 * memoizada em módulo COM A CHAVE DO TOKEN: N seções na mesma página fazem UMA
 * chamada a /users/me, a navegação seguinte não repete, e trocar de conta no
 * mesmo navegador não herda o "sim" do usuário anterior (memoizar sem chave
 * mostraria o diagnóstico ao gestor que logasse depois de um admin).
 */

import { useEffect, useState } from "react";
import { api, getToken } from "@/lib/api/client";

let cache: { token: string | null; resposta: Promise<boolean> } | null = null;

async function consultar(): Promise<boolean> {
  if (!getToken()) return false;
  try {
    const me = await api.GET("/api/v1/users/me");
    return Boolean((me.data as { is_superuser?: boolean } | undefined)?.is_superuser);
  } catch {
    // sem resposta, o padrão é o mais restrito: esconde o diagnóstico
    return false;
  }
}

export function ehAdmin(): Promise<boolean> {
  const token = getToken();
  if (!cache || cache.token !== token) cache = { token, resposta: consultar() };
  return cache.resposta;
}

/** `false` até a resposta chegar — nunca pisca o diagnóstico para o gestor. */
export function useEhAdmin(): boolean {
  const [admin, setAdmin] = useState(false);
  useEffect(() => {
    let vivo = true;
    void ehAdmin().then((v) => {
      if (vivo) setAdmin(v);
    });
    return () => {
      vivo = false;
    };
  }, []);
  return admin;
}
