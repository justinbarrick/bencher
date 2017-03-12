package main

import (
    "io/ioutil"
    "net/http"
    "sync"
    "testing"
    "time"
)

func BenchmarkHandleStructAdd(b *testing.B) {
    workers := 100
    requests := 100000

    client := &http.Client {
        Transport: &http.Transport {
            MaxIdleConnsPerHost: workers,
        },
    }

    var wg sync.WaitGroup
    wg.Add(workers)

    start := time.Now()

    for i := 0; i < workers; i++ {
        go func() {
            defer wg.Done()

            for j := 0; j < (requests / workers); j++ {
                res, err := client.Head("http://127.0.0.1/")

                if err != nil {
                    continue
                }

                ioutil.ReadAll(res.Body)
                res.Body.Close()
            }
        }()
    }

    wg.Wait()

    total := time.Since(start)
    rps := float64(requests) / total.Seconds()

    b.Log(requests, "HTTP requests in", total.Seconds(), "seconds,", rps, "rps")
}
