import json,hashlib,http.cookiejar,urllib.request,urllib.error,time
from pathlib import Path
from urllib.parse import urlsplit,urlencode
from datetime import datetime,timezone

P=Path(__file__).parent
scope=json.loads((P/'scope.json').read_text())
secret=json.loads((P/'access.json').read_text())['share_secret']
origin=scope['url'];host=urlsplit(origin)
deadline=datetime.fromisoformat(scope['deadline'].replace('Z','+00:00')).timestamp()
assert scope['target']=='preview' and scope['epoch']=='mcai-p0-20261106-d' and scope['database']=='mcai_p0_epoch_20261106d'
assert host.scheme=='https' and host.netloc=='medicalchannelai-b5vc26me3-rerisse7-1717s-projects.vercel.app'
class SameOrigin(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,url):
        target=urlsplit(url)
        if (target.scheme,target.netloc)!=(host.scheme,host.netloc):raise RuntimeError('CROSS_ORIGIN_REJECTED')
        return super().redirect_request(req,fp,code,msg,headers,url)
jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(SameOrigin(),urllib.request.HTTPCookieProcessor(jar))
def get(path):
    assert path.split('?')[0] in {'/api/status','/api/public-snapshot','/api/collector-status'}
    remaining=deadline-time.time()
    if remaining<1:raise RuntimeError('ABSOLUTE_DEADLINE_REACHED')
    url=origin+path
    if not any(c.name.startswith('_vercel') for c in jar):url+=('?' if '?' not in url else '&')+urlencode({'_vercel_share':secret})
    req=urllib.request.Request(url,headers={'Accept':'application/json'},method='GET')
    try:response=opener.open(req,timeout=min(30,remaining))
    except urllib.error.HTTPError as e:response=e
    with response:
        raw=response.read()
        try:payload=json.loads(raw)
        except ValueError:payload={'non_json_bytes':len(raw)}
        return {'at':datetime.now(timezone.utc).isoformat(),'http':response.status,'response':payload,'headers':{k:response.headers.get(k) for k in ['age','x-vercel-cache','cache-control','x-medicalchannelai-snapshot-source']}}
def save(name,value):
    output=json.dumps(value,ensure_ascii=False,indent=2)
    assert secret not in output
    (P/name).write_text(output+'\n')
def canonical_hash(value):
    # Final cross-reader proof also uses Node canonicalization to bind Vercel's JS hash.
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
status=get('/api/status');save('status.json',status)
assert status['http']==200
assert status['response']['commit']==scope['source_sha'][:7]
assert status['response']['preview_epoch']==scope['epoch']
assert status['response']['snapshot']['source_mode']=='DATABASE'
for name,path in [('fresh','/api/public-snapshot?fresh='+str(int(time.time()*1000))),('ordinary','/api/public-snapshot'),('collector','/api/collector-status')]:
    value=get(path);save(name+'.json',value);assert value['http']==200
print(json.dumps({'status':status['http'],'commit':status['response']['commit'],'epoch':scope['epoch'],'source_mode':'DATABASE','methods':['GET'],'queue_triggered':False}))
