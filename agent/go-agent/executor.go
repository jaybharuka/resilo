package main

import (
	"fmt"
	"os"
	"os/exec"
	"runtime"
)

var allowedActions = map[string]bool{
	"restart_service": true,
	"run_script":      true,
	"notify_only":     true,
}

type Command struct {
	Action string `json:"action"`
	Target string `json:"target"`
}

func ExecuteCommand(cmd Command) error {
	if !allowedActions[cmd.Action] {
		return fmt.Errorf("action '%s' not in allowlist", cmd.Action)
	}

	dryRun := os.Getenv("DRY_RUN") != "false"
	fmt.Printf("[EXEC] action=%s target=%s\n", cmd.Action, cmd.Target)

	if dryRun {
		fmt.Printf("[DRY RUN] Skipping execution of %s on %s\n", cmd.Action, cmd.Target)
		return nil
	}

	switch cmd.Action {
	case "restart_service":
		return restartService(cmd.Target)
	case "run_script":
		return runScript(cmd.Target)
	case "notify_only":
		fmt.Printf("[NOTIFY] %s\n", cmd.Target)
		return nil
	default:
		return fmt.Errorf("unhandled action: %s", cmd.Action)
	}
}

func restartService(name string) error {
	var c *exec.Cmd
	if runtime.GOOS == "windows" {
		script := fmt.Sprintf("net stop %s; net start %s", name, name)
		c = exec.Command("powershell", "-Command", script)
	} else {
		c = exec.Command("systemctl", "restart", name)
	}
	out, err := c.CombinedOutput()
	if err != nil {
		return fmt.Errorf("restart_service %s failed: %w — %s", name, err, string(out))
	}
	fmt.Printf("[EXEC] restart_service %s OK\n", name)
	return nil
}

func runScript(script string) error {
	var c *exec.Cmd
	if runtime.GOOS == "windows" {
		c = exec.Command("powershell", "-Command", script)
	} else {
		c = exec.Command("sh", "-c", script)
	}
	out, err := c.CombinedOutput()
	if len(out) > 0 {
		fmt.Printf("[EXEC] output: %s\n", string(out))
	}
	if err != nil {
		return fmt.Errorf("run_script failed: %w", err)
	}
	return nil
}
