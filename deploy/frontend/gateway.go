// The local TCP bridge sends Nginx TLS connections through Tailscale's
// userspace HTTP CONNECT proxy without terminating or inspecting TLS.
package main

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"os/signal"
	"strings"
	"syscall"
	"time"
)

func bridge(client net.Conn, target string) {
	defer client.Close()
	upstream, err := net.DialTimeout("tcp", "127.0.0.1:1055", 10*time.Second)
	if err != nil {
		log.Printf("Tailscale proxy: %v", err)
		return
	}
	defer upstream.Close()
	_ = upstream.SetDeadline(time.Now().Add(30 * time.Second))
	_, err = fmt.Fprintf(upstream, "CONNECT %s HTTP/1.1\r\nHost: %s\r\n\r\n", target, target)
	if err != nil {
		log.Printf("CONNECT write: %v", err)
		return
	}
	reader := bufio.NewReader(upstream)
	response, err := http.ReadResponse(reader, &http.Request{Method: http.MethodConnect})
	if err != nil {
		log.Printf("CONNECT response: %v", err)
		return
	}
	if response.StatusCode != http.StatusOK {
		log.Printf("CONNECT rejected: %s", response.Status)
		return
	}
	_ = upstream.SetDeadline(time.Time{})
	done := make(chan struct{})
	go func() { _, _ = io.Copy(upstream, client); close(done) }()
	_, _ = io.Copy(client, reader)
	_ = client.Close()
	_ = upstream.Close()
	<-done
}

func run() error {
	host := os.Getenv("SPARK_TAILSCALE_HOST")
	if host == "" || strings.ContainsAny(host, ":/ \r\n") {
		return fmt.Errorf("invalid SPARK_TAILSCALE_HOST")
	}
	target := net.JoinHostPort(host, "443")
	// The volume root may belong to a different UID on OpenShift. Tailscale
	// chmods its state directory, so use a child owned by this container user.
	if err := os.MkdirAll("/var/lib/tailscale/private", 0700); err != nil {
		return fmt.Errorf("create Tailscale state directory: %w", err)
	}
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer cancel()
	daemon := exec.CommandContext(ctx, "tailscaled", "--tun=userspace-networking", "--state=/var/lib/tailscale/private/tailscaled.state", "--socket=/tmp/tailscaled.sock", "--outbound-http-proxy-listen=127.0.0.1:1055")
	daemon.Stdout, daemon.Stderr = os.Stdout, os.Stderr
	if err := daemon.Start(); err != nil {
		return err
	}
	daemonDone := make(chan error, 1)
	go func() { daemonDone <- daemon.Wait(); cancel() }()
	defer func() { cancel(); <-daemonDone }()
	for i := 0; i < 100; i++ {
		if ctx.Err() != nil {
			return fmt.Errorf("tailscaled stopped during startup")
		}
		if _, err := os.Stat("/tmp/tailscaled.sock"); err == nil {
			break
		}
		time.Sleep(100 * time.Millisecond)
	}
	login := exec.CommandContext(ctx, "tailscale", "--socket=/tmp/tailscaled.sock", "up", "--auth-key=file:/var/run/tailscale-auth/authkey", "--hostname=event-frontend")
	login.Stdout, login.Stderr = os.Stdout, os.Stderr
	if err := login.Run(); err != nil {
		return fmt.Errorf("Tailscale authentication: %w", err)
	}
	listener, err := net.Listen("tcp", "127.0.0.1:10443")
	if err != nil {
		return err
	}
	defer listener.Close()
	go func() { <-ctx.Done(); _ = listener.Close() }()
	go func() {
		for {
			c, err := listener.Accept()
			if err != nil {
				return
			}
			go bridge(c, target)
		}
	}()
	nginx := exec.CommandContext(ctx, "nginx", "-g", "daemon off;")
	nginx.Stdout, nginx.Stderr = os.Stdout, os.Stderr
	if err := nginx.Run(); err != nil && ctx.Err() == nil {
		return fmt.Errorf("nginx: %w", err)
	}
	return ctx.Err()
}

func main() {
	if err := run(); err != nil && err != context.Canceled {
		log.Fatal(err)
	}
}
