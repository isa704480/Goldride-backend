import requests

API_URL = "http://localhost:8000/api/auth/admin/login/"
RIDES_URL = "http://localhost:8000/api/rides/admin/rides/"

def test_admin_api():
    try:
        # Login
        login_resp = requests.post(API_URL, json={'phone': 'admin', 'password': 'admin123'})
        if login_resp.status_code != 200:
            print(f"Login failed: {login_resp.status_code} {login_resp.text}")
            return
        
        token = login_resp.json()['access']
        print(f"Login success. Token: {token[:20]}...")

        # Get Rides
        headers = {'Authorization': f'Bearer {token}'}
        rides_resp = requests.get(RIDES_URL, headers=headers)
        print(f"Rides Status: {rides_resp.status_code}")
        if rides_resp.status_code == 200:
            data = rides_resp.json()
            print(f"Rides count: {len(data.get('rides', []))}")
            print(f"Pending requests count: {len(data.get('pending_requests', []))}")
            print(f"Data: {data}")
        else:
            print(f"Failed to get rides: {rides_resp.text}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_admin_api()
