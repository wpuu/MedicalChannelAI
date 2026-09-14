import json
import sys
from pathlib import Path

app = Path(sys.argv[1])
root = app / 'web/pipeline/data'
positive_files = [root/'tianjin_live_teda_records.json', root/'tianjin_live_tjmugh_records.json', root/'tianjin_live_tjzyefy_intent_records.json']
negative_files = [root/'tianjin_live_tjfch_records.json', root/'tianjin_live_tjzyefy_records.json', root/'tianjin_live_ccgp_records.json']
pos_states = {'MARKET_RESEARCH','PROCUREMENT_INTENT','SUPPLIER_RECRUITMENT'}
neg_states = {'BIDDING','AWARD','RESULT'}

def collect(paths, states, label):
    out, seen = [], set()
    for path in paths:
        for row in json.loads(path.read_text(encoding='utf-8')):
            facts, source = row.get('facts') or {}, row.get('source') or {}
            state = str(facts.get('lifecycle_state') or '').upper()
            title = str(facts.get('project_name') or '').strip()
            url = str(source.get('url') or '').strip()
            if state in states and title and url and url not in seen:
                seen.add(url)
                out.append({'title':title,'url':url,'label':label,'state':state})
    return out

positives = sorted(collect(positive_files,pos_states,'positive'), key=lambda x:(x['state'],x['url']))[:12]
negatives = sorted(collect(negative_files,neg_states,'negative'), key=lambda x:(x['state'],x['url']))[:len(positives)]
if len(positives) < 8 or len(negatives) != len(positives):
    raise SystemExit(f'corpus gate failed positives={len(positives)} negatives={len(negatives)}')
corpus = positives + negatives

