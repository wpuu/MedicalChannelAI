import assert from 'node:assert/strict'
import { previewEpoch, epochKey, scopePreviewCache, assertPreviewDatabase } from '../api/_previewEpoch.js'
const saved={environment:process.env.VERCEL_ENV,epoch:process.env.MCAI_PREVIEW_EPOCH,database:process.env.MCAI_PREVIEW_DATABASE}
try {
 const values=new Map([['snapshot','legacy']]);const tags=[]
 const raw={get:async k=>values.get(k),set:async(k,v,o)=>{values.set(k,v);if(o?.tags)tags.push(...o.tags)},delete:async k=>values.delete(k),expireTag:async t=>tags.push(t)}
 process.env.VERCEL_ENV='preview';process.env.MCAI_PREVIEW_EPOCH='cycle-a'
 process.env.MCAI_PREVIEW_DATABASE='mcai_p0_epoch_test'
 assert.doesNotThrow(()=>assertPreviewDatabase('postgres://test:test@localhost/mcai_p0_epoch_test'))
 assert.throws(()=>assertPreviewDatabase('postgres://test:test@localhost/old_database'),/PREVIEW_DATABASE_SCOPE_INVALID/)
 const a=scopePreviewCache(raw);assert.equal(await a.get('snapshot'),undefined)
 await a.set('snapshot','a',{ttl:7,tags:['t']});assert.equal(values.get('snapshot'),'legacy');assert.equal(await a.get('snapshot'),'a');assert.deepEqual(tags,[epochKey('t','cycle-a')])
 process.env.MCAI_PREVIEW_EPOCH='cycle-b';const b=scopePreviewCache(raw)
 assert.equal(await b.get('snapshot'),undefined);await b.set('snapshot','b');await a.delete('snapshot');assert.equal(await b.get('snapshot'),'b');assert.equal(values.get('snapshot'),'legacy')
 process.env.VERCEL_ENV='production';process.env.MCAI_PREVIEW_EPOCH='invalid/ignored'
 assert.equal(previewEpoch(),null);assert.equal(scopePreviewCache(raw),raw)
 process.env.VERCEL_ENV='preview';assert.throws(()=>previewEpoch(),/PREVIEW_EPOCH_INVALID/)
 process.env.MCAI_PREVIEW_EPOCH='';assert.equal(scopePreviewCache(raw),raw)
} finally {
 if(saved.database===undefined)delete process.env.MCAI_PREVIEW_DATABASE;else process.env.MCAI_PREVIEW_DATABASE=saved.database
 if(saved.environment===undefined)delete process.env.VERCEL_ENV;else process.env.VERCEL_ENV=saved.environment
 if(saved.epoch===undefined)delete process.env.MCAI_PREVIEW_EPOCH;else process.env.MCAI_PREVIEW_EPOCH=saved.epoch
}
console.log('Preview epoch cache and Production compatibility: PASS')
