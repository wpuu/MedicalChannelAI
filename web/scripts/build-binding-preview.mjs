import { spawnSync } from 'node:child_process'
import { checkPreviewBinding, DIAGNOSTIC_BRANCH } from '../api/_previewBindingCheck.js'

if (process.env.VERCEL_ENV !== 'preview' || process.env.VERCEL_GIT_COMMIT_REF !== DIAGNOSTIC_BRANCH) {
  throw new Error('BINDING_DIAGNOSTIC_BUILD_REQUIRES_APPROVED_PREVIEW_BRANCH')
}
// This diagnostic branch deliberately skips data refresh and the historical
// prebuild tests. Build only; never pass deployment secrets to build children.
const allowedKeys = ['PATH', 'HOME', 'TMPDIR', 'NODE_ENV', 'LANG', 'CI']
const buildEnv = Object.fromEntries(allowedKeys.filter(key => process.env[key] !== undefined)
  .map(key => [key, process.env[key]]))
for (const entry of ['typescript/bin/tsc', 'vite/bin/vite.js']) {
  const args = entry.startsWith('typescript') ? ['--noEmit'] : ['build']
  const result = spawnSync(process.execPath, [`node_modules/${entry}`, ...args], {
    stdio: 'inherit', env: buildEnv,
  })
  if (result.error || result.status !== 0) throw new Error('BINDING_PREVIEW_COMPILATION_FAILED')
}
// Imported core has no DB driver import or effects; this reference ensures
// packaging catches a missing diagnostic module without opening a connection.
if (typeof checkPreviewBinding !== 'function') throw new Error('BINDING_DIAGNOSTIC_MISSING')
