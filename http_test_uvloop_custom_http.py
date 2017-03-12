import asyncio
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import multiprocessing
import time
import os

NUM_COROUTINES = 1000
NUM_REQUESTS = 100000
NUM_WORKERS = int(os.getenv("GOMAXPROCS", multiprocessing.cpu_count() * 2))

class Connection:
    def __init__(self, host, port, pool_available, loop):
        self.lock = asyncio.Lock()
        self.reader = None
        self.writer = None
        self.host = host
        self.port = port
        self.loop = loop
        self.pool_available = pool_available
        self.connect_count = 0

    async def connect(self):
        self.connect_count += 1
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port, loop=self.loop)

    async def read(self, num_bytes):
        if not self.reader:
            await self.connect()

        return await self.reader.read(num_bytes)

    async def send(self, message):
        if not self.writer:
            await self.connect()

        self.writer.write(message.encode())

    async def acquire(self):
        await self.lock.acquire()

    def release(self):
        self.lock.release()
        self.pool_available.release()

    def locked(self):
        return self.lock.locked()

    def close(self):
        self.writer.close()
        self.writer = None
        self.reader = None

class Pool:
    def __init__(self, host, port, conn_limit, loop):
        self.conn_limit = conn_limit

        self.host = host
        self.port = port

        self.loop = loop

        self.pool = []
        self.pool_available = asyncio.Semaphore(self.conn_limit)
        self.pool_lock = asyncio.Lock()

    async def connect(self):
        await self.pool_available.acquire()

        c = None

        async with self.pool_lock:
            if len(self.pool) < self.conn_limit:
                c = Connection(self.host, self.port, self.pool_available, self.loop)
                await c.acquire()
                self.pool.append(c)
            else:
                for i, connection in enumerate(self.pool):
                    if not connection.locked():
                        await connection.acquire()
                        c = connection
                        break

        return c

    async def stats(self):
        connections = 0

        async with self.pool_lock:
            for connection in self.pool:
                connections += connection.connect_count

        return connections

async def worker(request_lock, session):
    connection = await session.connect()

    await connection.send("""HEAD / HTTP/1.1
Host: 127.0.0.1
User-Agent: fast-af

""")

    response = await connection.read(65535)
    if b'HTTP/1.1 200 OK' not in response:
        connection.close()

    connection.release()
    request_lock.release()

async def main(loop):
    request_lock = asyncio.Semaphore(value=NUM_COROUTINES)

    session = Pool('127.0.0.1', 80, 10, loop)

    tasks = []

    for j in range(int(NUM_REQUESTS / NUM_WORKERS)):
        await request_lock.acquire()
        task = worker(request_lock, session)
        task = asyncio.ensure_future(task)
        tasks.append(task)

    await asyncio.wait(tasks)

    connect_count = await session.stats()
    print('Requests per connection: {}'.format(NUM_REQUESTS / connect_count))

def bench():
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main(loop))

if __name__ == '__main__':
    procs = []

    start = time.time()

    if NUM_WORKERS > 1:
        for _ in range(NUM_WORKERS):
            proc = multiprocessing.Process(target=bench)
            proc.start()
            procs.append(proc)

        for proc in procs:
            proc.join()
    else:
        bench()

    total = time.time() - start
    print('%s HTTP requests in %.2f seconds, %.2f rps' % (NUM_REQUESTS, total, NUM_REQUESTS / total))
