import type { DiscoveryRadarResult, DiscoverySourceInput } from './discoveryRadarApi'
import type { DiscoveryContinuationSegment } from './discoveryContinuationApi'
import {
  discoveryWorkspaceDbKey,
  discoveryWorkspaceIsAccountScoped,
} from './discoveryWorkspaceAccountIsolation'

const DB_NAME = 'medicalchannelai.discovery.continuation.local'
const DB_VERSION = 1
const DB_STORE = 'ledger'
const MAX_SEGMENTS_PER_ROOT = 5

export interface DiscoveryContinuationLedger {
  schema_version: 1
  source_id: string
  source_url: string
  root_content_fingerprint: string
  segments: DiscoveryContinuationSegment[]
}

function continuationRecordKey(sourceId: string): string {
  return discoveryWorkspaceIsAccountScoped()
    ? `${discoveryWorkspaceDbKey()}::${sourceId}`
    : sourceId
}

function activeAccountRecordPrefix(): string | null {
  return discoveryWorkspaceIsAccountScoped()
    ? `${discoveryWorkspaceDbKey()}::`
    : null
}

function openDb(): Promise<IDBDatabase> {
  if (typeof indexedDB === 'undefined') return Promise.reject(new Error('INDEXED_DB_UNAVAILABLE'))
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(DB_STORE)) db.createObjectStore(DB_STORE)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('CONTINUATION_DB_OPEN_FAILED'))
    request.onblocked = () => reject(new Error('CONTINUATION_DB_BLOCKED'))
  })
}

function blankLedger(source: DiscoverySourceInput, root: DiscoveryRadarResult): DiscoveryContinuationLedger {
  return {
    schema_version: 1,
    source_id: source.id,
    source_url: source.url,
    root_content_fingerprint: root.content_fingerprint,
    segments: [],
  }
}

function normalizeSegment(value: unknown): DiscoveryContinuationSegment | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const row = value as Partial<DiscoveryContinuationSegment>
  if (
    row.schema_version !== '0.1' ||
    row.mode !== 'AI_DISCOVERY_CONTINUATION_SHADOW' ||
    row.analysis_version !== 'agnes-discovery-continuation-v1' ||
    typeof row.segment_id !== 'string' ||
    !Number.isInteger(row.segment_index) || Number(row.segment_index) < 1 ||
    typeof row.source_id !== 'string' ||
    typeof row.source_url !== 'string' ||
    typeof row.root_content_fingerprint !== 'string' ||
    !Array.isArray(row.page_urls) ||
    !Array.isArray(row.anchor_snapshot) || row.anchor_snapshot.length > 80 ||
    !Array.isArray(row.candidates) ||
    typeof row.exhausted !== 'boolean' ||
    row.partial !== false ||
    row.error_code !== null ||
    row.production_data_mutated !== false
  ) return null
  return row as DiscoveryContinuationSegment
}

function normalizeLedger(value: unknown): DiscoveryContinuationLedger | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const row = value as Partial<DiscoveryContinuationLedger>
  if (
    row.schema_version !== 1 ||
    typeof row.source_id !== 'string' ||
    typeof row.source_url !== 'string' ||
    typeof row.root_content_fingerprint !== 'string' ||
    !Array.isArray(row.segments) || row.segments.length > MAX_SEGMENTS_PER_ROOT
  ) return null
  const segments = row.segments.map(normalizeSegment)
  if (segments.some((item) => item === null)) return null
  for (let index = 0; index < segments.length; index += 1) {
    const segment = segments[index] as DiscoveryContinuationSegment
    if (
      segment.source_id !== row.source_id ||
      segment.source_url !== row.source_url ||
      segment.root_content_fingerprint !== row.root_content_fingerprint ||
      segment.segment_index !== index + 1 ||
      (index < segments.length - 1 && segment.exhausted)
    ) return null
  }
  return {
    schema_version: 1,
    source_id: row.source_id,
    source_url: row.source_url,
    root_content_fingerprint: row.root_content_fingerprint,
    segments: segments as DiscoveryContinuationSegment[],
  }
}

async function readLedger(recordKey: string): Promise<DiscoveryContinuationLedger | null> {
  const db = await openDb()
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(DB_STORE, 'readonly')
      const request = transaction.objectStore(DB_STORE).get(recordKey)
      request.onsuccess = () => resolve(normalizeLedger(request.result))
      request.onerror = () => reject(request.error ?? new Error('CONTINUATION_DB_READ_FAILED'))
    })
  } finally {
    db.close()
  }
}

async function writeLedger(ledger: DiscoveryContinuationLedger, recordKey: string): Promise<void> {
  const db = await openDb()
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction(DB_STORE, 'readwrite')
      transaction.objectStore(DB_STORE).put(ledger, recordKey)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error('CONTINUATION_DB_WRITE_FAILED'))
      transaction.onabort = () => reject(transaction.error ?? new Error('CONTINUATION_DB_WRITE_ABORTED'))
    })
  } finally {
    db.close()
  }
}

