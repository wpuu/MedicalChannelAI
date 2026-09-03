const LEGACY_BOOTSTRAP_KEY = 'medicalchannelai.discovery.workspace.bootstrap.v4'
const LEGACY_V3_KEY = 'medicalchannelai.discovery.workspace.v3'
const LEGACY_V2_KEY = 'medicalchannelai.discovery.workspace.v2'
const ACCOUNT_BOOTSTRAP_PREFIX = 'medicalchannelai.discovery.workspace.account.v2.'
const UNOWNED_BOOTSTRAP_KEY = 'medicalchannelai.discovery.workspace.unowned.v2.bootstrap'
const UNOWNED_V3_KEY = 'medicalchannelai.discovery.workspace.unowned.v2.v3'
const UNOWNED_V2_KEY = 'medicalchannelai.discovery.workspace.unowned.v2.v2'

const DB_NAME = 'medicalchannelai.discovery.local'
const DB_VERSION = 1
const DB_STORE = 'workspace'
const LEGACY_DB_KEY = 'current'
const ACCOUNT_DB_PREFIX = 'account-v2:'
const UNOWNED_DB_KEY = 'legacy-unowned-v2'

let activeAccountToken = null

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

export function discoveryWorkspaceIsAccountScoped() {
  return typeof activeAccountToken === 'string' && activeAccountToken.length > 0
}

export function discoveryWorkspaceStorageKey() {
  return activeAccountToken
    ? `${ACCOUNT_BOOTSTRAP_PREFIX}${activeAccountToken}`
    : LEGACY_BOOTSTRAP_KEY
}

export function discoveryWorkspaceDbKey() {
  return activeAccountToken
    ? `${ACCOUNT_DB_PREFIX}${activeAccountToken}`
    : LEGACY_DB_KEY
}

function browserLocalStorage() {
  if (typeof window === 'undefined' || !window.localStorage) {
    throw new Error('DISCOVERY_ACCOUNT_LOCAL_STORAGE_UNAVAILABLE')
  }
  return window.localStorage
}

function archiveLocal(storage, sourceKey, archiveKey) {
  const value = storage.getItem(sourceKey)
  if (value === null) return
  if (storage.getItem(archiveKey) === null) storage.setItem(archiveKey, value)
  storage.removeItem(sourceKey)
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

async function quarantineLegacyIndexedWorkspace() {
  if (!indexedDbAvailable()) return
  const db = await openDb()
  try {
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(DB_STORE, 'readwrite')
      const store = transaction.objectStore(DB_STORE)
      const currentRequest = store.get(LEGACY_DB_KEY)
      const archiveRequest = store.get(UNOWNED_DB_KEY)
      let currentReady = false
      let archiveReady = false
      let currentValue
      let archiveValue

      const apply = () => {
        if (!currentReady || !archiveReady) return
        if (currentValue !== undefined && archiveValue === undefined) {
          store.put(currentValue, UNOWNED_DB_KEY)
        }
        store.delete(LEGACY_DB_KEY)
      }

      currentRequest.onsuccess = () => {
        currentValue = currentRequest.result
        currentReady = true
        apply()
      }
      archiveRequest.onsuccess = () => {
        archiveValue = archiveRequest.result
        archiveReady = true
        apply()
      }
      currentRequest.onerror = () => reject(currentRequest.error ?? new Error('DISCOVERY_ACCOUNT_DB_READ_FAILED'))
      archiveRequest.onerror = () => reject(archiveRequest.error ?? new Error('DISCOVERY_ACCOUNT_DB_READ_FAILED'))
      transaction.oncomplete = () => resolve()
      transaction.onerror = () => reject(transaction.error ?? new Error('DISCOVERY_ACCOUNT_DB_QUARANTINE_FAILED'))
      transaction.onabort = () => reject(transaction.error ?? new Error('DISCOVERY_ACCOUNT_DB_QUARANTINE_ABORTED'))
    })
  } finally {
    db.close()
  }
}

async function deleteDbValue(key) {
  if (!indexedDbAvailable()) return
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

export async function activateDiscoveryWorkspaceForAccount(username) {
  const token = discoveryAccountToken(username)
  const storage = browserLocalStorage()

  // Pre-account Radar data has no trustworthy owner. Preserve it for audit/recovery
  // but never assign it to the first authenticated account.
  archiveLocal(storage, LEGACY_BOOTSTRAP_KEY, UNOWNED_BOOTSTRAP_KEY)
  archiveLocal(storage, LEGACY_V3_KEY, UNOWNED_V3_KEY)
  archiveLocal(storage, LEGACY_V2_KEY, UNOWNED_V2_KEY)
  await quarantineLegacyIndexedWorkspace()

  activeAccountToken = token
  return token
}

export async function clearActiveDiscoveryWorkspaceAccount() {
  const token = activeAccountToken
  activeAccountToken = null
  if (!token) return

  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      window.localStorage.removeItem(`${ACCOUNT_BOOTSTRAP_PREFIX}${token}`)
    }
  } catch {
    // Server deletion has already succeeded. Failure to remove the local fallback
    // does not expose it because no future account uses this account-scoped key.
  }

  try {
    await deleteDbValue(`${ACCOUNT_DB_PREFIX}${token}`)
  } catch {
    // Same boundary as above: the orphan remains keyed only to the deleted token.
  }
}
