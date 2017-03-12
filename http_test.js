var http = require('http');
var async = require('async');
var cluster = require('cluster');

var NUM_WORKERS = require('os').cpus().length * 2;
var NUM_REQUESTS = 10000;

function do_request(i, callback) {
    request = {
        agent: session,
        method: 'HEAD',
        hostname: '127.0.0.1',
        port: 80,
        path: '/',

    };

    req = http.request(request, function(res) {
        res.resume();

        res.on('end', function() {
            callback();
        })
    })
    
    req.on('error', function(error) {
        console.log(error)
        callback();
    });

    req.end();
}

if(cluster.isMaster) {
    var start = new Date();

    for(var i=0; i<NUM_WORKERS; i++) {
        cluster.fork();
    }

    var exited = 0;

    cluster.on('exit', function(worker, code, signal) {
        if(exited == NUM_WORKERS - 1) {
            var elapsed = ((new Date()) - start) / 1000;
            console.log('completed in', elapsed, 'seconds.', NUM_REQUESTS / elapsed, 'rps');
        } else {
            exited++;
        }
    });
} else {
    var session = new http.Agent({ keepAlive: true });

    var nums = [];
    for(var i=0; i<NUM_REQUESTS/NUM_WORKERS; i++) {
        nums.push(i);
    }

    async.eachLimit(nums, 100, do_request, function(err) {
        process.exit()
    });
}
