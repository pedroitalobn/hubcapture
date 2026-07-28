/** Skeleton com shimmer de vidro (estado de loading). */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton-glass ${className}`} />;
}

export function SkeletonCards({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-24" />
      ))}
    </div>
  );
}
