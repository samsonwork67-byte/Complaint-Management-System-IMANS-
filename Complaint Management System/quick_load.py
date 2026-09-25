import threading
import urllib.request
import urllib.parse
import http.cookiejar
import time

HOST = 'http://127.0.0.1:5000'
NUM_THREADS = 10


def worker(i):
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        # login
        data = urllib.parse.urlencode({'username': 'admin', 'password': '1234'}).encode()
        req = urllib.request.Request(HOST + '/login', data=data, method='POST')
        resp = opener.open(req, timeout=5)
        print(f"[{i}] login -> {resp.getcode()}")
    except Exception as e:
        print(f"[{i}] login error: {e}")
        return
    try:
        # check session
        resp = opener.open(HOST + '/api/me', timeout=5)
        body = resp.read().decode()[:200]
        print(f"[{i}] /api/me -> {resp.getcode()} {body}")
    except Exception as e:
        print(f"[{i}] /api/me error: {e}")
    try:
        resp = opener.open(HOST + '/api/audit-log/feed?limit=30', timeout=5)
        body = resp.read().decode()[:200]
        print(f"[{i}] /api/audit-log/feed -> {resp.getcode()} {body}")
    except Exception as e:
        print(f"[{i}] feed error: {e}")


threads = []
for i in range(NUM_THREADS):
    t = threading.Thread(target=worker, args=(i,))
    t.start()
    threads.append(t)
    time.sleep(0.1)

for t in threads:
    t.join()

print('done')
