"use client";

import { Check, Compass, Landmark, MapPin, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/Button";
import { Callout } from "@/components/Callout";
import { FilterChips } from "@/components/FilterChips";
import { api, getToken } from "@/lib/api/client";

const FONTES = [
  { value: "fpm", label: "FPM" },
  { value: "emendas", label: "Emendas" },
  { value: "fns", label: "FNS (Saúde)" },
  { value: "fnde", label: "FNDE (Educação)" },
  { value: "transferegov_ff", label: "TransfereGov" },
];

const PAPEIS = [
  { value: "parlamentar", label: "Parlamentar" },
  { value: "executivo", label: "Chefe do Executivo" },
  { value: "equipe", label: "Equipe" },
];

const INPUT =
  "rounded-lg border border-gray-300 bg-white px-3 py-2 transition-colors focus:border-brand-500 dark:border-gray-700 dark:bg-gray-950";

export default function OnboardingPage() {
  const router = useRouter();
  const [ibge, setIbge] = useState("");
  const [nome, setNome] = useState("");
  const [uf] = useState("");
  const [papel, setPapel] = useState<string | null>("executivo");
  const [fontes, setFontes] = useState<string[]>(["fpm", "emendas"]);
  const [msg, setMsg] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  function toggleFonte(v: string | null) {
    if (v === null) return;
    setFontes((f) => (f.includes(v) ? f.filter((x) => x !== v) : [...f, v]));
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setSalvando(true);
    setMsg(null);
    const { error } = await api.POST("/api/v1/onboarding", {
      body: {
        municipios: [{ ibge, nome: nome || null, uf: uf || null }],
        fontes,
        areas: [],
        monitorar_ativo: true,
        papel: papel ?? undefined,
        disparar_sync: false,
      },
    });
    if (error) {
      setMsg("Falha ao salvar o onboarding.");
    } else {
      router.push("/painel/repasses");
    }
    setSalvando(false);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-6 px-6 py-10">
      <div className="flex items-center gap-3 animate-fade-up">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-600 to-brand-800 text-white shadow-md">
          <Compass className="h-6 w-6" aria-hidden />
        </span>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Vamos configurar seu painel
          </h1>
          <p className="text-sm text-gray-500">
            Escolha um município e as fontes que quer acompanhar.
          </p>
        </div>
      </div>

      <form
        onSubmit={salvar}
        className="flex flex-col gap-6 rounded-2xl border border-gray-200 bg-white p-6 shadow-card animate-fade-up [animation-delay:80ms] dark:border-gray-800 dark:bg-gray-900"
      >
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-2 inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            <MapPin className="h-4 w-4" aria-hidden />
            Território
          </legend>
          <div className="grid grid-cols-3 gap-3">
            <label className="col-span-1 flex flex-col gap-1.5 text-sm font-medium">
              IBGE
              <input
                value={ibge}
                onChange={(e) => setIbge(e.target.value.replace(/\D/g, ""))}
                maxLength={7}
                required
                inputMode="numeric"
                placeholder="3550308"
                className={`${INPUT} tabular-nums`}
              />
            </label>
            <label className="col-span-2 flex flex-col gap-1.5 text-sm font-medium">
              Nome do município
              <input
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="São Paulo"
                className={INPUT}
              />
            </label>
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            <UserRound className="h-4 w-4" aria-hidden />
            Seu papel
          </legend>
          <FilterChips
            options={PAPEIS}
            selected={papel}
            onSelect={(v) => setPapel(v)}
            allLabel="Nenhum"
          />
        </fieldset>

        <fieldset>
          <legend className="mb-2 inline-flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
            <Landmark className="h-4 w-4" aria-hidden />
            Fontes de interesse
          </legend>
          <div className="flex flex-wrap gap-2">
            {FONTES.map((f) => {
              const ativa = fontes.includes(f.value);
              return (
                <button
                  key={f.value}
                  type="button"
                  onClick={() => toggleFonte(f.value)}
                  aria-pressed={ativa}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-medium transition-all duration-150 active:scale-95 ${
                    ativa
                      ? "border-brand bg-brand text-brand-fg shadow-sm"
                      : "border-gray-300 bg-white text-gray-700 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:border-brand-700 dark:hover:bg-brand-900/20"
                  }`}
                >
                  {ativa && <Check className="h-3.5 w-3.5 animate-scale-in" aria-hidden />}
                  {f.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        {msg && <Callout tone="error">{msg}</Callout>}
        <Button
          type="submit"
          loading={salvando}
          disabled={ibge.length !== 7}
          icon={<Check className="h-4 w-4" aria-hidden />}
        >
          {salvando ? "Salvando…" : "Concluir"}
        </Button>
      </form>
    </main>
  );
}
