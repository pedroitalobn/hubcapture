"use client";

import { useEffect, useRef, useState } from "react";
import { Aviso, Button, Input } from "./ui";

/**
 * Busca sob demanda numa fonte oficial por código IBGE. Estava duplicada em
 * captação, repasses, obras e conformidade, cada uma com um texto de erro
 * diferente para a mesma situação.
 */
export function SyncForm({
  rotulo,
  botao,
  erroPadrao,
  ibgeSugerido,
  onSync,
}: {
  rotulo: string;
  botao: string;
  erroPadrao: string;
  /** Pré-preenche com o município do perfil — o caso comum é sincronizar o próprio. */
  ibgeSugerido?: string | null;
  onSync: (ibge: string) => Promise<{ ok: boolean; mensagem?: string }>;
}) {
  const [ibge, setIbge] = useState(ibgeSugerido ?? "");
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState<{ tom: "ok" | "erro"; texto: string } | null>(null);
  const tocado = useRef(false);

  // O perfil chega depois da montagem, então o valor inicial do state não basta.
  // Só preenche enquanto o usuário não tiver digitado nada.
  useEffect(() => {
    if (ibgeSugerido && !tocado.current) setIbge(ibgeSugerido);
  }, [ibgeSugerido]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    setAviso(null);
    setOcupado(true);
    try {
      const r = await onSync(ibge);
      setAviso({
        tom: r.ok ? "ok" : "erro",
        texto: r.mensagem ?? (r.ok ? "Sincronização concluída." : erroPadrao),
      });
    } catch {
      setAviso({ tom: "erro", texto: erroPadrao });
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <form onSubmit={enviar} className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-ink">{rotulo}</span>
          <Input
            value={ibge}
            onChange={(e) => {
              tocado.current = true;
              setIbge(e.target.value.replace(/\D/g, "").slice(0, 7));
            }}
            placeholder="3550308"
            inputMode="numeric"
            aria-label={rotulo}
            className="w-40"
          />
        </label>
        <Button type="submit" disabled={ocupado || ibge.length !== 7}>
          {ocupado ? "Buscando…" : botao}
        </Button>
      </form>
      {aviso && <Aviso tom={aviso.tom}>{aviso.texto}</Aviso>}
    </div>
  );
}
