import aiohttp
import asyncio
import multiprocessing
import time
import os

NUM_COROUTINES = 1000
NUM_REQUESTS = 10000
NUM_WORKERS = int(os.getenv("GOMAXPROCS", multiprocessing.cpu_count() * 2))

async def worker(request_lock, session, url):
    async with session.head(url) as response:
        await response.text()
    request_lock.release()

async def main(loop):
    request_lock = asyncio.Semaphore(value=NUM_COROUTINES)

    conn = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(loop=loop, connector=conn) as session:
        tasks = []

        for j in range(int(NUM_REQUESTS / NUM_WORKERS)):
            await request_lock.acquire()
            task = worker(request_lock, session, 'http://127.0.0.1/')
            task = asyncio.ensure_future(task)
            tasks.append(task)

        await asyncio.wait(tasks)

def bench():
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main(loop))

if __name__ == '__main__':
    procs = []

    start = time.time()

    for _ in range(NUM_WORKERS):
        proc = multiprocessing.Process(target=bench)
        proc.start()
        procs.append(proc)

    for proc in procs:
        proc.join()

    total = time.time() - start
    print('%s HTTP requests in %.2f seconds, %.2f rps' % (NUM_REQUESTS, total, NUM_REQUESTS / total))
