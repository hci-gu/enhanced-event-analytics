package main

import (
	"bufio"
	"fmt"
	"io"
	"net"
	"net/http"
	"testing"
	"time"
)

func TestBridgeConnectsAndRelays(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:1055")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	result := make(chan error, 1)
	go func() {
		conn, err := listener.Accept()
		if err != nil {
			result <- err
			return
		}
		defer conn.Close()
		_ = conn.SetDeadline(time.Now().Add(5 * time.Second))
		reader := bufio.NewReader(conn)
		req, err := http.ReadRequest(reader)
		if err != nil {
			result <- err
			return
		}
		if req.Method != http.MethodConnect || req.Host != "spark.example:443" {
			result <- fmt.Errorf("unexpected CONNECT: %s %s", req.Method, req.Host)
			return
		}
		if _, err = io.WriteString(conn, "HTTP/1.1 200 Connection Established\r\n\r\n"); err != nil {
			result <- err
			return
		}
		buf := make([]byte, 4)
		if _, err = io.ReadFull(reader, buf); err != nil {
			result <- err
			return
		}
		if string(buf) != "ping" {
			result <- fmt.Errorf("unexpected data: %q", buf)
			return
		}
		_, err = io.WriteString(conn, "pong")
		result <- err
	}()
	client, server := net.Pipe()
	defer client.Close()
	_ = client.SetDeadline(time.Now().Add(5 * time.Second))
	go bridge(server, "spark.example:443")
	if _, err = io.WriteString(client, "ping"); err != nil {
		t.Fatal(err)
	}
	buf := make([]byte, 4)
	if _, err = io.ReadFull(client, buf); err != nil {
		t.Fatal(err)
	}
	if string(buf) != "pong" {
		t.Fatalf("unexpected response %q", buf)
	}
	if err = <-result; err != nil {
		t.Fatal(err)
	}
}
