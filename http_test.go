package main

import (
    "crypto/tls"
    "io/ioutil"
    "net/http"
    "golang.org/x/net/http2"
    "sync"
    "testing"
    "time"
)

func BenchmarkHTTP(b *testing.B) {
    workers := 100
    requests := 100000

    transport := &http.Transport {
        MaxIdleConnsPerHost: 100,
    }

    client := &http.Client {
        Transport: transport,
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
                    b.Fatal(err)
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

func BenchmarkHTTPS(b *testing.B) {
    workers := 100
    requests := 100000

    transport := &http.Transport {
        MaxIdleConnsPerHost: 100,
        TLSClientConfig: &tls.Config {
            InsecureSkipVerify: true,
        },
    }

    client := &http.Client {
        Transport: transport,
    }

    var wg sync.WaitGroup
    wg.Add(workers)

    start := time.Now()

    for i := 0; i < workers; i++ {
        go func() {
            defer wg.Done()

            for j := 0; j < (requests / workers); j++ {
                res, err := client.Head("https://127.0.0.1/")

                if err != nil {
                    b.Fatal(err)
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
func BenchmarkHTTP2(b *testing.B) {
    workers := 100
    requests := 100000

    transport := &http.Transport {
        MaxIdleConnsPerHost: 100,
        TLSClientConfig: &tls.Config {
            InsecureSkipVerify: true,
        },
    }

    http2.ConfigureTransport(transport)

    client := &http.Client {
        Transport: transport,
    }

    var wg sync.WaitGroup
    wg.Add(workers)

    start := time.Now()

    for i := 0; i < workers; i++ {
        go func() {
            defer wg.Done()

            for j := 0; j < (requests / workers); j++ {
                res, err := client.Head("https://127.0.0.1/")

                if err != nil {
                    b.Fatal(err)
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
