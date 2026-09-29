import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, resolve } from 'node:path'
import { transformWithEsbuild } from 'vite'

// The device-family classifier exists twice (Python builds the snapshot, the
// web client relates an opportunity's 标的 to 成交价参考 rows). Both must agree
// on every parity vector of the shared taxonomy, and the bundled snapshot must
// ship exactly that taxonomy.
const scriptDir = dirname(fileURLToPath(import.meta.url))
const taxonomyPath = resolve(scriptDir, '../pipeline/data/device_families.json')
const taxonomy = JSON.parse(readFileSync(taxonomyPath, 'utf8'))
const sourcePath = resolve(scriptDir, '../src/utils/deviceFamily.ts')
const transformed = await transformWithEsbuild(readFileSync(sourcePath, 'utf8'), sourcePath, { loader: 'ts', format: 'esm' })
const moduleUrl = `data:text/javascript;base64,${Buffer.from(transformed.code, 'utf8').toString('base64')}`
const { deviceFamilyForName, deviceFamiliesForNames, normalizeDeviceName } = await import(moduleUrl)

const families = taxonomy.families
assert(Array.isArray(families) && families.length >= 20, 'taxonomy must list device families')
assert(Array.isArray(taxonomy.parity_vectors) && taxonomy.parity_vectors.length >= 30, 'taxonomy must carry parity vectors')

for (const [name, expected] of taxonomy.parity_vectors) {
  assert.equal(deviceFamilyForName(name, families), expected, `device family parity failed for "${name}"`)
}
assert.equal(deviceFamilyForName('CBCT', families), 'DENTAL')
assert.equal(deviceFamilyForName('DRY BOX', families), null)
assert.equal(deviceFamilyForName('ｍｒｉ 系统', families), 'MRI')
assert.equal(normalizeDeviceName('　彩色　多普勒（Ｘ）'), '彩色 多普勒(X)')
assert.deepEqual(deviceFamiliesForNames(['彩色多普勒超声诊断仪', '彩超', '麻醉机', null], families), ['ULTRASOUND', 'ANESTHESIA_RESP'])

// The snapshot ships the same ordered taxonomy the client classifies with.
const snapshot = JSON.parse(readFileSync(resolve(scriptDir, '../public/data/today-actions.public.json'), 'utf8'))
const reference = snapshot.award_price_reference
assert(reference && typeof reference === 'object', 'snapshot must embed award_price_reference')
assert.deepEqual(
  reference.families.map((family) => family.code),
  families.map((family) => family.code),
  'snapshot taxonomy order must match pipeline/data/device_families.json',
)
assert.equal(reference.row_count, reference.rows.length)
for (const row of reference.rows) {
  assert(Number.isInteger(row.unit_price_cny) && row.unit_price_cny > 0, 'reference rows carry a positive unit price')
  assert(typeof row.brand === 'string' && row.brand.length > 0, 'reference rows carry a single brand')
  assert(!/[;；、]/.test(row.brand), `multi-valued brand leaked into reference: ${row.brand}`)
  assert(/^https:\/\/www\.ccgp\.gov\.cn\//.test(row.source_url), 'reference rows link to the official notice')
  assert.equal(row.family, deviceFamilyForName(row.name, families), `client/pipeline family mismatch for "${row.name}"`)
}

console.log(`device family parity ok (${taxonomy.parity_vectors.length} vectors, ${reference.row_count} reference rows)`)
export {}
