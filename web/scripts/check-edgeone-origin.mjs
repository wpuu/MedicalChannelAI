import assert from 'node:assert/strict'
import indexHandler from '../../ops/edgeone-cn-proxy/edge-functions/index.js'
import catchAllHandler from '../../ops/edgeone-cn-proxy/edge-functions/[[default]].js'

const origin = 'https://medicalchannelai.vercel.app'
const savedFetch = globalThis.fetch
try {
  for (const handler of [indexHandler, catchAllHandler]) {
    let calls = []
    globalThis.fetch = async (url, init) => {
      calls.push({ url: String(url), init })
      return new Response('upstream', { status: 200 })
    }
    for (const path of [
      '//outside.example/collect',
      '/%2foutside.example/collect',
      '/%2f%2foutside.example/collect',
      '/%5coutside.example/collect',
      '/bad%escape',
    ]) {
      const response = await handler({ request: new Request(`https://medicalai.qd.je${path}`, {
        headers: { Cookie: 'session=test-only', Authorization: 'Bearer test-only' },
      }) })
      assert.equal(response.status, 400, path)
    }
    assert.equal(calls.length, 0, 'invalid paths must not forward credentials')

    await handler({ request: new Request('https://medicalai.qd.je/') })
    assert.equal(calls.pop().url, `${origin}/today`)
    await handler({ request: new Request('https://medicalai.qd.je/api/example?q=one&q=two&eo_token=discard&eo_time=discard', {
      method: 'POST',
      body: 'test payload',
      headers: { Cookie: 'session=test-only', Authorization: 'Bearer test-only' },
    }) })
    const forwarded = calls.pop()
    assert.equal(forwarded.url, `${origin}/api/example?q=one&q=two`)
    assert.equal(forwarded.init.headers.cookie, 'session=test-only')
    assert.equal(forwarded.init.headers.authorization, 'Bearer test-only')
    assert.equal(new TextDecoder().decode(forwarded.init.body), 'test payload')
    assert.equal(forwarded.init.redirect, 'manual')

    for (const [location, expected] of [
      [`${origin}/today?next=1`, 'https://medicalai.qd.je/today?next=1'],
      ['https://outside.example/redirect', 'https://outside.example/redirect'],
    ]) {
      globalThis.fetch = async (url, init) => {
        assert.equal(new URL(url).origin, origin)
        assert.equal(init.redirect, 'manual', 'upstream redirects must never forward credentials automatically')
        calls.push({ url, init })
        return new Response(null, { status: 302, headers: { Location: location } })
      }
      const before = calls.length
      const response = await handler({ request: new Request('https://medicalai.qd.je/today', {
        headers: { Authorization: 'Bearer test-only' },
      }) })
      assert.equal(calls.length, before + 1)
      assert.equal(response.headers.get('location'), expected)
    }
    globalThis.fetch = async () => { throw new Error('sensitive-upstream-detail') }
    const failed = await handler({ request: new Request('https://medicalai.qd.je/today') })
    assert.equal(failed.status, 502)
    assert.ok(!(await failed.text()).includes('sensitive-upstream-detail'))
  }
} finally {
  globalThis.fetch = savedFetch
}
console.log('EdgeOne fixed-origin forwarding: PASS')
