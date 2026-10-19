import requests
from app.core import network

DATA=dict(ip='93.184.216.34',country='Example country',city='Example city',isp='Example ISP',checked_at='2026-10-19T12:00:00+00:00')


def test_network_endpoint_requires_admin_and_caches(admin,monkeypatch):
    calls=[]
    monkeypatch.setattr(network,'fetch_network',lambda:(calls.append(1) or DATA.copy()))
    response=admin.get('/api/network');assert response.status_code==200
    assert response.json()['ip']==DATA['ip'] and response.json()['stale'] is False
    assert admin.get('/api/network').json()['isp']==DATA['isp']
    assert calls==[1]
    token=admin.post('/api/tokens',json={'name':'Scoped app'}).json()['token']
    assert admin.get('/api/network',headers={'Authorization':'Bearer '+token}).status_code==403
    admin.cookies.clear()
    assert admin.get('/api/network').status_code==401


def test_network_lookup_retains_last_good_value_and_throttles_failures(monkeypatch):
    clock=[0];monkeypatch.setattr(network.time,'monotonic',lambda:clock[0])
    calls=[]
    def fetch():
        calls.append(1)
        if len(calls)>1:raise requests.Timeout('secret connection detail')
        return DATA.copy()
    monkeypatch.setattr(network,'fetch_network',fetch)
    cache=network.NetworkInfo()
    assert cache.get()['ip']==DATA['ip']
    clock[0]=299;cache.get();assert len(calls)==1
    clock[0]=300;stale=cache.get();assert stale['stale'] and stale['ip']==DATA['ip']
    assert 'secret' not in stale['error']
    clock[0]=301;cache.get();assert len(calls)==2
    clock[0]=331;cache.get();assert len(calls)==3


def test_network_failure_is_safe_on_first_load(monkeypatch):
    def fetch():raise ValueError('malformed external payload')
    monkeypatch.setattr(network,'fetch_network',fetch)
    data=network.NetworkInfo().get()
    assert data['ip'] is None and data['stale']
    assert 'malformed' not in data['error']
