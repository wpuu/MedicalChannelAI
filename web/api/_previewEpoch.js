import { getCache as nativeGetCache } from '@vercel/functions'

export function previewEpoch() {
  if (String(process.env.VERCEL_ENV || '').trim().toLowerCase() !== 'preview') return null
  const value = String(process.env.MCAI_PREVIEW_EPOCH || '').trim()
  if (!value) return null
  if (!/^[a-z0-9][a-z0-9-]{0,47}$/.test(value)) throw new Error('PREVIEW_EPOCH_INVALID')
  return value
}
export function epochKey(value, epoch) {
  return `medicalchannelai:preview:${epoch}:${value}`
}
export function scopePreviewCache(cache, epoch = previewEpoch()) {
  if (!epoch) return cache
  return {
    get: key => cache.get(epochKey(key, epoch)),
    set: (key, value, options) => cache.set(epochKey(key, epoch), value, options ? {
      ...options,
      ...(options.tags ? { tags: options.tags.map(tag => epochKey(tag, epoch)) } : {}),
    } : options),
    delete: key => cache.delete(epochKey(key, epoch)),
    expireTag: tags => cache.expireTag(Array.isArray(tags)
      ? tags.map(tag => epochKey(tag, epoch)) : epochKey(tags, epoch)),
  }
}
export function getCache(options) {
  const epoch = previewEpoch()
  return scopePreviewCache(nativeGetCache(options), epoch)
}

export function assertPreviewDatabase(url) {
  if (!previewEpoch()) return
  const expected = String(process.env.MCAI_PREVIEW_DATABASE || '').trim()
  let actual
  try { actual = decodeURIComponent(new URL(url).pathname.slice(1)) } catch { throw new Error('PREVIEW_DATABASE_SCOPE_INVALID') }
  if (!/^mcai_p0_epoch_[a-z0-9_]+$/.test(expected) || actual !== expected) {
    throw new Error('PREVIEW_DATABASE_SCOPE_INVALID')
  }
}
