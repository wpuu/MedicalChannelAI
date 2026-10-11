export const FROZEN_CANDIDATE = '69082cbc058704a330a1cea68d0514a2f5971c45'
export const DIAGNOSTIC_BRANCH = 'test/medical-preview-binding-20261011'

export async function checkPreviewBinding(method, env, connect) {
  const commit = /^[a-f0-9]{40}$/.test(env.VERCEL_GIT_COMMIT_SHA || '')
    ? env.VERCEL_GIT_COMMIT_SHA : null
  const base = {
    schema_version: 'medical-preview-binding-v1',
    frozen_candidate: FROZEN_CANDIDATE,
    deployed_commit: commit,
    matches_neondb: null,
    transaction_read_only: null,
    stopped: true,
  }
  const result = (status, diagnostic, extra = {}) => ({
    status, body: { ...base, diagnostic, ...extra },
  })
  if (method !== 'GET') return result(405, 'GET_ONLY')
  if (env.VERCEL_ENV !== 'preview' || env.VERCEL_GIT_COMMIT_REF !== DIAGNOSTIC_BRANCH) {
    return result(404, 'PREVIEW_BRANCH_REQUIRED')
  }
  if (!commit) return result(503, 'DEPLOYED_COMMIT_UNCONFIRMED')
  // Exactly the same URL precedence as privateDb; do not import that helper:
  // other application helpers can initialize schemas or read business tables.
  const url = String(env.DATABASE_URL || env.POSTGRES_URL || '').trim()
  if (!url) return result(503, 'DATABASE_BINDING_UNCONFIGURED')

  let sql
  try {
    sql = connect(url, {
      max: 1, idle_timeout: 1, connect_timeout: 5, prepare: false,
      ssl: 'require',
      connection: {
        default_transaction_read_only: 'on',
        statement_timeout: '5000',
        lock_timeout: '1000',
      },
    })
    const rows = await sql.begin('read only', async (transaction) => transaction`
      SELECT current_database() = 'neondb' AS matches_neondb,
             current_setting('transaction_read_only') = 'on' AS transaction_read_only
    `)
    const row = rows?.[0]
    if (typeof row?.matches_neondb !== 'boolean' || row.transaction_read_only !== true) {
      return result(503, 'READ_ONLY_BINDING_UNCONFIRMED')
    }
    if (!row.matches_neondb) {
      return result(409, 'DATABASE_BINDING_MISMATCH_STOP', {
        matches_neondb: false, transaction_read_only: true,
      })
    }
    return result(200, 'NEONDB_BINDING_CONFIRMED', {
      matches_neondb: true, transaction_read_only: true, stopped: false,
    })
  } catch {
    // Never return driver errors: they can contain credentials or host names.
    return result(503, 'DATABASE_BINDING_UNCONFIRMED_STOP')
  } finally {
    if (sql) await sql.end({ timeout: 1 }).catch(() => {})
  }
}
