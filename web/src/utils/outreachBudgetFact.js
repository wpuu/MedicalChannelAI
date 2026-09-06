export function outreachBudgetFactText(value) {
  const budget = Number(value)
  if (!Number.isFinite(budget) || budget <= 0) return null
  if (budget < 10_000) return `项目预算约${Math.round(budget)}元`
  const wan = budget / 10_000
  const decimals = wan < 10 ? 2 : wan < 100 ? 1 : 0
  return `项目预算约${Number(wan.toFixed(decimals))}万元`
}
