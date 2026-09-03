const OWNER_KEY = 'medicalchannelai.discovery.workspace.owner.v1'
const SWITCH_KEY = 'medicalchannelai.discovery.workspace.switch.v1'
const BOOTSTRAP_KEY = 'medicalchannelai.discovery.workspace.bootstrap.v4'
const V3_KEY = 'medicalchannelai.discovery.workspace.v3'
const V2_KEY = 'medicalchannelai.discovery.workspace.v2'
const ACCOUNT_BOOTSTRAP_PREFIX = 'medicalchannelai.discovery.workspace.account.v1.'
const ACCOUNT_V3_PREFIX = 'medicalchannelai.discovery.workspace.account-v3.v1.'
const ACCOUNT_V2_PREFIX = 'medicalchannelai.discovery.workspace.account-v2.v1.'
const UNOWNED_BOOTSTRAP_KEY = 'medicalchannelai.discovery.workspace.unowned.v1.bootstrap'
const UNOWNED_V3_KEY = 'medicalchannelai.discovery.workspace.unowned.v1.v3'
const UNOWNED_V2_KEY = 'medicalchannelai.discovery.workspace.unowned.v1.v2'

const DB_NAME = 'medicalchannelai.discovery.local'
const DB_VERSION = 1
const DB_STORE = 'workspace'
const DB_CURRENT_KEY = 'current'
const DB_ACCOUNT_PREFIX = 'account:'
const DB_UNOWNED_KEY = 'legacy-unowned'
const TOKEN_RE = /^[0-9a-f]{16}$/
const PHASES = new Set(['PREPARED', 'PREVIOUS_BACKED_UP', 'TARGET_RESTORED'])

function hash32(text, seed) {
  let hash = seed >>> 0
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, '0')
}

export function discoveryAccountToken(username) {
  const normalized = String(username || '').trim().toLowerCase()
  if (!normalized) throw new Error('DISCOVERY_ACCOUNT_SCOPE_INVALID')
  return `${hash32(normalized, 2166136261)}${hash32(normalized, 2246822519)}`
}

function browserLocalStorage() {
  if (typeof window === 'undefined' || !window.localStorage) {
    throw new Error('DISCOVERY_ACCOUNT_LOCAL_STORAGE_UNAVAILABLE')
  }
  return window.localStorage
}

function accountBootstrapKey(token) {
  return `${ACCOUNT_BOOTSTRAP_PREFIX}${token}`
}

function accountV3Key(token) {
  return `${ACCOUNT_V3_PREFIX}${token}`
}

function accountV2Key(token) {
  return `${ACCOUNT_V2_PREFIX}${token}`
}

function copyOrClearLocal(storage, from, to) {
  const value = storage.getItem(from)
  if (value === null) storage.removeItem(to)
  else storage.setItem(to, value)
}

function archiveLocalIfPresent(storage, from, to) {
  const value = storage.getItem(from)
  if (value !== null && storage.getItem(to) === null) storage.setItem(to, value)
}

function restoreLocalValue(storage, from, to) {
  const value = storage.getItem(from)
  if (value === null) storage.removeItem(to)
  else storage.setItem(to, value)
}

function backupCurrentLocal(storage, token) {
  if (token) {
    copyOrClearLocal(storage, BOOTSTRAP_KEY, accountBootstrapKey(token))
    copyOrClearLocal(storage, V3_KEY, accountV3Key(token))
    copyOrClearLocal(storage, V2_KEY, accountV2Key(token))
    return
  }
  archiveLocalIfPresent(storage, BOOTSTRAP_KEY, UNOWNED_BOOTSTRAP_KEY)
  archiveLocalIfPresent(storage, V3_KEY, UNOWNED_V3_KEY)
  archiveLocalIfPresent(storage, V2_KEY, UNOWNED_V2_KEY)
}

function restoreLocal(storage, token) {
  restoreLocalValue(storage, accountBootstrapKey(token), BOOTSTRAP_KEY)
  restoreLocalValue(storage, accountV3Key(token), V3_KEY)
  restoreLocalValue(storage, accountV2Key(token), V2_KEY)
}

function indexedDbAvailable() {
  return typeof indexedDB !== 'undefined'
}

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION)
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(DB_STORE)) db.createObjectStore(DB_STORE)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('DISCOVERY_ACCOUNT_DB_OPEN_FAILED'))
    request.onblocked = () => reject(new Error('DISCOVERY_ACCOUNT_DB_BLOCKED'))
  })
}

async function readDbValue(key) {
  const db = await openDb()
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(DB_STORE, 'readonly')
      const request = transaction.objectStore(DB_STORE).get(key)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error ?? new Error('DISCOVERY_ACCOUNT_DB_READ_FAILED'))
    })
  } finally {
    db.close()
  }
}

async function writeDbValue(key, value) {
  const db = await openDb()
  try {
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(DB_STORE, 'readwrite')
      transaction.objectStore(DB_STORE).put(value, key)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error('DISCOVERY_ACCOUNT_DB_WRITE_FAILED'))
      transaction.onabort = () => reject(transaction.error ?? new Error('DISCOVERY_ACCOUNT_DB_WRITE_ABORTED'))
    })
  } finally {
    db.close()
  }
}

