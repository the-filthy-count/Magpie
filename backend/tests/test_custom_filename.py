import json
import subprocess
import sys
import pytest
from app.database.store import DEFAULTS
from app.downloads.options import custom_filename
from test_engine import SCRIPT, PNG

@pytest.mark.parametrize('position,expected',[('start','Alice - Nature - original.jpg'),('end','original - Alice - Nature.jpg')])
def test_literal_filename_fields(position,expected):
    assert custom_filename('original.jpg',{'creator':'Alice','tag':'Nature'},position)==expected
    assert '/' not in custom_filename('original.jpg',{'tag':'../../outside\\bad'},position)
    assert '{filename}' in custom_filename('original.jpg',{'tag':'{filename}'},position)
    assert len(custom_filename('original.jpg',{'tag':'山'*100},position).encode())<=240

@pytest.mark.parametrize('position',['start','end'])
def test_real_download_custom_filename(tmp_path,position):
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    spec=dict(url='https://93.184.216.34/fixture.png',destination_path=str(root),archive=str(archive),settings={**DEFAULTS,'organisation':'flat'},payload=PNG.hex(),custom_fields={'creator':'Alice','tag':'Nature'},filename_position=position)
    result=subprocess.run([sys.executable,'-c',SCRIPT],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    files=list(root.glob('*.png'));assert len(files)==1 and files[0].read_bytes()==PNG
    if position=='start':assert files[0].name.startswith('Alice - Nature - ')
    else:assert files[0].name.endswith(' - Alice - Nature.png')


def test_api_fields_survive_history_and_retry(admin,destination):
    token=admin.post('/api/tokens',json={'name':'Naming client'}).json()['token']
    headers={'Authorization':'Bearer '+token}
    data={'url':'https://example.com/gallery','category':'Pictures','custom_fields':{'creator':'Alice','collection':'Nature'},'filename_position':'end'}
    response=admin.post('/api/downloads',headers=headers,json=data)
    assert response.status_code==201,response.text
    ident=response.json()['id']
    for path in ('/api/downloads/'+ident,'/api/downloads'):
        row=admin.get(path,headers=headers).json()
        if isinstance(row,list):row=row[0]
        assert row['custom_fields']==data['custom_fields'] and row['filename_position']=='end'
    admin.post('/api/downloads/'+ident+'/cancel',headers=headers)
    row=admin.post('/api/downloads/'+ident+'/retry',headers=headers).json()
    assert row['custom_fields']==data['custom_fields'] and row['filename_position']=='end'
    for invalid in ({'filename_position':'middle'},{'custom_fields':{'tag':''}},{'custom_fields':{'tag':42}},{'custom_fields':{'tag':'x'*101}},{'custom_fields':{str(i):'value' for i in range(11)}}):
        assert admin.post('/api/downloads',headers=headers,json={**data,**invalid}).status_code==422


def test_fields_combine_with_flat_gallery_names(tmp_path):
    script=SCRIPT.replace('sys.exit(run(spec))', '''
from gallery_dl.extractor.bunkr import BunkrAlbumExtractor
BunkrAlbumExtractor.fetch_album=lambda self,ident:([{'file':'https://93.184.216.34/one.png','name':'one.png','id':'one'}],{'album_id':ident,'album_name':'Summer gallery','count':1})
sys.exit(run(spec))
''')
    root=tmp_path/'media';root.mkdir();archive=tmp_path/'archive';archive.mkdir()
    spec=dict(url='https://bunkr.cr/a/FIXTURE',destination_path=str(root),archive=str(archive),settings={**DEFAULTS,'organisation':'flat_gallery'},payload=PNG.hex(),custom_fields={'creator':'Alice'},filename_position='end')
    result=subprocess.run([sys.executable,'-c',script],input=json.dumps(spec)+'\n',capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    assert (root/'Summer gallery - one - Alice.png').read_bytes()==PNG
