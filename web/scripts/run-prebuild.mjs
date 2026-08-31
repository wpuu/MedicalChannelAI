import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const pipelineDir = resolve(scriptDir, '../../pipeline')
const unittestArgs = ['-m', 'unittest', 'discover', '-s', 'tests', '-v']

const candidates = []
if (process.env.PYTHON) candidates.push([process.env.PYTHON, unittestArgs])
candidates.push(
  ['python3', unittestArgs],
  ['python', unittestArgs],
  ['py', ['-3', ...unittestArgs]],
)

let pythonRan = false
for (const [command, args] of candidates) {
  const result = spawnSync(command, args, {
    cwd: pipelineDir,
    stdio: 'inherit',
    env: process.env,
  })
  if (result.error?.code === 'ENOENT') continue
  if (result.error) throw result.error
  pythonRan = true
  if (result.status !== 0) {
    throw new Error(`PIPELINE_UNITTEST_FAILED:${command}:exit_${result.status}`)
  }
  break
}

if (!pythonRan) {
  throw new Error('PYTHON_RUNTIME_NOT_FOUND_FOR_PIPELINE_TESTS')
}

await import('./check-ai-boundary.mjs')
console.log('Prebuild verification: PASS')
