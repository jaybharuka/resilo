package main

import "os"

type Config struct {
	AgentToken string
	BackendURL string
}

func LoadConfig() Config {
	backendURL := os.Getenv("BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://localhost:8000"
	}
	return Config{
		AgentToken: os.Getenv("AGENT_TOKEN"),
		BackendURL: backendURL,
	}
}
