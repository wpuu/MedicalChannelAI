import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { safeTelephoneHref } from '../src/utils/safeTelephoneLinks.js'

assert.equal(safeTelephoneHref('022-23717450-8002'), 'tel:02223717450,8002')
assert.equal(safeTelephoneHref('电话 022-28227838-803'), 'tel:02228227838,803')
assert.equal(safeTelephoneHref('022-23717450'), 'tel:02223717450')
assert.equal(safeTelephoneHref('400-123-4567'), 'tel:4001234567')
assert.equal(safeTelephoneHref('+86 22 23717450 转 8002'), 'tel:+862223717450,8002')
assert.equal(safeTelephoneHref('022-23717450、022-28227838'), null)
assert.equal(safeTelephoneHref('张老师'), null)

const scriptDir = dirname(fileURLToPath(import.meta.url))
const main = readFileSync(resolve(scriptDir, '../src/main.tsx'), 'utf8')
assert(main.includes('installSafeTelephoneLinks()'))

for (const relativePath of [
  '../src/components/today/ActionCard.tsx',
  '../src/components/opportunity/FactsCard.tsx',
  '../src/pages/OpportunityPoolPage.tsx',
]) {
  const source = readFileSync(resolve(scriptDir, relativePath), 'utf8')
  assert(source.includes('href={contactPhoneHref}'))
}

console.log('Safe telephone dialing checks: PASS')
