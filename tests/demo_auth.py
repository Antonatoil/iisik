"""Log in seeded demo accounts with JWT for compatibility regressions."""
import os
from functools import lru_cache

DEMO_USERS = {
  'demo-student-token': 'student@example.test',
  'demo-student2-token': 'student2@example.test',
  'demo-teacher-token': 'math@example.test',
  'demo-admin-token': 'admin@example.test',
}

@lru_cache(maxsize=4)
def demo_token(legacy_label):
    """For tests only: obtain a genuine JWT instead of accepting old bearer strings."""
    from fastapi.testclient import TestClient
    from app.main import app
    if legacy_label not in DEMO_USERS:
        return legacy_label
    secret = os.environ['LAB5_DEMO_PASSWORD']
    with TestClient(app) as client:
        result=client.post('/graphql/',json={
            'query':'mutation($input: LoginInput!) { login(input:$input) { token } }',
            'variables':{'input':{'email':DEMO_USERS[legacy_label], 'password':secret}}
        })
    data=result.json()
    assert 'errors' not in data, data
    return data['data']['login']['token']
