#!/usr/bin/python2
import types
import uuid
import socket
import select
import time

class Scheduler:
    def __init__(self):
        self.coroutines = []
        self.coroutine_map = {}
        self.descriptors = []

    def add_coroutine(self, coroutine):
        self.coroutines.append(coroutine)

    def iterate(self):
        scheduled_coroutines = []

        print '\n[!] invoking self.coroutines: %s' % self.coroutines

        if not self.coroutines:
            time.sleep(0.01)

        for coroutine in self.coroutines:
            if isinstance(coroutine, types.FunctionType) or isinstance(coroutine, types.FunctionType):
                coroutine = (coroutine,)

            # It's a function, argument pair that hasn't been started yet.
            if isinstance(coroutine, tuple):
                identifier = None
                if len(coroutine) == 3:
                    identifier = coroutine[2]

                args = ()
                if len(coroutine) > 1:
                    args = coroutine[1]

                # Run the function.
                print 'calling %s with %s (%s)' % (coroutine[0], args, identifier)
                result = coroutine[0](*args)
                if isinstance(result, types.GeneratorType):
                    # Got a new coroutine, add it to the maps and schedule it.
                    if identifier:
                        self.coroutine_map[result] = self.coroutine_map[identifier]
                        del self.coroutine_map[identifier]
                    scheduled_coroutines.append(result)
                # Got a return value: set it and reschedule parent.
                elif identifier and identifier in self.coroutine_map:
                        parent = self.coroutine_map[identifier]
                        scheduled_coroutines.append(parent)
                        self.coroutine_map[parent] = result
                        del self.coroutine_map[identifier]
                        print 'Scheduled parent %s with %s' % (parent, result)

                continue

            # Run the coroutine.
            try:
                args = self.coroutine_map.get(coroutine)
                print 'calling %s with %s' % (coroutine, args)
                print 'coroutine map: %s' % self.coroutine_map
                if isinstance(args, types.GeneratorType):
                    # This is a child to parent mapping.
                    args = None
                elif coroutine in self.coroutine_map:
                    # We need to remove the return value so it doesn't get reused.
                    del self.coroutine_map[coroutine]

                result = coroutine.send(args)
            except StopIteration:
                if coroutine in self.coroutine_map:
                    parent = self.coroutine_map[coroutine]
                    scheduled_coroutines.append(parent)
                    del self.coroutine_map[coroutine]

                continue

            # If the coroutine returns nothing, then we schedule it for execution.
            if not result:
                scheduled_coroutines.append(coroutine)
                continue

            func = result
            args = ()
            if isinstance(func, tuple):
                args = func[1]
                func = func[0]

            identifier = '%s%s' % (func, uuid.uuid4())
            print 'got %s from %s (%s)' % (result, coroutine, identifier)

            if isinstance(func, NonBlocking):
                self.coroutine_map[func] = coroutine
                self.descriptors.append(func)
            # If the returned value is not a function, call the coroutine again
            # so that it completes and then store the result.
            elif not isinstance(func, types.FunctionType) and not isinstance(func, types.MethodType):
                try:
                    next(coroutine)
                except StopIteration:
                    pass

                print coroutine, self.coroutine_map.get(coroutine), self.coroutine_map
                # Store the result here with the coroutine's parent and reschedule
                # the parent coroutine.
                if coroutine in self.coroutine_map:
                    parent = self.coroutine_map[coroutine]
                    self.coroutine_map[parent] = result
                    scheduled_coroutines.append(parent)
                    del self.coroutine_map[coroutine]
            else:
                # Store the parent coroutine with the identifier
                # and schedule the new coroutine for execution.
                self.coroutine_map[identifier] = coroutine
                scheduled_coroutines.append((func, args, identifier))

        self.descriptors = [ d for d in self.descriptors if not d.closed ]
        print 'Invoking descriptors: %s' % self.descriptors
        writable = [ d for d in self.descriptors if d.writable ]
        readable = [ d for d in self.descriptors if d.readable ]

        readable, writable, _ = select.select(readable, writable, [], 0)
        for descriptor in set(readable).union(set(writable)):
            print '%s is active! scheduling %s' % (descriptor, self.coroutine_map[descriptor])
            scheduled_coroutines.append(self.coroutine_map[descriptor])
            del self.coroutine_map[descriptor]

        self.coroutines = scheduled_coroutines

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
    def __init__(self):
        self.sock = socket.socket()
        self.sock.setblocking(0)
        self.writable = False
        self.readable = False
        self.closed = False

    def connect(self, host):
        self.writable = True

        yield self

        self.writable = False
        print 'got host! %s' % (host,)

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
    print 'end coroutine'
    return arg

def test(arg=None):
    print 'in test: %s' % arg

    if arg:
        result = yield (test_coroutine, (arg,))
    else:
        result = yield test_coroutine

    print 'end test: %s' % result
    print 'expected: %s, actual: %s' % (arg, result)
    assert result == arg

def a_long_test():
    print 'in a_long_test'
    result = yield test
    print result
    assert result == None

    print 'second part of a long test'
    result = yield test, ('hello', )
    assert result == 'hello'

    print 'third part of a long test'
    result = yield test_coroutine
    assert result == None

    print 'fourth part of a long test'
    result = yield test_coroutine, ('hello', )
    assert result == 'hello'

def network_test(google):
    sock = Socket()

    yield sock.connect, ((google, 80),)
    print 'Connected to google!'
    yield sock.send, ('GET / HTTP/1.1\r\nHost: google.com\r\n\r\n',)
    print 'Send data to google!'

    data = yield sock.recv, (4096,)
    print 'Received data from google: %s' % data

    yield sock.close
    print 'Closed connection to google.'

if __name__ == '__main__':
    google = socket.gethostbyname('google.com')

    coroutines = Scheduler()
    coroutines.add_coroutine(test)
    coroutines.add_coroutine(a_long_test)
    coroutines.add_coroutine(test())
    coroutines.add_coroutine((test, ('helloooo', )))

    for _ in range(100):
        coroutines.add_coroutine((network_test, (google,)))

    coroutines.add_coroutine(test)
    coroutines.add_coroutine(test)
    coroutines.run_until_complete()
