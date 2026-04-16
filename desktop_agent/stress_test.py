"""
Resilo AI Demo — Stress Test
Spikes CPU + Memory to trigger the AI agent pipeline.

Usage:
    python stress_test.py --cpu        # burn CPU for 60s
    python stress_test.py --mem        # allocate 800MB for 60s
    python stress_test.py --both       # cpu + memory together
    python stress_test.py --duration 30 --both
"""
from __future__ import annotations
import argparse
import multiprocessing
import sys
import time
import threading


def _cpu_worker(stop_event: multiprocessing.Event) -> None:
    """Burn 100% of one CPU core until stop_event is set."""
    while not stop_event.is_set():
        pass  # pure busy-loop


def spike_cpu(duration: int) -> None:
    cores = multiprocessing.cpu_count()
    stop  = multiprocessing.Event()
    procs = [multiprocessing.Process(target=_cpu_worker, args=(stop,))
             for _ in range(cores)]
    print(f"[stress] Burning {cores} CPU cores for {duration}s…")
    for p in procs:
        p.start()
    time.sleep(duration)
    stop.set()
    for p in procs:
        p.join()
    print("[stress] CPU stress done.")


def spike_memory(duration: int) -> None:
    mb = 800
    print(f"[stress] Allocating {mb} MB for {duration}s…")
    blob = bytearray(mb * 1024 * 1024)       # allocate
    _ = blob[::4096]                          # touch pages so OS actually commits
    time.sleep(duration)
    del blob
    print("[stress] Memory released.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cpu",      action="store_true")
    p.add_argument("--mem",      action="store_true")
    p.add_argument("--both",     action="store_true")
    p.add_argument("--duration", type=int, default=60)
    args = p.parse_args()

    if not (args.cpu or args.mem or args.both):
        p.print_help()
        sys.exit(1)

    duration = args.duration
    threads  = []

    if args.both or args.mem:
        t = threading.Thread(target=spike_memory, args=(duration,), daemon=True)
        t.start()
        threads.append(t)

    if args.both or args.cpu:
        # run CPU spike in main thread (blocks until done)
        spike_cpu(duration)
    else:
        for t in threads:
            t.join()


if __name__ == "__main__":
    main()
