import { cx } from "./ui";

/** Skeleton pulsante (estado de carregamento). */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-surface-2", className)} />;
}

export function SkeletonCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-[92px]" />
      ))}
    </div>
  );
}

/** Placeholder de lista de cartões — a Captação carregava sem nenhum (UI-06). */
export function SkeletonList({ count = 3 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-xl border border-line p-4">
          <div className="flex flex-col gap-3">
            <div className="flex items-start justify-between gap-4">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-28" />
            </div>
            <div className="flex gap-2">
              <Skeleton className="h-5 w-20 rounded-full" />
              <Skeleton className="h-5 w-24 rounded-full" />
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
            <Skeleton className="h-3 w-1/2" />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonLines({ count = 4 }: { count?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-10" />
      ))}
    </div>
  );
}
