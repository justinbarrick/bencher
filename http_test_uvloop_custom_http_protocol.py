import asyncio
import uvloop
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
import multiprocessing
import time
import os

NUM_COROUTINES = 1000
NUM_REQUESTS = 100000
NUM_WORKERS = int(os.getenv("GOMAXPROCS", multiprocessing.cpu_count() * 2))

class Connection(asyncio.Protocol):
    def __init__(self, host, port, pool_available, loop):
        # Whether or not a connection is established.
        self.connected = asyncio.Event(loop=loop)
        # Whether or not data is available.
        self.data_available = asyncio.Event(loop=loop)

        self.lock = asyncio.Lock()
        self.pool_available = pool_available

        self.buffered = b''

        self.host = host
        self.port = port

        self.loop = loop
        self.conn = None
        self.connect_count = 0

    # Asychronous protocol handlers.
    def connection_made(self, transport):
        self.transport = transport
        self.connected.set()

    def connection_lost(self, exc):
        self.data_available.set()
        self.connected.clear()
        self.conn = None

    def data_received(self, data):
        self.buffered += data
        self.data_available.set()

    # Coroutines used by pool / user.
    async def connect(self):
        """
        Return immediately if already connected, otherwise open a new connection and wait
        for it to be established.
        """
        if self.connected.is_set():
            return

        self.connected.clear()
        self.data_available.clear()

        self.connect_count += 1
        _, self.conn = await self.loop.create_connection(lambda: self, self.host, self.port)

        await self.connected.wait()

    async def read(self, num_bytes):
        """
        Wait for data to be available and then return it.
        """
        if not self.connected.is_set():
            return

        await self.data_available.wait()
        self.data_available.clear()

        data = self.buffered
        self.buffered = b''

        return data

    async def send(self, message):
        """
        Send data through the socket.
        """
        await self.connect()
        self.transport.write(message.encode())

    async def acquire(self):
        """
        Lock the connection for use.
        """
        await self.lock.acquire()

    def release(self):
        """
        Release the connection back into the pool.
        """
        self.lock.release()
        self.pool_available.release()

    def locked(self):
        """
        Check if the connection is locked.
        """
        return self.lock.locked()

    def close(self):
        """
        Close the connection.
        """
        self.conn.close()
        self.conn = None

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
    await request_lock.acquire()

    connection = await session.connect()

    await connection.send("""HEAD / HTTP/1.1
Host: 127.0.0.1
User-Agent: fast-af

""")

    response = await connection.read(65535)
    if not response:
        print('Connection closed.')
    elif b'HTTP/1.1 200 OK' not in response:
        print(response)
        connection.close()

    connection.release()
    request_lock.release()

async def main(loop):
    request_lock = asyncio.Semaphore(value=NUM_COROUTINES)

    session = Pool('127.0.0.1', 80, 10, loop)

    tasks = []

    num_requests = int(NUM_REQUESTS / NUM_WORKERS)

    for j in range(num_requests):
        task = worker(request_lock, session)
        task = asyncio.ensure_future(task)
        tasks.append(task)

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    for d in done:
        pass
        #print(d)

    connect_count = await session.stats()
    print('Requests per connection: {}'.format(num_requests / connect_count))

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
