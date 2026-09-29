/**
 * Matching key for project numbers across notices (mirror of
 * `ccgp_award.normalize_project_number` in the Python pipeline).
 *
 * Tender and result notices for the same project are typed by different
 * clerks: full-width brackets/dashes (`HBHX（Z）-2026-019` vs `HBHX(Z)-2026-019`),
 * stray spaces and letter case all occur. The displayed value is never changed.
 */
export function normalizeProjectNumber(value: string | null | undefined): string {
  if (!value) return ''
  let text = ''
  for (const char of String(value)) {
    const code = char.codePointAt(0) ?? 0
    if (code === 0x3000) text += ' '
    else if (code >= 0xff01 && code <= 0xff5e) text += String.fromCodePoint(code - 0xfee0)
    else text += char
  }
  return text.replace(/\s+/g, '').toLowerCase()
}
