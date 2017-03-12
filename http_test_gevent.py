from gevent.pool import Pool
import requests
import time
import multiprocessing
import os

NUM_COROUTINES = 100
NUM_REQUESTS = 10000
NUM_WORKERS = int(os.getenv("GOMAXPROCS", multiprocessing.cpu_count() * 2))

def request(session, url):
    response = session.get(url)

def main():
    pool = Pool(NUM_COROUTINES)
    session = requests.Session()

    for _ in range(int(NUM_REQUESTS / NUM_WORKERS)):
        pool.spawn(request, session, 'http://127.0.0.1')

    pool.join()

if __name__ == '__main__':
    procs = []

    start = time.time()

    for _ in range(NUM_WORKERS):
        proc = multiprocessing.Process(target=main)
        proc.start()
        procs.append(proc)

    for proc in procs:
        proc.join()

    total = time.time() - start
    print('%s HTTP requests in %.2f seconds, %.2f rps' % (NUM_REQUESTS, total, NUM_REQUESTS / total))
