export const DEFAULT_TODAY_LIMIT = 5
export const ALLOWED_TODAY_LIMITS = Object.freeze([3, 5, 8, 10, 15])

export function normalizeTodayLimit(value) {
  const number = Number(value)
  return ALLOWED_TODAY_LIMITS.includes(number) ? number : null
}

export async function ensureTodayDisplayPreferenceSchema(sql) {
  await sql`
    CREATE TABLE IF NOT EXISTS private_user_ui_preferences (
      user_id UUID PRIMARY KEY REFERENCES private_users(id) ON DELETE CASCADE,
      today_limit SMALLINT NOT NULL DEFAULT 5 CHECK (today_limit IN (3, 5, 8, 10, 15)),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
  `
}

export async function todayLimitForUser(sql, user) {
  const rows = await sql`
    SELECT today_limit
    FROM private_user_ui_preferences
    WHERE user_id = ${user.id}
    LIMIT 1
  `
  return normalizeTodayLimit(rows[0]?.today_limit) ?? DEFAULT_TODAY_LIMIT
}

export async function setTodayLimitForUser(sql, user, value) {
  const todayLimit = normalizeTodayLimit(value)
  if (todayLimit === null) return null
  await sql`
    INSERT INTO private_user_ui_preferences (user_id, today_limit, updated_at)
    VALUES (${user.id}, ${todayLimit}, now())
    ON CONFLICT (user_id) DO UPDATE SET
      today_limit = EXCLUDED.today_limit,
      updated_at = now()
  `
  return todayLimit
}