export function continuationEligible(root: DiscoveryRadarResult) {
  return (
    root.coverage_partial === false &&
    (root.coverage_page_limit_applied === true || root.anchor_cap_applied === true)
  )
}

export async function loadContinuationLedger(
  source: DiscoverySourceInput,
  root: DiscoveryRadarResult,
): Promise<DiscoveryContinuationLedger> {
  if (!continuationEligible(root)) return blankLedger(source, root)
  const recordKey = continuationRecordKey(source.id)
  try {
    const stored = await readLedger(recordKey)
    if (
      stored &&
      stored.source_url === source.url &&
      stored.root_content_fingerprint === root.content_fingerprint
    ) return stored
  } catch {
    // Continuation is optional; root radar remains usable if this ledger is unavailable.
  }
  return blankLedger(source, root)
}

export async function appendContinuationSegment(
  ledger: DiscoveryContinuationLedger,
  segment: DiscoveryContinuationSegment,
): Promise<DiscoveryContinuationLedger> {
  if (ledger.segments.length >= MAX_SEGMENTS_PER_ROOT) throw new Error('CONTINUATION_SEGMENT_LIMIT_REACHED')
  if (ledger.segments.at(-1)?.exhausted) throw new Error('CONTINUATION_ALREADY_EXHAUSTED')
  if (
    segment.source_id !== ledger.source_id ||
    segment.source_url !== ledger.source_url ||
    segment.root_content_fingerprint !== ledger.root_content_fingerprint ||
    segment.segment_index !== ledger.segments.length + 1 ||
    segment.partial !== false
  ) throw new Error('CONTINUATION_SEGMENT_MISMATCH')

  const seenAnchorUrls = new Set(ledger.segments.flatMap((item) => item.anchor_snapshot.map((anchor) => anchor.url)))
  if (segment.anchor_snapshot.some((anchor) => seenAnchorUrls.has(anchor.url))) {
    throw new Error('CONTINUATION_SEGMENT_DUPLICATE_ANCHOR')
  }

  const next: DiscoveryContinuationLedger = {
    ...ledger,
    segments: [...ledger.segments, segment],
  }
  // Capture the account namespace before the asynchronous IndexedDB write. A
  // late segment from a previous account can never land in the next account.
  const recordKey = continuationRecordKey(ledger.source_id)
  await writeLedger(next, recordKey)
  return next
}

export async function clearContinuationLedger(sourceId: string): Promise<void> {
  const recordKey = continuationRecordKey(sourceId)
  try {
    const db = await openDb()
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = db.transaction(DB_STORE, 'readwrite')
        transaction.objectStore(DB_STORE).delete(recordKey)
        transaction.oncomplete = () => resolve()
        transaction.onerror = () => reject(transaction.error ?? new Error('CONTINUATION_DB_DELETE_FAILED'))
        transaction.onabort = () => reject(transaction.error ?? new Error('CONTINUATION_DB_DELETE_ABORTED'))
      })
    } finally {
      db.close()
    }
  } catch {
    // Clearing optional continuation state must not break the root radar workspace.
  }
}

export async function clearActiveContinuationLedgersForAccount(): Promise<void> {
  const prefix = activeAccountRecordPrefix()
  if (!prefix) return
  try {
    const db = await openDb()
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = db.transaction(DB_STORE, 'readwrite')
        const store = transaction.objectStore(DB_STORE)
        const request = store.openCursor()
        request.onsuccess = () => {
          const cursor = request.result
          if (!cursor) return
          if (typeof cursor.key === 'string' && cursor.key.startsWith(prefix)) cursor.delete()
          cursor.continue()
        }
        request.onerror = () => reject(request.error ?? new Error('CONTINUATION_DB_CURSOR_FAILED'))
        transaction.oncomplete = () => resolve()
        transaction.onerror = () => reject(transaction.error ?? new Error('CONTINUATION_DB_CLEAR_FAILED'))
        transaction.onabort = () => reject(transaction.error ?? new Error('CONTINUATION_DB_CLEAR_ABORTED'))
      })
    } finally {
      db.close()
    }
  } catch {
    // Account deletion already succeeded on the server. Orphaned records remain
    // scoped to the deleted account token and cannot be read by another account.
  }
}

export function continuationLedgerSummary(ledger: DiscoveryContinuationLedger) {
  const last = ledger.segments.at(-1)
  return {
    segment_count: ledger.segments.length,
    analyzed_anchor_count: ledger.segments.reduce((sum, item) => sum + item.analyzed_anchor_count, 0),
    candidate_count: ledger.segments.reduce((sum, item) => sum + item.candidate_count, 0),
    exhausted: last?.exhausted === true,
    can_continue: ledger.segments.length < MAX_SEGMENTS_PER_ROOT && last?.exhausted !== true,
  }
}
