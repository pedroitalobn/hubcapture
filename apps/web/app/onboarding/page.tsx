"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
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

export default function OnboardingPage() {
  const router = useRouter();
  const [ibge, setIbge] = useState("");
  const [nome, setNome] = useState("");
  const [uf, setUf] = useState("");
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
    <main className="mx-auto flex min-h-screen w-full max-w-lg flex-col justify-center px-6 py-10">
      <div className="glass-card animate-fade-up flex flex-col gap-6 p-8">
      <div>
        <h1 className="text-gradient text-2xl font-bold">Vamos configurar seu painel</h1>
        <p className="text-sm text-gray-500">
          Escolha um município e as fontes que quer acompanhar.
        </p>
      </div>
      <form onSubmit={salvar} className="flex flex-col gap-4">
        <div className="grid grid-cols-3 gap-3">
          <label className="col-span-1 flex flex-col gap-1 text-sm">
            IBGE
            <input
              value={ibge}
              onChange={(e) => setIbge(e.target.value)}
              maxLength={7}
              required
              placeholder="3550308"
              className="input-glass px-3.5 py-2.5"
            />
          </label>
          <label className="col-span-2 flex flex-col gap-1 text-sm">
            Nome do município
            <input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="São Paulo"
              className="input-glass px-3.5 py-2.5"
            />
          </label>
        </div>

        <div>
          <p className="mb-2 text-sm text-gray-500">Seu papel</p>
          <FilterChips
            options={PAPEIS}
            selected={papel}
            onSelect={(v) => setPapel(v)}
          />
        </div>

        <div>
          <p className="mb-2 text-sm text-gray-500">Fontes de interesse</p>
          <div className="flex flex-wrap gap-2">
            {FONTES.map((f) => (
              <button
                key={f.value}
                type="button"
                onClick={() => toggleFonte(f.value)}
                className={`chip px-3 py-1 text-sm ${
                  fontes.includes(f.value) ? "chip-active" : ""
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {msg && <p className="text-sm text-red-400">{msg}</p>}
        <button
          type="submit"
          disabled={salvando || ibge.length !== 7}
          className="btn-primary px-5 py-2.5"
        >
          {salvando ? "Salvando…" : "Concluir"}
        </button>
      </form>
      </div>
    </main>
  );
}
