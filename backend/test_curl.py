import requests

login = requests.post("http://localhost:8000/api/v1/auth/login", json={"username": "tawssil_admin", "password": "password"}).json()
print("Login:", login)

token = login.get("access_token")
headers = {"Authorization": f"Bearer {token}"}
res = requests.get("http://localhost:8000/api/v1/developers/team-kpis?project_id=1", headers=headers)
print("KPIs:", res.status_code, res.json())
