#!/usr/bin/env python3
"""Small deployment smoke check; --live generates one sample article."""
import argparse
import json
from pathlib import Path
import time
import threading
import httpx

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:18567')
parser.add_argument('--live', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
credentials = json.loads((root/'secrets.json').read_text())
report = {'checks':[], 'live_requested':args.live}
client = httpx.Client(base_url=args.url, timeout=30, follow_redirects=True)

def check(name, ok):
    assert ok, name
    report['checks'].append(name)
    print('PASS '+name, flush=True)

def api(method, path, **kw):
    response = client.request(method, '/api'+path, **kw)
    response.raise_for_status()
    body = response.json()
    assert body.get('code') == 0, (path, body.get('message'))
    return body.get('data')

check('health', api('GET','/health') == 'ok')
check('branded homepage', 'yangbin' in client.get('/').text)
check('SPA refresh', client.get('/user/login').status_code == 200)
check('missing API stays 404', client.get('/api/does-not-exist').status_code == 404)
check('missing asset stays 404', client.get('/assets/missing.js').status_code == 404)
check('anonymous access rejected', client.get('/api/user/get/login').json()['code'] != 0)
user = api('POST','/user/login',json={'userAccount':'yangbin','userPassword':credentials['admin_password']})
check('admin login', user['userRole'] == 'admin')
check('session cookie', bool(client.cookies.get('SESSION')))
check('session round trip', api('GET','/user/get/login')['userAccount']=='yangbin')
check('article list', 'records' in api('POST','/article/list',json={'current':1,'pageSize':10}))
check('admin user list', 'records' in api('POST','/user/list/page',json={'current':1,'pageSize':10}))

if args.live:
    task = api('POST','/article/create',json={'topic':'向大学新生解释如何用番茄工作法安排一小时学习，简洁、准确，不虚构研究数据','style':'educational','enabledImageMethods':['iconify']})
    report['task_id'] = task
    events=[]
    def listen():
        try:
            with httpx.Client(base_url=args.url, cookies=client.cookies, timeout=650) as stream_client:
                with stream_client.stream('GET','/api/article/progress/'+task) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if line.startswith('data: '):
                            events.append(json.loads(line[6:]).get('type'))
        except Exception as exc:
            report['sse_error']=type(exc).__name__
    listener=threading.Thread(target=listen,daemon=True)
    listener.start()
    def wait_phase(expected):
        deadline = time.monotonic()+600
        while time.monotonic()<deadline:
            article = api('GET','/article/'+task)
            if article['status']=='FAILED':
                raise RuntimeError(article.get('errorMessage'))
            if article.get('phase')==expected or article['status']==expected:
                return article
            time.sleep(3)
        raise TimeoutError(expected)
    article=wait_phase('TITLE_SELECTING')
    check('live titles', bool(article['titleOptions']))
    title=article['titleOptions'][0]
    api('POST','/article/confirm-title',json={'taskId':task,'selectedMainTitle':title['mainTitle'],'selectedSubTitle':title['subTitle'],'userDescription':'只需要两个小节，正文约500字。'})
    article=wait_phase('OUTLINE_EDITING')
    check('live outline', bool(article['outline']))
    api('POST','/article/confirm-outline',json={'taskId':task,'outline':article['outline'][:2]})
    article=wait_phase('COMPLETED')
    check('live completed article', len(article.get('fullContent') or '')>100)
    listener.join(timeout=5)
    check('live SSE events', bool(events))
    report['sse_event_types']=sorted(set(events))
    report['article_characters']=len(article['fullContent'])
    report['image_count']=len(article.get('images') or [])
    (root/'sample-article.md').write_text(article['fullContent'],encoding='utf-8')
(root/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
