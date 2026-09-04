import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const scriptDir = dirname(fileURLToPath(import.meta.url))
const pipelineDir = resolve(scriptDir, '../pipeline')
const unittestArgs = ['-m', 'unittest', 'discover', '-s', 'tests', '-v']
const refreshArgs = ['scripts/refresh_bundled_snapshot.py']

function verifyPilotDeploymentEnvironment() {
  const buildMode = String(process.env.VITE_BUILD_MODE || '').trim().toLowerCase()
  if (buildMode !== 'pilot') return

  const missing = []
  const apiBaseUrl = String(process.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '')
  if (apiBaseUrl !== '/api') missing.push('VITE_API_BASE_URL=/api')
  if (String(process.env.PILOT_PRIVATE_ACCOUNTS_ENABLED || '').trim() !== '1') {
    missing.push('PILOT_PRIVATE_ACCOUNTS_ENABLED=1')
  }
  if (!String(process.env.DATABASE_URL || process.env.POSTGRES_URL || '').trim()) {
    missing.push('DATABASE_URL_OR_POSTGRES_URL')
  }
  const inviteCodes = String(process.env.PILOT_INVITE_CODES || '')
    .split(/[\n,;]+/)
    .map((value) => value.trim())
    .filter(Boolean)
  if (!inviteCodes.some((value) => value.length >= 24)) {
    missing.push('PILOT_INVITE_CODES')
  }

  if (missing.length > 0) {
    throw new Error(`PILOT_DEPLOYMENT_ENV_INCOMPLETE:${missing.join(',')}`)
  }
  console.log('Pilot deployment environment contract: PASS')
}

function verifyPreviewSmokeSyntax() {
  const scriptPath = resolve(scriptDir, 'pilot-preview-smoke.mjs')
  const result = spawnSync(process.execPath, ['--check', scriptPath], {
    stdio: 'inherit',
    env: process.env,
  })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error(`PILOT_PREVIEW_SMOKE_SYNTAX_FAILED:exit_${result.status}`)
  }
  console.log('Pilot Preview smoke syntax: PASS')
}

verifyPilotDeploymentEnvironment()
verifyPreviewSmokeSyntax()

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

await import('./check-serverless-entrypoints.mjs')
await import('./check-verified-snapshot.mjs')
await import('./check-medical-channel-scope.mjs')
await import('./check-private-profile-matching.mjs')
await import('./check-ai-decision-contract.mjs')
await import('./check-relative-window-boundary.mjs')
await import('./check-runtime-opportunity-time.mjs')
await import('./check-mobile-first-ui.mjs')
await import('./check-pre-market-signal-ui.mjs')
await import('./check-phone-dialing.mjs')
await import('./check-trial-outreach-parity.mjs')
await import('./check-radar-account-isolation.mjs')
await import('./check-continuation-account-isolation.mjs')
await import('./check-account-session-isolation.mjs')
await import('./check-account-local-scope.mjs')
await import('./check-local-profile-migration-safety.mjs')
await import('./check-runtime-status.mjs')
await import('./check-ai-boundary.mjs')
await import('./check-source-quality-boundary.mjs')
console.log('Prebuild verification: PASS')