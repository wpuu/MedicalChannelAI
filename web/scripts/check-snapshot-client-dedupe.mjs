// Guards against re-introducing redundant full-snapshot downloads in the
// browser. All demo-mode consumers must go through verifiedSnapshotClient.ts,
// which dedupes in-flight requests and reuses the parsed payload briefly.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const srcDir = join(root, 'src')
const clientPath = join(srcDir, 'services', 'verifiedSnapshotClient.ts')
const failures = []

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    return statSync(full).isDirectory() ? walk(full) : /\.(ts|vue)$/.test(name) ? [full] : []
  })
}

for (const file of walk(srcDir)) {
  if (file === clientPath) continue
  const source = readFileSync(file, 'utf8')
  if (/fetch\(\s*(verifiedSnapshotUrl|this\.snapshotUrl|snapshotUrl)\b/.test(source)) {
    failures.push(`${relative(root, file)} fetches the verified snapshot directly; use loadVerifiedSnapshotPayload()`)
  }
}

const client = readFileSync(clientPath, 'utf8')
if (!client.includes("cache: 'no-cache'")) failures.push('verifiedSnapshotClient must revalidate with cache: no-cache')
if (client.includes("'no-store'")) failures.push('verifiedSnapshotClient must not bypass the HTTP cache with no-store')
if (!/SNAPSHOT_CLIENT_TTL_MS\s*=\s*\d/.test(client)) failures.push('verifiedSnapshotClient must define SNAPSHOT_CLIENT_TTL_MS')
if (!/if \(entry === created\) entry = null/.test(client)) failures.push('verifiedSnapshotClient must not memoize failed loads')

const consumers = {
  'services/verifiedOpportunityPool.ts': /loadVerifiedSnapshot(?:Payload)?\(/,
  'services/StaticSnapshotTodayActionsService.ts': /loadVerifiedSnapshot(?:Payload)?\(/,
}
for (const [path, symbol] of Object.entries(consumers)) {
  const source = readFileSync(join(srcDir, path), 'utf8')
  const found = symbol instanceof RegExp ? symbol.test(source) : source.includes(symbol)
  if (!found) failures.push(`${path} must use the shared verifiedSnapshotClient loader`)
}

const aiClient = readFileSync(join(srcDir, 'services', 'aiDecisionApi.ts'), 'utf8')
if (!aiClient.includes('snapshotProvenance(card.snapshot_meta)')) {
  failures.push('aiDecisionApi must key decisions from each input card snapshot_meta')
}
if (/getVerifiedSnapshotAsOf|verifiedSnapshotUrl/.test(aiClient)) {
  failures.push('aiDecisionApi must not use a later global snapshot clock to validate or hydrate an older card')
}

if (failures.length) {
  console.error('Snapshot client dedupe check failed:\n- ' + failures.join('\n- '))
  process.exit(1)
}
console.log('Snapshot client dedupe check passed.')
