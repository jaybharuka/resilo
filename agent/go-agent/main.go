package main

import (
	"fmt"
	"os"
	"time"
)

func main() {
	cfg := LoadConfig()
	fmt.Printf("Agent starting — backend=%s dry_run=%s\n", cfg.BackendURL, os.Getenv("DRY_RUN"))

	go func() {
		for {
			PollCommands(cfg)
			time.Sleep(5 * time.Second)
		}
	}()

	for {
		m, err := CollectMetrics()
		if err != nil {
			fmt.Printf("[error] collect: %v\n", err)
			time.Sleep(5 * time.Second)
			continue
		}
		fmt.Printf("CPU=%.1f%% MEM=%.1f%% DISK=%.1f%% NET=%d/%d UPTIME=%ds PROCS=%d\n",
			m.CPU, m.Memory, m.Disk, m.NetSent, m.NetRecv, m.Uptime, m.Processes)
		if err := SendMetrics(cfg, m); err != nil {
			fmt.Printf("[error] send: %v\n", err)
		}
		time.Sleep(5 * time.Second)
	}
}
