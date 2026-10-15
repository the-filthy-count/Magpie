import socket
import subprocess
import sys
import pytest
from app.core.security import validate_url,destination_path,safe_template,hash_password,verify_password
@pytest.mark.parametrize('url',['file:///etc/passwd','ftp://example.com','http://localhost/x','http://127.0.0.1','http://[::1]/','http://169.254.169.254/latest','http://192.168.1.2','http://10.0.0.1','http://[::ffff:127.0.0.1]','http://user:password@example.com','http://example.com:8080','https://a.local/x','https://example.com/\n'])
def test_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):validate_url(url,resolve=False)
def test_dns_rebinding_and_mixed_results(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('93.184.216.34',443)),(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError):validate_url('https://example.com')
def test_public_url():
    assert validate_url('https://93.184.216.34/path')
def test_paths(tmp_path):
    root=tmp_path/'root';root.mkdir();outside=tmp_path/'outside';outside.mkdir()
    (root/'escape').symlink_to(outside,target_is_directory=True)
    for path in (str(root/'../outside'),str(root/'escape'),str(outside),'relative'):
        with pytest.raises(ValueError):destination_path(path,[root])
    assert destination_path(str(root),[root])==str(root)
@pytest.mark.parametrize('value',['../../etc','/tmp/x','{foo.__class__}','{x!r}','{x:eval}','{x|exec}','{x/../x}','..','{x'])
def test_unsafe_templates(value):
    with pytest.raises(ValueError):safe_template(value)
def test_hashes():
    value=hash_password('a long password')
    assert verify_password('a long password',value)
    assert not verify_password('wrong',value)
    assert hash_password('a long password')!=value
def test_kernel_filesystem_confinement(tmp_path):
    root=tmp_path/'allowed';root.mkdir();outside=tmp_path/'outside';outside.mkdir()
    (root/'link').symlink_to(outside,target_is_directory=True)
    script='''
from pathlib import Path
from app.core.security import landlock
import sys
root,outside=map(Path,sys.argv[1:]);landlock([root])
(root/'good').write_text('ok')
for path in (outside/'bad',root/'link'/'bad',root/'..'/'bad'):
    try:path.write_text('escaped')
    except PermissionError:pass
    else:raise AssertionError('Sandbox escaped')
'''
    r=subprocess.run([sys.executable,'-c',script,str(root),str(outside)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    assert (root/'good').read_text()=='ok'
def test_actual_connection_is_checked():
    script='''
import socket
from app.core.security import guard_network
guard_network()
for address in [('127.0.0.1',80),('169.254.169.254',80),('93.184.216.34',22)]:
    try:socket.socket().connect(address)
    except (ValueError,OSError):pass
    else:raise AssertionError('Connection not blocked')
'''
    r=subprocess.run([sys.executable,'-c',script],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
