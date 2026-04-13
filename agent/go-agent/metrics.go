package main

import (
	"runtime"

	"github.com/shirou/gopsutil/v3/cpu"
	"github.com/shirou/gopsutil/v3/disk"
	"github.com/shirou/gopsutil/v3/host"
	"github.com/shirou/gopsutil/v3/mem"
	gopsnet "github.com/shirou/gopsutil/v3/net"
	"github.com/shirou/gopsutil/v3/process"
)

type Metrics struct {
	CPU      float64
	Memory   float64
	Disk     float64
	NetSent  uint64
	NetRecv  uint64
	Uptime   uint64
	Processes int
}

func diskRoot() string {
	if runtime.GOOS == "windows" {
		return "C:\\"
	}
	return "/"
}

func CollectMetrics() (Metrics, error) {
	cpuPcts, err := cpu.Percent(0, false)
	if err != nil {
		return Metrics{}, err
	}
	vmStat, err := mem.VirtualMemory()
	if err != nil {
		return Metrics{}, err
	}
	diskStat, err := disk.Usage(diskRoot())
	if err != nil {
		return Metrics{}, err
	}
	netStats, err := gopsnet.IOCounters(false)
	if err != nil {
		return Metrics{}, err
	}
	uptime, err := host.Uptime()
	if err != nil {
		return Metrics{}, err
	}
	procs, _ := process.Pids()

	var netSent, netRecv uint64
	if len(netStats) > 0 {
		netSent = netStats[0].BytesSent
		netRecv = netStats[0].BytesRecv
	}

	return Metrics{
		CPU:      cpuPcts[0],
		Memory:   vmStat.UsedPercent,
		Disk:     diskStat.UsedPercent,
		NetSent:  netSent,
		NetRecv:  netRecv,
		Uptime:   uptime,
		Processes: len(procs),
	}, nil
}
