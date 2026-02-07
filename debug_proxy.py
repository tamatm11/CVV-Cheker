import requests
import sys

# Configuration
BINLIST_API = "https://lookup.binlist.net/457173"
HANDY_API = "https://data.handyapi.com/bin/457173"
PAYSTACK_API = "https://api.paystack.co/decision/bin/457173"

HEADERS = {
    'Accept-Version': '3',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def load_proxy():
    try:
        with open("proxy.txt", "r") as f:
            line = f.read().strip()
            parts = line.split(":")
            if len(parts) == 4:
                host, port, user, password = parts[0], parts[1], parts[2], parts[3]
                fmt = f"http://{user}:{password}@{host}:{port}"
                return {"http": fmt, "https": fmt}
            return None
    except Exception as e:
        print(f"Error reading proxy file: {e}")
        return None

def test_proxy():
    proxy = load_proxy()
    if not proxy:
        print("No valid proxy found in proxy.txt")
        return

    print(f"Testing with proxy: {proxy['http']}")
    
    apis = [BINLIST_API, HANDY_API, PAYSTACK_API]
    
    for url in apis:
        print(f"\nTesting URL: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, proxies=proxy, timeout=10)
            print(f"Status Code: {resp.status_code}")
            print(f"Response: {resp.text[:100]}...")
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    test_proxy()
