"use client";

export default function ObrasPage() {
  return (
    <>
      <header>
        <h1 className="text-2xl font-bold">Obras</h1>
        <p className="text-sm text-gray-500">
          Execução das obras no seu território (SISMOB · SIMEC · CAIXA).
        </p>
      </header>
      <div className="rounded-lg border border-dashed border-gray-300 p-6 text-sm text-gray-500 dark:border-gray-700">
        Em breve: acompanhamento das obras do(s) seu(s) município(s), com mapa e
        status de execução. Este eixo (P3) fecha o ciclo captar → receber →
        executar → prestar contas.
      </div>
    </>
  );
}
