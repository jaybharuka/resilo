package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

type Payload struct {
	Token     string    `json:"token"`
	CPU       float64   `json:"cpu"`
	Memory    float64   `json:"memory"`
	Disk      float64   `json:"disk"`
	NetSent   uint64    `json:"net_sent"`
	NetRecv   uint64    `json:"net_recv"`
	Uptime    uint64    `json:"uptime"`
	Processes int       `json:"processes"`
	Timestamp time.Time `json:"timestamp"`
}

type CommandResponse struct {
	Commands []Command `json:"commands"`
}

func PollCommands(cfg Config) {
	url := fmt.Sprintf("%s/agent/command?token=%s", cfg.BackendURL, cfg.AgentToken)
	resp, err := http.Get(url)
	if err != nil {
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return
	}
	var cr CommandResponse
	if err := json.NewDecoder(resp.Body).Decode(&cr); err != nil {
		return
	}
	for _, cmd := range cr.Commands {
		if err := ExecuteCommand(cmd); err != nil {
			fmt.Printf("[error] exec: %v\n", err)
		}
	}
}

func SendMetrics(cfg Config, m Metrics) error {
	payload := Payload{
		Token:     cfg.AgentToken,
		CPU:       m.CPU,
		Memory:    m.Memory,
		Disk:      m.Disk,
		NetSent:   m.NetSent,
		NetRecv:   m.NetRecv,
		Uptime:    m.Uptime,
		Processes: m.Processes,
		Timestamp: time.Now().UTC(),
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	url := fmt.Sprintf("%s/agent/metrics", cfg.BackendURL)
	resp, err := http.Post(url, "application/json", bytes.NewBuffer(body))
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("backend returned HTTP %d", resp.StatusCode)
	}
	return nil
}
