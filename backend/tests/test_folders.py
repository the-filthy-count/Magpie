def test_folders_require_auth(client):
    assert client.get('/api/folders').status_code == 401

def test_folder_browser_boundaries(admin, tmp_path):
    root = admin.root
    (root / 'Pictures').mkdir()
    (root / 'Private file.txt').write_text('not a directory')
    outside = tmp_path / 'outside'; outside.mkdir()
    (root / 'escape').symlink_to(outside, target_is_directory=True)
    data = admin.get('/api/folders').json()
    assert data['folders'] == [str(root)]
    data = admin.get('/api/folders', params={'path': str(root)}).json()
    assert data['folders'] == [str(root / 'Pictures')]
    assert data['parent'] == ''
    assert admin.get('/api/folders', params={'path': str(outside)}).status_code == 400
    assert admin.get('/api/folders', params={'path': str(root / 'escape')}).status_code == 400
    assert admin.get('/api/folders', params={'path': str(root) + '/../outside'}).status_code == 400
    data = admin.get('/api/folders', params={'path': str(root / 'pi'), 'suggest': True}).json()
    assert data['folders'] == [str(root / 'Pictures')]
    assert admin.get('/api/folders', params={'path': str(root) + '/'}).json()['path'] == str(root)

def test_media_and_heart_icons(admin):
    for icon in ('video', 'film', 'music', 'headphones', 'camera', 'heart'):
        folder = admin.root / icon; folder.mkdir()
        response = admin.post('/api/destinations', json={'name': icon, 'path': str(folder), 'icon': icon})
        assert response.status_code == 201
        assert response.json()['icon'] == icon
