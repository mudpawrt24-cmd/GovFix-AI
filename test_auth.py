from app import app, DATABASE, read_admins, write_admins
import json

print('Starting test auth flows using Flask test client')

with app.test_client() as client:
    # 1) GET / to populate csrf in session
    r = client.get('/')
    assert r.status_code == 200
    # extract csrf from session via client
    with client.session_transaction() as sess:
        csrf = sess.get('csrf_token')
    print('CSRF token:', csrf)

    headers = {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}

    # 2) Test citizen signup
    payload = {'name': 'Test Farmer', 'mobile': '9876543211', 'password': 'Password123'}
    r = client.post('/auth/signup', data=json.dumps(payload), headers=headers)
    print('/auth/signup', r.status_code, r.get_json())
    assert r.status_code == 201

    # 3) Test citizen login
    payload = {'mobile': '9876543211', 'password': 'Password123'}
    r = client.post('/auth/login', data=json.dumps(payload), headers=headers)
    print('/auth/login', r.status_code, r.get_json())
    assert r.status_code == 200

    # 4) Test admin login using default superadmin
    payload = {'username': 'admin', 'password': 'AdminPass123'}
    r = client.post('/admin/login', data=json.dumps(payload), headers=headers)
    print('/admin/login', r.status_code, r.get_json())
    assert r.status_code == 200

    # 5) Create admin invite (requires admin session)
    payload = {'username': 'officer1', 'email': 'officer1@example.local'}
    r = client.post('/admin/invite', data=json.dumps(payload), headers=headers)
    print('/admin/invite', r.status_code, r.get_json())
    assert r.status_code == 200
    verify_link = r.get_json().get('verify_link')
    print('Verify link:', verify_link)

    # 6) Simulate clicking verification link
    token = verify_link.split('/')[-1]
    r = client.get(f'/admin/verify/{token}')
    print('/admin/verify', r.status_code, r.get_data(as_text=True))
    assert r.status_code == 200

    # 7) Attempt protected admin override
    payload = {'escalation_id': DATABASE['admin_escalations'][0]['escalation_id'], 'notes': 'Test override'}
    r = client.post('/api/admin/override-approve', data=json.dumps(payload), headers=headers)
    print('/api/admin/override-approve', r.status_code, r.get_json())
    assert r.status_code == 200

print('All tests passed')
