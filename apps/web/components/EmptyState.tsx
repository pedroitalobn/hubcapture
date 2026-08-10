import { Inbox, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Estado vazio com ícone, mensagem e ação — no lugar de um parágrafo solto. */
export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-gray-300 px-6 py-12 text-center animate-fade-up dark:border-gray-700">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gray-100 text-gray-400 dark:bg-gray-900 dark:text-gray-500">
        <Icon className="h-7 w-7" aria-hidden />
      </span>
      <div>
        <p className="font-semibold">{title}</p>
        {description && (
          <p className="mx-auto mt-1 max-w-md text-sm text-gray-500">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}
