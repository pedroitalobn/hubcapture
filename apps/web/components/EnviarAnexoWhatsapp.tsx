"use client";

/**
 * Envio de anexo pelo WhatsApp com a escolha do formato — a mesma que o app do
 * WhatsApp oferece ao anexar.
 *
 * A escolha só aparece quando o arquivo é uma FOTO: PDF, planilha e afins não
 * têm o que escolher (viram documento e pronto), e mostrar um botão inerte
 * sugeriria que dá para mandá-los como imagem. Quem anexa foto decide entre
 * preservar o arquivo original (documento) ou vê-la na conversa (imagem).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Modal } from "@/components/Modal";
import { enviarAnexoWhatsapp, type EnvioWhatsappResultado } from "@/lib/api/client";

type Formato = "imagem" | "documento";

/** Tipos que a Cloud API aceita como foto. O resto só viaja como documento. */
const MIMES_FOTO = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "image/gif"];

function ehFoto(arquivo: File): boolean {
  return arquivo.type.startsWith("image/") || MIMES_FOTO.includes(arquivo.type);
}

function tamanhoLegivel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function EnviarAnexoWhatsapp({
  contatoId,
  nomeContato,
  telefone,
  aberto,
  aoFechar,
}: {
  contatoId: string;
  nomeContato: string;
  telefone: string;
  aberto: boolean;
  aoFechar: () => void;
}) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [formato, setFormato] = useState<Formato>("documento");
  const [legenda, setLegenda] = useState("");
  const [previa, setPrevia] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<EnvioWhatsappResultado | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const limpar = useCallback(() => {
    setArquivo(null);
    setFormato("documento");
    setLegenda("");
    setErro(null);
    setResultado(null);
    if (inputRef.current) inputRef.current.value = "";
  }, []);

  useEffect(() => {
    if (!aberto) limpar();
  }, [aberto, limpar]);

  // Prévia só faz sentido para foto; o object URL é revogado ao trocar/sair.
  useEffect(() => {
    if (!arquivo || !ehFoto(arquivo)) {
      setPrevia(null);
      return;
    }
    const url = URL.createObjectURL(arquivo);
    setPrevia(url);
    return () => URL.revokeObjectURL(url);
  }, [arquivo]);

  function escolher(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setArquivo(f);
    setErro(null);
    setResultado(null);
    // Foto entra pré-marcada como imagem (é o que o WhatsApp faz); o gestor
    // troca para documento quando quer o original do outro lado.
    setFormato(f && ehFoto(f) ? "imagem" : "documento");
  }

  async function enviar() {
    if (!arquivo) return;
    setEnviando(true);
    setErro(null);
    try {
      setResultado(await enviarAnexoWhatsapp(contatoId, arquivo, { formato, legenda }));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha no envio");
    } finally {
      setEnviando(false);
    }
  }

  const foto = arquivo ? ehFoto(arquivo) : false;

  return (
    <Modal
      aberto={aberto}
      aoFechar={aoFechar}
      rotulo="WhatsApp"
      titulo={`Enviar para ${nomeContato}`}
    >
      <div className="flex flex-col gap-4">
        <p className="text-xs text-ink-3">{telefone}</p>

        <input
          ref={inputRef}
          type="file"
          onChange={escolher}
          className="block w-full text-sm text-ink-2 file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-1.5 file:text-sm file:text-ink"
        />

        {arquivo && (
          <>
            <div className="flex items-center gap-3 rounded-lg bg-surface-2 p-3">
              {previa ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={previa}
                  alt=""
                  className="h-14 w-14 shrink-0 rounded object-cover"
                />
              ) : (
                <span className="grid h-14 w-14 shrink-0 place-items-center rounded bg-surface text-lg">
                  📄
                </span>
              )}
              <span className="min-w-0">
                <span className="block truncate text-sm">{arquivo.name}</span>
                <span className="block text-xs text-ink-3">
                  {tamanhoLegivel(arquivo.size)}
                  {arquivo.type ? ` · ${arquivo.type}` : ""}
                </span>
              </span>
            </div>

            {foto ? (
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-1 text-xs text-ink-3">Enviar como</legend>
                <div className="flex gap-2">
                  {(
                    [
                      {
                        v: "imagem" as const,
                        rotulo: "Imagem",
                        ajuda: "Aparece como foto na conversa. O WhatsApp aceita JPEG/PNG até 5 MB.",
                      },
                      {
                        v: "documento" as const,
                        rotulo: "Documento",
                        ajuda: "Mantém o arquivo original, sem recompressão. Chega como arquivo.",
                      },
                    ] as const
                  ).map((o) => (
                    <button
                      key={o.v}
                      type="button"
                      onClick={() => setFormato(o.v)}
                      aria-pressed={formato === o.v}
                      className={`flex-1 rounded-lg border p-3 text-left transition-colors ${
                        formato === o.v
                          ? "border-accent bg-surface-2"
                          : "border-hairline hover:bg-surface-2"
                      }`}
                    >
                      <span className="block text-sm">{o.rotulo}</span>
                      <span className="mt-0.5 block text-xs text-ink-3">{o.ajuda}</span>
                    </button>
                  ))}
                </div>
              </fieldset>
            ) : (
              <p className="text-xs text-ink-3">
                Este tipo de arquivo só pode ser enviado como documento.
              </p>
            )}

            <input
              value={legenda}
              onChange={(e) => setLegenda(e.target.value)}
              placeholder="Legenda (opcional)"
              className="input"
            />
          </>
        )}

        {erro && <p className="text-sm text-danger">{erro}</p>}
        {resultado && (
          <p className="text-sm text-ink-2">
            {resultado.enviado ? "Enviado" : "Não enviado"} como{" "}
            {resultado.formato === "imagem" ? "imagem" : "documento"} ·{" "}
            {tamanhoLegivel(resultado.tamanho)}
            {resultado.convertido && (
              <span className="mt-1 block text-xs text-ink-3">
                A foto foi convertida para caber nas regras do WhatsApp. Para mandar o
                arquivo exatamente como está, reenvie como documento.
              </span>
            )}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button onClick={aoFechar} className="btn btn-ghost btn-sm">
            Fechar
          </button>
          <button
            onClick={() => void enviar()}
            disabled={!arquivo || enviando}
            className="btn btn-primary btn-sm"
          >
            {enviando ? "Enviando…" : "Enviar"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
