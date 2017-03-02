#!/usr/bin/python2
import types
import uuid
import socket
import select
import time
import logging

class ScheduleTask:
    def __init__(self, coroutine):
        self.coroutine = coroutine

class Scheduler:
    def __init__(self):
        self.coroutines = []
        self.coroutine_map = {}
        self.descriptors = []

    def add_coroutine(self, coroutine):
        self.coroutines.append(coroutine)

    def iterate(self):
        scheduled_coroutines = []

        logging.debug('invoking self.coroutines: %s' % self.coroutines)

        if not self.coroutines:
            time.sleep(0.01)

        for coroutine in self.coroutines:
            # Run the coroutine.
            try:
                args = self.coroutine_map.get(coroutine)

                logging.debug('calling %s with %s' % (coroutine, args))
                logging.debug('coroutine map: %s' % self.coroutine_map)

                if isinstance(args, types.GeneratorType):
                    # This is a child to parent mapping.
                    args = None
                elif coroutine in self.coroutine_map:
                    # We need to remove the return value so it doesn't get reused.
                    del self.coroutine_map[coroutine]

                result = coroutine.send(args)
            except StopIteration:
                # The coroutine completed, so schedule the parent, if any.
                parent = self.get_parent(coroutine)
                if parent:
                    scheduled_coroutines.append(parent)
                continue

            # If the coroutine returns nothing, then we schedule it for execution.
            if not result:
                scheduled_coroutines.append(coroutine)
                continue

            logging.debug('got %s from %s' % (result, coroutine))

            # Inherits from NonBlocking, schedule the descriptor and add a mapping.
            if isinstance(result, NonBlocking):
                self.coroutine_map[result] = coroutine
                self.descriptors.append(result)
            # It's a ScheduleTask object, schedule the task and the parent (don't
            # associate the task with the parent - "threads")
            elif isinstance(result, ScheduleTask):
                scheduled_coroutines.append(result.coroutine)
                scheduled_coroutines.append(coroutine)
            # Schedule the new generator and map it to the parent.
            elif isinstance(result, types.GeneratorType):
                scheduled_coroutines.append(result)
                self.coroutine_map[result] = coroutine
            # Otherwise call the coroutine again so that it completes and then
            # store the result.
            else:
                try:
                    next(coroutine)
                except StopIteration:
                    pass

                parent = self.get_parent(coroutine)
                if parent:
                    scheduled_coroutines.append(parent)
                    self.coroutine_map[parent] = result

        self.coroutines = scheduled_coroutines
        self.poll_descriptors()

    def poll_descriptors(self):
        self.descriptors = [ d for d in self.descriptors if not d.closed ]
        logging.debug('Invoking descriptors: %s' % self.descriptors)
        writable = [ d for d in self.descriptors if d.writable ]
        readable = [ d for d in self.descriptors if d.readable ]

        readable, writable, _ = select.select(readable, writable, [], 0)
        for descriptor in set(readable).union(set(writable)):
            logging.debug('%s is active! scheduling %s' % (descriptor, self.coroutine_map[descriptor]))
            self.coroutines.append(self.coroutine_map[descriptor])
            del self.coroutine_map[descriptor]

    def get_parent(self, coroutine):
        if coroutine in self.coroutine_map:
            parent = self.coroutine_map[coroutine]
            del self.coroutine_map[coroutine]
            return parent

    def run_until_complete(self):
        while self.coroutines or self.descriptors:
            self.iterate()

class NonBlocking(object):
    def __init__(self):
        self.writable = False
        self.readable = False

    def fileno(self):
        raise NotImplemented

class Socket(NonBlocking):
    def __init__(self, sock=None):
        self.sock = sock or socket.socket()
        self.sock.setblocking(0)
        self.writable = False
        self.readable = False
        self.closed = False

    def getsockname(self):
        return self.sock.getsockname()

    def bind(self, addr):
        return self.sock.bind(addr)

    def listen(self, num):
        return self.sock.listen(num)

    def accept(self):
        self.readable = True

        yield self

        client, addr = self.sock.accept()
        self.readable = False

        yield addr, Socket(client)

    def connect(self, host):
        self.writable = True

        yield self

        self.writable = False

        try:
            yield self.sock.connect(host)
        except socket.error:
            pass

    def send(self, data):
        self.writable = True

        sent_bytes = 0
        while sent_bytes < len(data):
            yield self
            sent_bytes += self.sock.send(data[sent_bytes:])

        self.writable = False

    def recv(self, num_bytes):
        self.readable = True
        yield self
        self.readable = False
        yield self.sock.recv(num_bytes)

    def close(self):
        self.closed = True
        return self.sock.close()

    def fileno(self):
        return self.sock.fileno()

def test_coroutine(arg=None):
    print 'in coroutine: %s' % arg
    yield arg
    print 'end coroutine'

def test(arg=None):
    print 'in test: %s' % arg

    result = yield test_coroutine(arg)

    print 'end test: %s' % result
    print 'expected: %s, actual: %s' % (arg, result)
    assert result == arg

def a_long_test():
    print 'in a_long_test'
    result = yield test_coroutine()
    print result
    assert result == None

    print 'second part of a long test'
    result = yield test('hello')
    assert result == 'hello'

    print 'third part of a long test'
    result = yield test_coroutine()
    assert result == None

    print 'fourth part of a long test'
    result = yield test('hello')
    assert result == 'hello'

def network_test(google):
    sock = Socket()

    yield sock.connect((google, 80))
    print 'Connected to google!'
    yield sock.send('GET / HTTP/1.1\r\nHost: google.com\r\n\r\n')
    print 'Send data to google!'

    data = yield sock.recv(4096)
    print 'Received data from google: %s' % data.split('\r\n')[0]

    yield sock.close()
    print 'Closed connection to google.'

def test_client(port, data):
    client = Socket()

    print 'Connecting to test server at %d' % port
    yield client.connect(('127.0.0.1', port))

    print 'Sending "%s" to test server at port %d' % (data, port)
    yield client.send(data)

    print 'Receiving from test server %d' % port
    received = yield client.recv(4096)

    print 'Received "%s" from %d (expected: "%s")' % (received, port, data)
    assert received == data

    yield client.close()

def test_handle_client(client, addr):
    print 'Handling client from %s:%d' % addr
    received = yield client.recv(4096)

    print 'Echoing "%s" back to client.' % received
    yield client.send(received)
    yield client.close()

def launch_clients(port, num_clients):
    for index in range(num_clients):
        print 'Launching to client to say "hello %d"' % index
        yield ScheduleTask(test_client(port, 'hello %d' % index))

def accept_clients(server, num_clients):
    print 'Accepting clients.'
    for _ in range(num_clients):
        addr, client = yield server.accept()
        yield ScheduleTask(test_handle_client(client, addr))

    yield server.close()

def test_server():
    server = Socket()

    server.bind(('127.0.0.1', 0))
    server.listen(5)

    addr, port = server.getsockname()

    print 'Bound to port %d, launching clients.' % port
    yield ScheduleTask(launch_clients(port, 15))
    yield ScheduleTask(accept_clients(server, 15))

if __name__ == '__main__':
    google = socket.gethostbyname('google.com')

    coroutines = Scheduler()
    coroutines.add_coroutine(test())
    coroutines.add_coroutine(a_long_test())
    coroutines.add_coroutine(test())
    coroutines.add_coroutine(test('helloooo'))

    for _ in range(100):
        coroutines.add_coroutine(network_test(google))

    coroutines.add_coroutine(test())
    coroutines.add_coroutine(test())
    coroutines.add_coroutine(test_server())
    coroutines.run_until_complete()
