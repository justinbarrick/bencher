#!/usr/bin/python2
import threading
from threading import Thread
import multiprocessing
from multiprocessing import Process
import time
import requests
import logging

def runner(func, times, *args):
    for _ in xrange(times):
        try:
            func(*args)
        except Exception as e:
            logging.error('Error in thread: %s' % e)

def bench(func, times, workers, bench_type, *args):
    logging.warning('%s:' % bench_type)

    threads = []
    each = int(times / workers)

    thread_type = Thread
    if bench_type == 'multiprocessing':
        thread_type = Process

    start_time = time.time()

    for _ in xrange(workers):
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

def read_10000_bytes():
    open('/dev/urandom', 'r').read(1000000)

def count_to_1000():
    a = 1
    for _ in xrange(1000):
        a *= 2

if __name__ == '__main__':
    multibench(read_10000_bytes, 4000, 100)

    multibench(count_to_1000, 100000, 100)

    lock = multiprocessing.Lock()
    multibench(acquire_mutex, 5000000, 100, lock)

    multibench(get_page, 4000, 100)
