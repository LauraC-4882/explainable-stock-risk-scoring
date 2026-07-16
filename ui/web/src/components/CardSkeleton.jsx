// Layout-matched loading placeholder, shown instead of a bare spinner so the
// card doesn't visually jump once real data arrives.
export default function CardSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="flex items-center gap-5 border-b border-border px-5 py-4">
        <div className="h-[68px] w-[116px] rounded-full bg-surface2" />
        <div className="space-y-2">
          <div className="h-9 w-16 rounded bg-surface2" />
          <div className="h-4 w-20 rounded-full bg-surface2" />
        </div>
      </div>
      <div className="space-y-2.5 border-b border-border px-5 py-3.5">
        <div className="h-2.5 w-24 rounded bg-surface2" />
        <div className="h-1.5 w-full rounded-full bg-surface2" />
        <div className="h-1.5 w-full rounded-full bg-surface2" />
      </div>
      <div className="grid grid-cols-4 divide-x divide-border border-b border-border">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="space-y-1.5 px-3.5 py-2.5">
            <div className="h-2 w-10 rounded bg-surface2" />
            <div className="h-3.5 w-8 rounded bg-surface2" />
          </div>
        ))}
      </div>
      <div className="space-y-3.5 px-4 py-4">
        <div className="h-32 w-full rounded-lg bg-surface2" />
        <div className="h-20 w-full rounded-lg bg-surface2" />
      </div>
    </div>
  )
}
