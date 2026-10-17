from fastapi.testclient import TestClient
from app.main import create_app


def test_webp_brand_assets_have_explicit_media_type(tmp_path, monkeypatch):
    static=tmp_path/'static';static.mkdir()
    payload=b'RIFF\x04\x00\x00\x00WEBP'
    for name in ('logo.webp','id.webp'):(static/name).write_bytes(payload)
    monkeypatch.setenv('MAGPIE_STATIC',str(static))
    root=tmp_path/'downloads';root.mkdir()
    with TestClient(create_app(tmp_path/'config',[root],start_queue=False)) as client:
        for name in ('logo.webp','id.webp'):
            response=client.get('/'+name)
            assert response.status_code==200
            assert response.headers['content-type']=='image/webp'
            assert response.headers['x-content-type-options']=='nosniff'
            assert response.content==payload
