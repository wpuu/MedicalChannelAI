import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const card = readFileSync(resolve(scriptDir, '../src/components/profile/LocalProfileImportCard.tsx'), 'utf8')

const saveIndex = card.indexOf('const saved = await saveCustomerProfile(merged)')
const clearIndex = card.indexOf('clearImportedLocalProfile()', saveIndex)
const hideIndex = card.indexOf('setLocalProfile(null)', clearIndex)
const callbackIndex = card.indexOf('onImported(saved)', hideIndex)
assert(saveIndex >= 0)
assert(clearIndex > saveIndex)
assert(hideIndex > clearIndex)
assert(callbackIndex > hideIndex)
assert(card.includes('云端保存成功后，本机旧副本会自动清除'))
assert(card.includes('避免以后被其他账号重复导入'))
assert(card.includes("toast('导入失败；本机数据和账号原数据都未被删除')"))

console.log('Local profile migration consumption checks: PASS')