script = r'''const corpus = __CORPUS__
const signalTypes = new Set(['DEMAND_RESEARCH','SUPPLIER_RECRUITMENT','TEST_ENTERPRISE_RECRUITMENT','ARGUMENTATION_INVITATION','PURCHASE_INTENTION','OTHER_PREPROCUREMENT'])
const models = ['agnes-2.5-flash','agnes-3.0-flash']
const phases = [{name:'sla12',timeout_ms:12000},{name:'quality25',timeout_ms:25000}]
const keys = String(process.env.AGNES_API_KEYS || process.env.AGNES_API_KEY || '').split(/[\n,;]+/).map(x=>x.trim()).filter(Boolean)
const baseUrl = String(process.env.AGNES_API_BASE_URL || 'https://apihub.agnes-ai.com/v1').trim().replace(/\/+$/,'')
if (!keys.length) { console.error('AGNES_AB_SAFE_ERROR=AGNES_KEY_MISSING'); process.exit(2) }
const anchors = corpus.map(({title,url})=>({title,url}))
const positives = corpus.filter(x=>x.label==='positive')
const negatives = corpus.filter(x=>x.label==='negative')
console.log('AGNES_AB_INFO_JSON='+JSON.stringify({key_count:keys.length,corpus_count:corpus.length,positive_count:positives.length,negative_count:negatives.length,models,production_data_mutated:false}))

function messages(){return [
  {role:'system',content:'你是医疗行业公开商机发现器。只从输入的官方公开来源链接列表中挑选仍可能影响需求、测试、论证、方案或采购准备的前期窗口。优先：需求调研、供应商征集、测试企业征集、论证邀请、采购意向。排除：正式招标公告、成交/中标结果、评分细则、招聘、人事、党建、新闻宣传、纯制度通知。禁止补全、改写、猜测URL；只能原样返回输入URL。不要把判断说成已验证事实。严格输出JSON，不要Markdown。'},
  {role:'user',content:JSON.stringify({source:'MedicalChannelAI 固定 A/B 基准语料',source_kind:'OFFICIAL_BENCHMARK',anchors,max_candidates:12,output_schema:{candidates:[{title:'对应输入标题',url:'必须与输入URL完全一致',signal_type:Array.from(signalTypes),confidence:'0到1',reason:'不超过80个汉字'}]}})}
]}
function jsonContent(s){return s.trim().replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'').trim()}
function parse(content){
  let p; try{p=JSON.parse(jsonContent(content))}catch{return {ok:false,error:'AI_RESPONSE_INVALID'}}
  if(!p||typeof p!=='object'||!Array.isArray(p.candidates))return {ok:false,error:'AI_RESPONSE_INVALID'}
  const allowed=new Map(anchors.map(x=>[x.url,x]));const selected=[];const seen=new Set();let ungrounded=0,invalid=0
  for(const row of p.candidates){
    if(!row||typeof row!=='object'){invalid++;continue}
    const url=typeof row.url==='string'?row.url.trim():'';if(!allowed.has(url)){ungrounded++;continue}
    const type=typeof row.signal_type==='string'?row.signal_type.trim().toUpperCase():'';const conf=Number(row.confidence);const reason=typeof row.reason==='string'?row.reason.replace(/\s+/g,' ').trim():''
    if(!signalTypes.has(type)||!Number.isFinite(conf)||conf<0||conf>1||!reason){invalid++;continue}
    if(!seen.has(url)){seen.add(url);selected.push(url)}
  }
  return {ok:true,raw:p.candidates.length,selected,ungrounded,invalid}
}
async function runOne(model,slot,timeoutMs){
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),timeoutMs);const started=Date.now()
  try{
    const r=await fetch(baseUrl+'/chat/completions',{method:'POST',signal:controller.signal,headers:{Authorization:`Bearer ${keys[slot]}`,'Content-Type':'application/json',Accept:'application/json'},body:JSON.stringify({model,messages:messages(),temperature:0,max_tokens:1400,stream:false})})
    const latency_ms=Date.now()-started
    if(!r.ok)return {provider_ok:false,model,key_slot:slot,timeout_ms:timeoutMs,latency_ms,error:`UPSTREAM_HTTP_${r.status}`}
    const payload=await r.json();const content=payload?.choices?.[0]?.message?.content
    if(typeof content!=='string'||!content.trim())return {provider_ok:false,model,key_slot:slot,timeout_ms:timeoutMs,latency_ms,error:'UPSTREAM_CONTENT_EMPTY'}
    const parsed=parse(content);if(!parsed.ok)return {provider_ok:false,model,key_slot:slot,timeout_ms:timeoutMs,latency_ms,error:parsed.error}
    const s=new Set(parsed.selected),hits=positives.filter(x=>s.has(x.url)).length,fp=negatives.filter(x=>s.has(x.url)).length
    return {provider_ok:true,model,key_slot:slot,timeout_ms:timeoutMs,latency_ms,raw_candidate_count:parsed.raw,candidate_count:s.size,positive_hits:hits,false_positives:fp,recall:Number((hits/positives.length).toFixed(4)),false_positive_rate:Number((fp/negatives.length).toFixed(4)),precision:Number((s.size?hits/s.size:1).toFixed(4)),rejected_ungrounded_count:parsed.ungrounded,rejected_invalid_count:parsed.invalid}
  }catch(e){const latency_ms=Date.now()-started;const timed=e?.name==='AbortError'||/aborted/i.test(String(e?.message||e||''));return {provider_ok:false,model,key_slot:slot,timeout_ms:timeoutMs,latency_ms,error:timed?'TIMEOUT':'PROVIDER_EXCEPTION'}}finally{clearTimeout(timer)}
}
const rows=[]
for(const phase of phases){for(const model of models){const batch=await Promise.all(keys.map((_,slot)=>runOne(model,slot,phase.timeout_ms)));for(const x of batch){rows.push({phase:phase.name,...x});console.log('AGNES_AB_ROW_JSON='+JSON.stringify({phase:phase.name,...x}))}}}
function pct(vals,p){if(!vals.length)return null;const a=[...vals].sort((x,y)=>x-y);return a[Math.min(a.length-1,Math.max(0,Math.ceil(p*a.length)-1))]}
const report={}
for(const phase of phases.map(x=>x.name)){report[phase]={};for(const model of models){const r=rows.filter(x=>x.phase===phase&&x.model===model),ok=r.filter(x=>x.provider_ok),avg=k=>ok.length?Number((ok.reduce((s,x)=>s+Number(x[k]??0),0)/ok.length).toFixed(4)):null,lats=r.map(x=>Number(x.latency_ms)).filter(Number.isFinite);report[phase][model]={attempts:r.length,successes:ok.length,success_rate:r.length?Number((ok.length/r.length).toFixed(4)):0,timeouts:r.filter(x=>x.error==='TIMEOUT').length,p50_latency_ms:pct(lats,.5),p95_latency_ms:pct(lats,.95),avg_recall:avg('recall'),avg_false_positive_rate:avg('false_positive_rate'),avg_precision:avg('precision'),avg_candidate_count:avg('candidate_count'),total_rejected_ungrounded:ok.reduce((s,x)=>s+Number(x.rejected_ungrounded_count||0),0),total_rejected_invalid:ok.reduce((s,x)=>s+Number(x.rejected_invalid_count||0),0)}}}
const expected=keys.length*models.length*phases.length
if(rows.length!==expected){console.error(`AGNES_AB_SAFE_ERROR=ATTEMPT_COUNT_MISMATCH expected=${expected} actual=${rows.length}`);process.exit(3)}
console.log('AGNES_AB_REPORT_JSON='+JSON.stringify(report))
'''.replace('__CORPUS__', json.dumps(corpus, ensure_ascii=False))

scripts = app / 'web/scripts'
scripts.mkdir(parents=True, exist_ok=True)
(scripts/'agnes-ab-build.mjs').write_text(script, encoding='utf-8')
package_path = app/'web/package.json'
pkg = json.loads(package_path.read_text(encoding='utf-8'))
old = pkg['scripts']['build']
pkg['scripts']['build'] = 'node scripts/agnes-ab-build.mjs && ' + old
package_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'injected':True,'positive_count':len(positives),'negative_count':len(negatives),'total':len(corpus)}, ensure_ascii=False))
