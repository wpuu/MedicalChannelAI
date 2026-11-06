// PostgreSQL timestamptz supports microseconds. Date.parse is only the whole
// millisecond component; keep the remaining digits for revision ordering.
export function snapshotRevisionMicros(value) {
  const text = String(value ?? '')
  const match = text.match(/T\d{2}:\d{2}:\d{2}(?:\.(\d{1,6}))?(?:Z|[+-]\d{2}:\d{2})$/)
  const millis = Date.parse(text)
  if (!match || !Number.isFinite(millis)) throw new Error('PUBLIC_SNAPSHOT_AS_OF_INVALID')
  const fraction = (match[1] || '').padEnd(6, '0')
  return BigInt(millis) * 1000n + BigInt(fraction.slice(3))
}

