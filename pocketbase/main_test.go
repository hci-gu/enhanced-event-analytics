package main

import "testing"

func TestPrivateListener(t *testing.T) {
	for _, address := range []string{"127.0.0.1:8090", "127.0.0.2:9090", "[::1]:8090"} {
		if err := validatePrivateListener(address, ""); err != nil {
			t.Errorf("loopback listener rejected: %s: %v", address, err)
		}
	}
	for _, address := range []string{"0.0.0.0:8090", ":8090", "[::]:8090", "192.168.1.2:8090", "localhost:8090", "invalid"} {
		if err := validatePrivateListener(address, ""); err == nil {
			t.Errorf("non-loopback or ambiguous listener accepted: %s", address)
		}
	}
	if err := validatePrivateListener("127.0.0.1:8090", "127.0.0.1:443"); err == nil {
		t.Fatal("direct HTTPS must be rejected; it can start another HTTP listener")
	}
}
