import { CircleAlert, CircleCheck, Info, TriangleAlert } from "lucide-react";

export type CalloutTone = "success" | "error" | "warning" | "info";

const STYLES: Record<CalloutTone, { box: string; icon: React.ReactNode }> = {
  success: {
    box: "border-green-200 bg-green-50 text-green-800 dark:border-green-900/60 dark:bg-green-950/40 dark:text-green-300",
    icon: <CircleCheck className="h-4 w-4 shrink-0" aria-hidden />,
  },
  error: {
    box: "border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300",
    icon: <CircleAlert className="h-4 w-4 shrink-0" aria-hidden />,
  },
  warning: {
    box: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300",
    icon: <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden />,
  },
  info: {
    box: "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-300",
    icon: <Info className="h-4 w-4 shrink-0" aria-hidden />,
  },
};

/** Mensagem de feedback (sucesso/erro/aviso/info) com ícone e entrada animada. */
export function Callout({
  tone = "info",
  children,
}: {
  tone?: CalloutTone;
  children: React.ReactNode;
}) {
  const s = STYLES[tone];
  return (
    <div
      role="status"
      className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm animate-scale-in ${s.box}`}
    >
      {s.icon}
      <span>{children}</span>
    </div>
  );
}
