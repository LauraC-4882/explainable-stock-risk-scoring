import { useLanguage } from '../i18n/LanguageContext'
import { fmt } from '../utils'
import InfoTooltip from './InfoTooltip'

export default function MetricTiles({ score }) {
  const { t } = useLanguage()
  const rsi = score.indicators?.rsi_14
  const rsiClass = rsi > 70 ? 'text-down' : rsi < 30 ? 'text-up' : 'text-slate-100'

  return (
    <div className="grid grid-cols-4 divide-x divide-border border-b border-border bg-surface2/20">
      <Tile label={t('metrics.vol30d')} value={fmt(score.volatility_30d, 100, 1, '%')} tooltip={t('glossary.volatility')} />
      <Tile
        label={t('metrics.var95')}
        value={fmt(score.var_95, 100, 2, '%')}
        valueClass="text-down"
        tooltip={t('glossary.var95')}
      />
      <Tile
        label={t('metrics.beta')}
        value={score.beta != null ? (+score.beta).toFixed(2) : '—'}
        tooltip={t('glossary.beta')}
      />
      <Tile label={t('metrics.rsi')} value={fmt(rsi, 1, 1)} valueClass={rsiClass} tooltip={t('glossary.rsi')} tooltipAlign="right" />
    </div>
  )
}

function Tile({ label, value, valueClass = '', tooltip, tooltipAlign = 'center' }) {
  return (
    <div className="px-2 py-2.5 transition-colors duration-150 hover:bg-surface2/60 sm:px-3.5">
      <div className="flex items-center gap-1 whitespace-nowrap text-[0.62rem] font-semibold uppercase tracking-wide text-muted sm:text-[0.65rem]">
        {label}
        {tooltip && <InfoTooltip text={tooltip} align={tooltipAlign} />}
      </div>
      <div className={`mt-0.5 text-sm font-bold tabular-nums ${valueClass}`}>{value}</div>
    </div>
  )
}
