import { useLanguage } from '../i18n/LanguageContext'

// Permanent, non-dismissible — deliberately its own tiny component so a
// future edit can't accidentally wrap it in a collapsible/closeable
// container. The risk score is computed from real market data; everything
// in this platform is other users' opinion, and should be read as such.
export default function CommunityDisclaimer() {
  const { t } = useLanguage()
  return (
    // Icon-free: a quiet italic note reads as legal small print on its own.
    <div className="border-b border-border bg-surface2/40 px-4 py-2.5 text-[0.7rem] italic leading-relaxed text-muted sm:px-5">
      {t('community.disclaimer')}
    </div>
  )
}
