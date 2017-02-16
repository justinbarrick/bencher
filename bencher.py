#!/usr/bin/python3
import threading
from threading import Thread
import multiprocessing
from multiprocessing import Process
import time
import requests
import logging
logging.basicConfig(level=logging.WARNING, format='[%(process)s] [%(threadName)s] [%(filename)s:%(lineno)s] [%(levelname)s] %(message)s')
import queue
import string
import random
import faulthandler
import signal
import code, traceback, signal

# http://stackoverflow.com/a/133384
def debug(sig, frame):
    """Interrupt running process, and provide a python prompt for
    interactive debugging."""
    d={'_frame':frame}         # Allow access to frame object.
    d.update(frame.f_globals)  # Unless shadowed by global
    d.update(frame.f_locals)

    i = code.InteractiveConsole(d)
    message  = "Signal received : entering python shell.\nTraceback:\n"
    message += ''.join(traceback.format_stack(frame))
    i.interact(message)

def runner(func, times, *args):
    logging.info('entering runner')

    for _ in range(times):
        try:
            func(*args)
        except Exception as e:
            logging.error('Error in thread: %s' % e)

    logging.info('leaving runner')

def bench(func, times, workers, bench_type, *args):
    logging.warning('%s:' % bench_type)

    threads = []
    each = int(times / workers)

    thread_type = Thread
    if bench_type == 'multiprocessing':
        thread_type = Process

    start_time = time.time()

    for _ in range(workers):
        if bench_type == 'single threaded':
            runner(*((func, each,) + args))
        else:
            t = thread_type(target=runner, args=(func, each,) + args)
            t.start()
            threads.append(t)

    if bench_type != 'single threaded':
        for thread in threads:
            thread.join()

    logging.warning('Completed in %d seconds.' % (time.time() - start_time))

def multibench(func, times, workers, *args):
    logging.warning('Running %s %d times with %d workers.' % (func, times, workers))
    bench(func, times, workers, 'threading', *args)
    bench(func, times, workers, 'single threaded', *args)
    bench(func, times, workers, 'multiprocessing', *args)
    logging.warning('')

def acquire_mutex(lock):
    lock.acquire()
    lock.release()

def get_page():
    requests.get('http://127.0.0.1').content

def read_1000000_bytes():
    open('/dev/urandom', 'rb').read(1000000)

def count_to_1000():
    a = 1
    for _ in range(1000):
        a *= 2

def do_queue(q):
    action = random.choice(['get', 'put'])
    q.cancel_join_thread()

    if action == 'get':
        logging.info('getting from queue size: %s' % (q.qsize()))
        try:
            q.get(block=False)
        except queue.Empty:
            pass
    else:
        logging.info('inserting into queue size: %s' % (q.qsize()))
        q.put(random.choice(string.ascii_letters), block=False)

    logging.info('operations completed!')

if __name__ == '__main__':
    faulthandler.register(signal.SIGUSR1)
    signal.signal(signal.SIGUSR2, debug)

    q = multiprocessing.Queue()
    multibench(do_queue, 500000, 100, q)

    multibench(read_1000000_bytes, 4000, 100)

    multibench(count_to_1000, 100000, 100)

    lock = multiprocessing.Lock()
    multibench(acquire_mutex, 5000000, 100, lock)

    multibench(get_page, 4000, 100)


