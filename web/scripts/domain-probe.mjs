import { promises as dns } from 'node:dns'
import https from 'node:https'
import { createHash } from 'node:crypto'

const host = 'medicalai.qd.je'
const targets = [
  ['custom', 'https://medicalai.qd.je'],
  ['vercel-default', 'https://medicalchannelai.vercel.app'],
  ['vercel-project', 'https://medicalchannelai-rerisse7-1717s-projects.vercel.app'],
  ['vercel-main-alias', 'https://medicalchannelai-git-main-rerisse7-1717s-projects.vercel.app'],
]

async function safeResolve(label, fn) {
  try {
    const value = await fn()
    console.log('[domain-probe:dns]', JSON.stringify({ label, value }))
  } catch (error) {
    console.log('[domain-probe:dns]', JSON.stringify({ label, error: error?.code || error?.message || String(error) }))
  }
}

await safeResolve('A', () => dns.resolve4(host))
await safeResolve('AAAA', () => dns.resolve6(host))
await safeResolve('CNAME', () => dns.resolveCname(host))

for (const [label, base] of targets) {
  for (const path of ['/', '/api/status']) {
    try {
      const response = await fetch(`${base}${path}`, { redirect: 'manual' })
      const text = await response.text()
      const title = text.match(/<title[^>]*>([^<]*)<\/title>/i)?.[1] ?? null
      const sha256 = createHash('sha256').update(text).digest('hex')
      console.log('[domain-probe:compare]', JSON.stringify({
        label,
        path,
        status: response.status,
        content_type: response.headers.get('content-type'),
        server: response.headers.get('server'),
        via: response.headers.get('via'),
        location: response.headers.get('location'),
        x_vercel_id: response.headers.get('x-vercel-id'),
        x_vercel_cache: response.headers.get('x-vercel-cache'),
        title,
        bytes: Buffer.byteLength(text),
        sha256,
      }))
    } catch (error) {
      console.log('[domain-probe:compare]', JSON.stringify({ label, path, error: error?.message || String(error), cause: error?.cause?.code || null }))
    }
  }
}

await new Promise((resolve) => {
  const request = https.get({ hostname: host, path: '/', method: 'HEAD' }, (response) => {
    const socket = response.socket
    const cert = socket.getPeerCertificate?.() || {}
    console.log('[domain-probe:tls]', JSON.stringify({
      status: response.statusCode,
      remote_address: socket.remoteAddress || null,
      alpn: socket.alpnProtocol || null,
      cert_subject_cn: cert.subject?.CN || null,
      cert_issuer_cn: cert.issuer?.CN || null,
      cert_valid_to: cert.valid_to || null,
    }))
    response.resume()
    response.on('end', resolve)
  })
  request.on('error', (error) => {
    console.log('[domain-probe:tls]', JSON.stringify({ error: error?.message || String(error), code: error?.code || null }))
    resolve()
  })
  request.setTimeout(10000, () => request.destroy(new Error('TLS_PROBE_TIMEOUT')))
})
