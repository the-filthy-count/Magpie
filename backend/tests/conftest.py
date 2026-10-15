import socket
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
@pytest.fixture
def client(tmp_path, monkeypatch):
    root=tmp_path/'downloads'; root.mkdir()
    app=create_app(tmp_path/'config',[root],start_queue=False)
    monkeypatch.setattr(socket,'getaddrinfo',lambda host,port,*a,**kw:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',port))])
    with TestClient(app) as c:
        c.app_ref=app; c.root=root; c.config=tmp_path/'config'
        c.setup_token=(c.config/'setup-token').read_text()
        yield c
@pytest.fixture
def admin(client):
    r=client.post('/api/auth/setup',json={'password':'correct horse battery staple'},headers={'X-Setup-Token':client.setup_token})
    assert r.status_code==200,r.text
    client.headers['X-CSRF-Token']=r.json()['csrf']
    return client
@pytest.fixture
def destination(admin):
    folder=admin.root/'pictures';folder.mkdir()
    r=admin.post('/api/destinations',json={'name':'Pictures','path':str(folder)})
    assert r.status_code==201,r.text
    return r.json()
