// Layout-matched loading placeholder, shown instead of a bare spinner so the
// card doesn't visually jump once real data arrives.
export default function CardSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="flex items-center gap-5 border-b border-border px-5 py-4">
        <div className="skeleton-shimmer animate-shimmer h-[68px] w-[116px] rounded-full" />
        <div className="space-y-2">
          <div className="skeleton-shimmer animate-shimmer h-9 w-16 rounded" />
          <div className="skeleton-shimmer animate-shimmer h-4 w-20 rounded-full" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 border-b border-border px-4 py-4 sm:grid-cols-3 md:grid-cols-5 sm:px-5">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="panel-tile skeleton-shimmer animate-shimmer h-[74px]" />
        ))}
      </div>
      <div className="space-y-2.5 border-b border-border px-5 py-3.5">
        <div className="skeleton-shimmer animate-shimmer h-2.5 w-24 rounded" />
        <div className="skeleton-shimmer animate-shimmer h-1.5 w-full rounded-full" />
        <div className="skeleton-shimmer animate-shimmer h-1.5 w-full rounded-full" />
      </div>
      <div className="grid grid-cols-4 divide-x divide-border border-b border-border">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="space-y-1.5 px-3.5 py-2.5">
            <div className="skeleton-shimmer animate-shimmer h-2 w-10 rounded" />
            <div className="skeleton-shimmer animate-shimmer h-3.5 w-8 rounded" />
          </div>
        ))}
      </div>
      <div className="space-y-3.5 px-4 py-4">
        <div className="skeleton-shimmer animate-shimmer h-32 w-full rounded-lg" />
        <div className="skeleton-shimmer animate-shimmer h-20 w-full rounded-lg" />
      </div>
    </div>
  )
}
