let installed = false

function cleanedPhoneText(value) {
  return String(value || '')
    .trim()
    .replace(/^电话\s*[:：]?\s*/i, '')
    .trim()
}

function splitExtension(raw) {
  const named = raw.match(/^(.*?)(?:\s*(?:转|分机|ext(?:ension)?\.?)\s*[:：-]?\s*)(\d{1,6})$/i)
  if (named) return { base: named[1].trim(), extension: named[2] }

  const parts = raw.split(/[-—–]/).map((part) => part.trim()).filter(Boolean)
  if (parts.length < 3) return { base: raw, extension: null }
  const tail = parts.at(-1)
  if (!tail || !/^\d{1,6}$/.test(tail)) return { base: raw, extension: null }
  const base = parts.slice(0, -1).join('-')
  const baseDigits = base.replace(/\D/g, '')
  if (baseDigits.length < 10) return { base: raw, extension: null }
  return { base, extension: tail }
}

export function safeTelephoneHref(value) {
  const raw = cleanedPhoneText(value)
  if (!raw || /[、,，;；/]/.test(raw)) return null

  const { base, extension } = splitExtension(raw)
  const leadingPlus = base.trim().startsWith('+')
  const digits = base.replace(/\D/g, '')
  if (digits.length < 5) return null
  return `tel:${leadingPlus ? '+' : ''}${digits}${extension ? `,${extension}` : ''}`
}

export function installSafeTelephoneLinks() {
  if (installed || typeof document === 'undefined') return
  installed = true
  document.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof Element)) return
    const anchor = target.closest('a[href^="tel:"]')
    if (!(anchor instanceof HTMLAnchorElement)) return
    const safeHref = safeTelephoneHref(anchor.textContent)
    if (!safeHref || anchor.getAttribute('href') === safeHref) return
    event.preventDefault()
    window.location.href = safeHref
  }, true)
}
