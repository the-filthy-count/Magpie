#!/usr/bin/env python3
"""Optional real-network smoke check against an already configured Magpie instance.

MAGPIE_TEST_PASSWORD is required. MAGPIE_TEST_URL defaults to a small public
Wikimedia logo. Creates one history entry; never removes downloaded media.
"""
import http.cookiejar
import json
import os
import sys
import time
import urllib.request

base = os.environ.get('MAGPIE_TEST_BASE', 'http://127.0.0.1:9080').rstrip('/')
password = os.environ.get('MAGPIE_TEST_PASSWORD')
if not password:
    sys.exit('Set MAGPIE_TEST_PASSWORD for a disposable or authorised test instance')
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
csrf = ''

def request(path, method='GET', data=None):
    req = urllib.request.Request(base+'/api'+path, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type':'application/json', 'X-CSRF-Token':csrf})
    with client.open(req, timeout=15) as response:
        return json.load(response)

assert request('/health')['status'] == 'ok'
csrf = request('/auth/login', 'POST', {'password':password})['csrf']
try:
    destinations = request('/destinations')
    selected = next((d for d in destinations if d['is_default'] and d['writable']), None)
    assert selected, 'Configure a writable default destination first'
    job = request('/downloads', 'POST', {
        'url':os.environ.get('MAGPIE_TEST_URL', 'https://en.wikipedia.org/static/images/project-logos/enwiki.png'),
        'destination_id':selected['id']})
    for _ in range(300):
        job = request('/downloads/'+job['id'])
        if job['status'] not in ('queued','downloading'):
            break
        time.sleep(.2)
    assert job['status'] == 'completed', job.get('error') or job['status']
    for path, signature in [('/', b'<div id="root">'),('/logo.png', b'\x89PNG\r\n\x1a\n'),('/bird.ttf', b'\x00\x01\x00\x00')]:
        with client.open(base+path) as response:
            assert signature in response.read(), 'Missing or unreadable asset: '+path
    print(json.dumps({key:job[key] for key in ('id','status','files','skipped','bytes')}))
    print('Health, authentication, destination, real download, frontend and supplied branding passed')
finally:
    request('/auth/logout', 'POST')
