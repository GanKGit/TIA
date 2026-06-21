from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

import psutil


def terminate_process_tree(pid: int, timeout_seconds: float = 5.0) -> list[int]:
    """Terminate a process and all descendants, killing any stragglers."""
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return []

    descendants = root.children(recursive=True)
    processes = descendants + [root]
    terminated_pids = [process.pid for process in processes]

    for process in descendants:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    try:
        root.terminate()
    except psutil.NoSuchProcess:
        pass

    _, alive = psutil.wait_procs(processes, timeout=timeout_seconds)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    if alive:
        psutil.wait_procs(alive, timeout=timeout_seconds)
    return terminated_pids


def find_service_process_roots(
    ports: Iterable[int],
    module_name: str,
    project_root: Path,
) -> list[int]:
    """Find matching TIA service roots listening on the supplied ports."""
    expected_ports = {int(port) for port in ports}
    root_pids: set[int] = set()

    for connection in psutil.net_connections(kind="tcp"):
        if (
            connection.status != psutil.CONN_LISTEN
            or connection.pid is None
            or not connection.laddr
            or connection.laddr.port not in expected_ports
        ):
            continue
        try:
            process = psutil.Process(connection.pid)
            if not _process_matches_service(process, module_name, project_root):
                continue
            process = _matching_service_root(process, module_name, project_root)
            root_pids.add(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return sorted(root_pids)


def _matching_service_root(process: psutil.Process, module_name: str, project_root: Path) -> psutil.Process:
    current = process
    while True:
        try:
            parent = current.parent()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break
        if parent is None or not _process_matches_service(parent, module_name, project_root):
            break
        current = parent
    return current


def _process_matches_service(process: psutil.Process, module_name: str, project_root: Path) -> bool:
    try:
        command_line = " ".join(process.cmdline()).casefold()
        working_directory = os.path.normcase(os.path.abspath(process.cwd()))
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False
    expected_directory = os.path.normcase(os.path.abspath(project_root))
    return module_name.casefold() in command_line and working_directory == expected_directory