async function deleteDbValue(key) {
  const db = await openDb()
  try {
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(DB_STORE, 'readwrite')
      transaction.objectStore(DB_STORE).delete(key)
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error('DISCOVERY_ACCOUNT_DB_DELETE_FAILED'))
      transaction.onabort = () => reject(transaction.error ?? new Error('DISCOVERY_ACCOUNT_DB_DELETE_ABORTED'))
    })
  } finally {
    db.close()
  }
}

async function backupCurrentIndexed(token) {
  if (!indexedDbAvailable()) return
  const current = await readDbValue(DB_CURRENT_KEY)
  if (token) {
    const accountKey = `${DB_ACCOUNT_PREFIX}${token}`
    if (current === undefined) await deleteDbValue(accountKey)
    else await writeDbValue(accountKey, current)
    return
  }
  if (current !== undefined && await readDbValue(DB_UNOWNED_KEY) === undefined) {
    await writeDbValue(DB_UNOWNED_KEY, current)
  }
}

async function restoreIndexed(token) {
  if (!indexedDbAvailable()) return
  const saved = await readDbValue(`${DB_ACCOUNT_PREFIX}${token}`)
  if (saved === undefined) await deleteDbValue(DB_CURRENT_KEY)
  else await writeDbValue(DB_CURRENT_KEY, saved)
}

function validToken(value) {
  return typeof value === 'string' && TOKEN_RE.test(value)
}

function readJournal(storage) {
  const raw = storage.getItem(SWITCH_KEY)
  if (!raw) return null
  let value
  try {
    value = JSON.parse(raw)
  } catch {
    storage.removeItem(SWITCH_KEY)
    throw new Error('DISCOVERY_ACCOUNT_SWITCH_STATE_INVALID')
  }
  const valid = value && typeof value === 'object' &&
    (value.from === null || validToken(value.from)) &&
    validToken(value.to) && PHASES.has(value.phase)
  if (!valid) {
    storage.removeItem(SWITCH_KEY)
    throw new Error('DISCOVERY_ACCOUNT_SWITCH_STATE_INVALID')
  }
  return value
}

function writeJournal(storage, journal) {
  storage.setItem(SWITCH_KEY, JSON.stringify(journal))
}

async function completeSwitch(storage, initialJournal) {
  let journal = { ...initialJournal }

  if (journal.phase === 'PREPARED') {
    // Copy only. Do not remove/replace current yet, so this phase is idempotent
    // even if IndexedDB fails after the local backup succeeds.
    backupCurrentLocal(storage, journal.from)
    await backupCurrentIndexed(journal.from)
    journal = { ...journal, phase: 'PREVIOUS_BACKED_UP' }
    writeJournal(storage, journal)
  }

  if (journal.phase === 'PREVIOUS_BACKED_UP') {
    // The previous account is safely backed up. Repeating this restore after a
    // partial failure is safe because target backups are never mutated here.
    restoreLocal(storage, journal.to)
    await restoreIndexed(journal.to)
    journal = { ...journal, phase: 'TARGET_RESTORED' }
    writeJournal(storage, journal)
  }

  if (journal.phase === 'TARGET_RESTORED') {
    storage.setItem(OWNER_KEY, journal.to)
    storage.removeItem(SWITCH_KEY)
  }
}

export async function activateDiscoveryWorkspaceForAccount(username) {
  const token = discoveryAccountToken(username)
  const storage = browserLocalStorage()

  // Finish an interrupted switch before evaluating the newly authenticated
  // account. Routes remain blocked until this promise resolves.
  const pending = readJournal(storage)
  if (pending) await completeSwitch(storage, pending)

  const previousToken = storage.getItem(OWNER_KEY)
  if (previousToken === token) return token
  if (previousToken !== null && !validToken(previousToken)) {
    throw new Error('DISCOVERY_ACCOUNT_OWNER_INVALID')
  }

  const journal = {
    from: previousToken,
    to: token,
    phase: 'PREPARED',
  }
  writeJournal(storage, journal)
  await completeSwitch(storage, journal)
  return token
}

export async function clearActiveDiscoveryWorkspaceAccount() {
  if (typeof window === 'undefined' || !window.localStorage) return
  const storage = window.localStorage
  const token = storage.getItem(OWNER_KEY)

  // Server-side deletion has already succeeded when this is called. Remove the
  // active current view first so another account can never inherit it even if
  // IndexedDB cleanup later fails.
  storage.removeItem(BOOTSTRAP_KEY)
  storage.removeItem(V3_KEY)
  storage.removeItem(V2_KEY)
  storage.removeItem(SWITCH_KEY)
  storage.removeItem(OWNER_KEY)
  if (validToken(token)) {
    storage.removeItem(accountBootstrapKey(token))
    storage.removeItem(accountV3Key(token))
    storage.removeItem(accountV2Key(token))
  }

  if (!indexedDbAvailable()) return
  try {
    await deleteDbValue(DB_CURRENT_KEY)
    if (validToken(token)) await deleteDbValue(`${DB_ACCOUNT_PREFIX}${token}`)
  } catch {
    // Local owner/current were already removed. A later account activation will
    // treat any orphaned IndexedDB current value as unowned instead of claiming it.
  }
}
