import aiohttp
import asyncio
import multiprocessing
import time
import os

NUM_COROUTINES = 100
NUM_REQUESTS = 1000000
NUM_WORKERS = int(os.getenv("GOMAXPROCS", multiprocessing.cpu_count() * 2))

async def worker(session, url):
    for _ in range(int(NUM_REQUESTS / NUM_COROUTINES)):
        async with session.get(url) as response:
            await response.text()

async def main(loop):
    async with aiohttp.ClientSession(loop=loop) as session:
        tasks = []

        for _ in range(int(NUM_COROUTINES / NUM_WORKERS)):
            tasks.append(worker(session, 'http://127.0.0.1/'))

        await asyncio.gather(*tasks)

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
    print('%s HTTP requests in %.2f seconds, %.2f rps' % (NUM_REQUESTS, total, 1000000 / total))
