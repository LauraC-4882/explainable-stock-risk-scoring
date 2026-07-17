import { useLanguage } from '../i18n/LanguageContext'
import { useAuth } from './AuthContext'

export default function WatchlistPanel({ onAdd }) {
  const { t } = useLanguage()
  const { watchlistPanelOpen, closeWatchlistPanel, watchlist, removeFromWatchlist } = useAuth()

  if (!watchlistPanelOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex animate-fade-in items-center justify-center bg-black/60 backdrop-blur-sm"
      style={{ animationDuration: '0.15s' }}
      onClick={closeWatchlistPanel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-[80vh] w-full max-w-md animate-fade-in overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl shadow-black/50"
        style={{ animationDuration: '0.2s' }}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-lg font-bold text-slate-100">{t('watchlist.title')}</h2>
          <button
            onClick={closeWatchlistPanel}
            className="rounded-md px-1.5 py-0.5 text-base leading-none text-muted transition hover:bg-down/10 hover:text-down"
          >
            ✕
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto">
          {watchlist.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm leading-relaxed text-muted">
              {t('watchlist.empty')}
            </p>
          ) : (
            watchlist.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between gap-3 border-b border-border px-5 py-3 transition-colors duration-150 last:border-b-0 hover:bg-surface2/50"
              >
                <div className="min-w-0">
                  <div className="font-bold text-slate-100">{item.ticker}</div>
                  {item.notes && (
                    <div className="truncate text-xs text-muted" title={item.notes}>
                      {item.notes}
                    </div>
                  )}
                </div>
                <div className="flex flex-shrink-0 items-center gap-2">
                  <button
                    onClick={() => onAdd(item.ticker)}
                    className="rounded-full border border-accent px-3 py-1 text-xs font-semibold text-accent transition-all duration-150 hover:bg-accent/10 active:scale-95"
                  >
                    {t('watchlist.add')}
                  </button>
                  <button
                    onClick={() => removeFromWatchlist(item.id)}
                    className="rounded-full border border-border px-3 py-1 text-xs font-semibold text-muted transition-all duration-150 hover:border-down hover:text-down active:scale-95"
                  >
                    {t('watchlist.remove')}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
