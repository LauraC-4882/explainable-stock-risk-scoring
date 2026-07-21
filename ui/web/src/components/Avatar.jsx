// Deterministic initials avatar — no image upload/storage involved (this
// app has no durable file storage on most free-tier hosts, see db.py), so
// the avatar is derived purely from the user's email: a hash picks one of
// the brand hues, the first letter is the glyph.
const HUES = ['#38bdf8', '#4f9cf6', '#14b8a6', '#f59e0b', '#8b7be8']

function hueFor(seed) {
  let hash = 0
  for (let i = 0; i < seed.length; i++) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0
  return HUES[hash % HUES.length]
}

export default function Avatar({ email, size = 34, className = '' }) {
  const letter = (email?.trim()[0] || '?').toUpperCase()
  const color = hueFor(email || '?')

  return (
    <div
      className={`flex flex-shrink-0 items-center justify-center rounded-full font-black text-white ${className}`}
      style={{ width: size, height: size, background: color, fontSize: size * 0.42 }}
      aria-hidden="true"
    >
      {letter}
    </div>
  )
}
