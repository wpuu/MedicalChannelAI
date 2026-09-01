import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const pipelineDir = resolve(scriptDir, '../pipeline')
const unittestArgs = ['-m', 'unittest', 'discover', '-s', 'tests', '-v']
const refreshArgs = ['scripts/refresh_bundled_snapshot.py']

const candidates = []
if (process.env.PYTHON) candidates.push([process.env.PYTHON, []])
candidates.push(
  ['python3', []],
  ['python', []],
  ['py', ['-3']],
)

let pythonRan = false
for (const [command, prefixArgs] of candidates) {
  const refresh = spawnSync(command, [...prefixArgs, ...refreshArgs], {
    cwd: pipelineDir,
    stdio: 'inherit',
    env: process.env,
  })
  if (refresh.error?.code === 'ENOENT') continue
  if (refresh.error) throw refresh.error
  pythonRan = true
  if (refresh.status !== 0) {
    throw new Error(`BUNDLED_SNAPSHOT_REFRESH_FAILED:${command}:exit_${refresh.status}`)
  }

  const result = spawnSync(command, [...prefixArgs, ...unittestArgs], {
    cwd: pipelineDir,
    stdio: 'inherit',
    env: process.env,
  })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error(`PIPELINE_UNITTEST_FAILED:${command}:exit_${result.status}`)
  }
  break
}

if (!pythonRan) {
  throw new Error('PYTHON_RUNTIME_NOT_FOUND_FOR_PIPELINE_TESTS')
}

await import('./check-verified-snapshot.mjs')
await import('./check-medical-channel-scope.mjs')
await import('./check-ai-decision-contract.mjs')
await import('./check-mobile-first-ui.mjs')
await import('./check-runtime-status.mjs')
await import('./check-ai-boundary.mjs')
console.log('Prebuild verification: PASS')
