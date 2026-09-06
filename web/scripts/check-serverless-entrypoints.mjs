import { readdirSync, readFileSync, statSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { dirname, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const webRoot = resolve(scriptDir, '..')
const apiRoot = resolve(webRoot, 'api')
const hobbyFunctionLimit = 12

function walk(directory) {
  const files = []
  for (const name of readdirSync(directory)) {
    const path = resolve(directory, name)
    const stat = statSync(path)
    if (stat.isDirectory()) files.push(...walk(path))
    else files.push(path)
  }
  return files
}

const files = walk(apiRoot)
for (const path of files.filter((item) => item.endsWith('.js'))) {
  const result = spawnSync(process.execPath, ['--check', path], {
    cwd: webRoot,
    stdio: 'inherit',
  })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error(`SERVERLESS_SYNTAX_INVALID:${relative(webRoot, path)}`)
  }
}

const authContract = spawnSync(
  process.execPath,
  [
    '--input-type=module',
    '--eval',
    `
      const auth = await import('./api/_auth.js')
      if (auth.normalizeInviteCode('ab12cd') !== 'AB12CD') throw new Error('SHORT_INVITE_NORMALIZATION_FAILED')
      if (auth.normalizeInviteCode('AB12CD34') !== 'AB12CD34') throw new Error('SHORT_INVITE_8_INVALID')
      if (auth.normalizeInviteCode('ABCDE') !== null) throw new Error('SHORT_INVITE_TOO_SHORT_ACCEPTED')
      if (auth.normalizeInviteCode('ABCDEFGHI') !== null) throw new Error('SHORT_INVITE_TOO_LONG_ACCEPTED')
      await import('./api/auth.js')
    `,
  ],
  {
    cwd: webRoot,
    stdio: 'inherit',
    env: process.env,
  },
)
if (authContract.error) throw authContract.error
if (authContract.status !== 0) {
  throw new Error(`SERVERLESS_AUTH_MODULE_CONTRACT_INVALID:exit_${authContract.status}`)
}

const deployable = files
  .filter((path) => path.endsWith('.js') || path.endsWith('.py'))
  .map((path) => relative(apiRoot, path))
  .filter((path) => !path.split(sep).some((part) => part.startsWith('_')))
  .sort()

if (deployable.length > hobbyFunctionLimit) {
  throw new Error(
    `VERCEL_HOBBY_FUNCTION_LIMIT_EXCEEDED:${deployable.length}/${hobbyFunctionLimit}:${deployable.join(',')}`,
  )
}

const config = JSON.parse(readFileSync(resolve(webRoot, 'vercel.json'), 'utf8'))
const rewriteMap = new Map(
  (Array.isArray(config.rewrites) ? config.rewrites : [])
    .filter((item) => item && typeof item === 'object')
    .map((item) => [item.source, item.destination]),
)
const requiredRewrites = new Map([
  ['/api/auth/register', '/api/auth?route=register'],
  ['/api/auth/login', '/api/auth?route=login'],
  ['/api/auth/logout', '/api/auth?route=logout'],
  ['/api/auth/me', '/api/auth?route=me'],
  ['/api/today', '/api/private?route=today'],
  ['/api/opportunity/:id', '/api/private?route=opportunity&id=:id'],
  ['/api/followup/:id', '/api/private?route=followup&id=:id'],
  ['/api/followed', '/api/private?route=followed'],
  ['/api/feedback/:id', '/api/private?route=feedback&id=:id'],
])
for (const [source, destination] of requiredRewrites) {
  if (rewriteMap.get(source) !== destination) {
    throw new Error(`PRIVATE_API_REWRITE_INVALID:${source}`)
  }
}

console.log(`Serverless entrypoints: PASS (${deployable.length}/${hobbyFunctionLimit} functions)`)
