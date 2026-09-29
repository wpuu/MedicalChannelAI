import type { DeviceFamily } from '@/types'

/**
 * Mirror of `medical_channel_pipeline/device_families.py`.
 *
 * The taxonomy itself is shipped in the snapshot (`award_price_reference.families`)
 * so both sides classify with the same ordered table: first family whose
 * keyword is contained in the normalised name, or whose acronym appears as a
 * whole Latin/digit token (`CT` must not match inside `CBCT`). Display aid for
 * 成交价参考 only — never scope, ranking or actionability.
 */

const FULLWIDTH_START = 0xff01
const FULLWIDTH_END = 0xff5e

export function normalizeDeviceName(value: unknown): string {
  const text = String(value ?? '')
  let out = ''
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0
    if (code >= FULLWIDTH_START && code <= FULLWIDTH_END) out += String.fromCodePoint(code - 0xfee0)
    else if (code === 0x3000) out += ' '
    else out += char
  }
  return out.toUpperCase().replace(/\s+/g, ' ').trim()
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function acronymPresent(name: string, acronym: string): boolean {
  if (!acronym) return false
  return new RegExp(`(?<![A-Z0-9])${escapeRegExp(acronym)}(?![A-Z0-9])`).test(name)
}

export function deviceFamilyForName(value: unknown, families: readonly DeviceFamily[] | null | undefined): string | null {
  const name = normalizeDeviceName(value)
  if (!name || !families?.length) return null
  for (const family of families) {
    if (family.keywords.some((keyword) => keyword && name.includes(normalizeDeviceName(keyword)))) return family.code
    if (family.acronyms.some((acronym) => acronymPresent(name, normalizeDeviceName(acronym)))) return family.code
  }
  return null
}

export function deviceFamilyLabel(code: string | null | undefined, families: readonly DeviceFamily[] | null | undefined): string | null {
  if (!code) return null
  return families?.find((family) => family.code === code)?.label ?? null
}

/** Distinct families of an opportunity's 标的 names (order of first appearance). */
export function deviceFamiliesForNames(
  names: readonly (string | null | undefined)[],
  families: readonly DeviceFamily[] | null | undefined,
): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const name of names) {
    const code = deviceFamilyForName(name, families)
    if (code && !seen.has(code)) {
      seen.add(code)
      out.push(code)
    }
  }
  return out
}
