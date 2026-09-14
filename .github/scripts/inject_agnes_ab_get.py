import json
import sys
from pathlib import Path

app = Path(sys.argv[1])
root = app / 'web/pipeline/data'
positives_src = [root/'tianjin_live_teda_records.json', root/'tianjin_live_tjmugh_records.json', root/'tianjin_live_tjzyefy_intent_records.json']
negatives_src = [root/'tianjin_live_tjfch_records.json', root/'tianjin_live_tjzyefy_records.json', root/'tianjin_live_ccgp_records.json']
pos_states = {'MARKET_RESEARCH', 'PROCUREMENT_INTENT', 'SUPPLIER_RECRUITMENT'}
neg_states = {'BIDDING', 'AWARD', 'RESULT'}

def collect(paths, states, label):
    rows, seen = [], set()
    for path in paths:
        for row in json.loads(path.read_text(encoding='utf-8')):
            facts, source = row.get('facts') or {}, row.get('source') or {}
            state = str(facts.get('lifecycle_state') or '').upper()
            title = str(facts.get('project_name') or '').strip()
            url = str(source.get('url') or '').strip()
            if state in states and title and url and url not in seen:
                seen.add(url)
                rows.append({'title': title, 'url': url, 'label': label, 'state': state})
    return rows

positives = sorted(collect(positives_src, pos_states, 'positive'), key=lambda x:(x['state'], x['url']))[:12]
negatives = sorted(collect(negatives_src, neg_states, 'negative'), key=lambda x:(x['state'], x['url']))[:len(positives)]
if len(positives) < 8 or len(negatives) != len(positives):
    raise SystemExit(f'corpus gate failed positives={len(positives)} negatives={len(negatives)}')
corpus = positives + negatives
print(json.dumps({'positive_count':len(positives),'negative_count':len(negatives),'total':len(corpus)}, ensure_ascii=False))

p = app / 'web/api/ai/discover.js'
text = p.read_text(encoding='utf-8')
handler = 'export default async function handler(request, response) {'
route_marker = "export default async function handler(request, response) {\n  const route = request.query?.route"
if text.count(handler) != 1 or text.count(route_marker) != 1:
    raise SystemExit('discover patch marker mismatch')

helper = r'''
// EPHEMERAL_AB_GET_START - staged only; never promote this deployment.
const AGNES_AB_MODEL_25 = ['agnes', '2.5', 'flash'].join('-')
const AGNES_AB_MODELS = new Set([AGNES_AB_MODEL_25, MODEL_ID])
const AGNES_AB_CORPUS = __CORPUS__

async function agnesAbGetHandler(query, response) {
  const keys = getApiKeys()
  if (!keys.length) return sendJson(response, 503, { error: 'AGNES_KEY_MISSING' })
  if (query?.action === 'info') return sendJson(response, 200, {
    key_count: keys.length,
    corpus_count: AGNES_AB_CORPUS.length,
    positive_count: AGNES_AB_CORPUS.filter((x) => x.label === 'positive').length,
    negative_count: AGNES_AB_CORPUS.filter((x) => x.label === 'negative').length,
    models: Array.from(AGNES_AB_MODELS),
    production_data_mutated: false,
  })
  const model = String(query?.model || '')
  if (!AGNES_AB_MODELS.has(model)) return sendJson(response, 400, { error: 'MODEL_NOT_ALLOWED' })
  const slot = Number(query?.key_slot)
  if (!Number.isInteger(slot) || slot < 0 || slot >= keys.length) return sendJson(response, 400, { error: 'KEY_SLOT_INVALID', key_count: keys.length })
  const timeoutMs = Math.max(1000, Math.min(25000, Number(query?.timeout_ms || 12000)))
  const anchors = AGNES_AB_CORPUS.map(({title,url}) => ({title,url}))
  const positives = AGNES_AB_CORPUS.filter((x) => x.label === 'positive')
  const negatives = AGNES_AB_CORPUS.filter((x) => x.label === 'negative')
  const baseUrl = String(process.env.AGNES_API_BASE_URL || DEFAULT_BASE_URL).trim().replace(/\/+$/, '')
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  const started = Date.now()
  try {
    const upstream = await fetch(`${baseUrl}/chat/completions`, {
      method: 'POST', signal: controller.signal,
      headers: {Authorization:`Bearer ${keys[slot]}`,'Content-Type':'application/json',Accept:'application/json'},
      body: JSON.stringify({model,messages:buildMessages({name:'MedicalChannelAI 固定 A/B 基准语料'},anchors),temperature:0,max_tokens:1400,stream:false}),
    })
    const latencyMs = Date.now() - started
    if (!upstream.ok) return sendJson(response, 200, {provider_ok:false,model,key_slot:slot,key_count:keys.length,timeout_ms:timeoutMs,latency_ms:latencyMs,error:`UPSTREAM_HTTP_${upstream.status}`,production_data_mutated:false})
    const payload = await upstream.json()
    const content = payload?.choices?.[0]?.message?.content
    if (typeof content !== 'string' || !content.trim()) return sendJson(response, 200, {provider_ok:false,model,key_slot:slot,key_count:keys.length,timeout_ms:timeoutMs,latency_ms:latencyMs,error:'UPSTREAM_CONTENT_EMPTY',production_data_mutated:false})
    let parsed
    try { parsed = parseCandidates(content, anchors) }
    catch { return sendJson(response, 200, {provider_ok:false,model,key_slot:slot,key_count:keys.length,timeout_ms:timeoutMs,latency_ms:latencyMs,error:'AI_RESPONSE_INVALID',production_data_mutated:false}) }
    const selected = new Set(parsed.candidates.map((x) => x.url))
    const hits = positives.filter((x) => selected.has(x.url)).length
    const fp = negatives.filter((x) => selected.has(x.url)).length
    return sendJson(response, 200, {
      provider_ok:true,model,key_slot:slot,key_count:keys.length,timeout_ms:timeoutMs,latency_ms:latencyMs,
      corpus_count:AGNES_AB_CORPUS.length,positive_count:positives.length,negative_count:negatives.length,
      raw_candidate_count:parsed.rawCount,candidate_count:parsed.candidates.length,positive_hits:hits,false_positives:fp,
      recall:Math.round((hits/positives.length)*10000)/10000,
      false_positive_rate:Math.round((fp/negatives.length)*10000)/10000,
      precision:Math.round((selected.size?hits/selected.size:1)*10000)/10000,
      rejected_ungrounded_count:parsed.rejectedUngrounded,rejected_invalid_count:parsed.rejectedInvalid,
      production_data_mutated:false,
    })
  } catch (error) {
    const latencyMs = Date.now() - started
    const timedOut = error?.name === 'AbortError' || /aborted/i.test(String(error?.message || error || ''))
    return sendJson(response, 200, {provider_ok:false,model,key_slot:slot,key_count:keys.length,timeout_ms:timeoutMs,latency_ms:latencyMs,error:timedOut?'TIMEOUT':'PROVIDER_EXCEPTION',production_data_mutated:false})
  } finally { clearTimeout(timeout) }
}
// EPHEMERAL_AB_GET_END

'''.replace('__CORPUS__', json.dumps(corpus, ensure_ascii=False))

replacement = helper + handler + "\n  if (request.method === 'GET' && request.query?.benchmark_ab === 'true') return agnesAbGetHandler(request.query, response)"
text = text.replace(handler, replacement, 1)
p.write_text(text, encoding='utf-8')
if 'EPHEMERAL_AB_GET_START' not in p.read_text(encoding='utf-8'):
    raise SystemExit('patch missing')
