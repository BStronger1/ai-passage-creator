#!/usr/bin/env python3
"""Restart this deployment's three services and verify saved state survives."""
import hashlib,json,subprocess,time
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[2]
s=json.loads((root/'secrets.json').read_text())
evidence=json.loads((root/'verification.json').read_text())
c=httpx.Client(base_url='http://127.0.0.1:18567',timeout=10)
r=c.post('/api/user/login',json={'userAccount':'yangbin','userPassword':s['admin_password']}).json()
assert r['code']==0
article_path='/api/article/'+evidence['task_id']
before=c.get(article_path).json()['data']
assert before['status']=='COMPLETED'
subprocess.run([str(root/'runtime/bin/supervisorctl'),'-c',str(root/'supervisord.conf'),'restart','all'],check=True)
for attempt in range(60):
 try:
  if c.get('/api/health').json()['code']==0:break
 except (httpx.HTTPError,ValueError):pass
 time.sleep(1)
else:raise RuntimeError('Restart health check failed')
assert c.get('/api/user/get/login').json()['data']['userAccount']=='yangbin'
after=c.get(article_path).json()['data']
assert after['status']=='COMPLETED' and before['fullContent']==after['fullContent']
result={'databasePersistence':True,'redisSessionPersistence':True,'apiHealthy':True,'articleSha256':hashlib.sha256(after['fullContent'].encode()).hexdigest()}
(root/'restart-verification.json').write_text(json.dumps(result,indent=2))
print('PASS full service restart: saved article and existing session survived.')
