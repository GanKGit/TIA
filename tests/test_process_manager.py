from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psutil

from app.services.process_manager import find_service_process_roots, terminate_process_tree


class FakeProcess:
    def __init__(self, pid: int, command: list[str], cwd: str, parent=None, children=None) -> None:
        self.pid = pid
        self._command = command
        self._cwd = cwd
        self._parent = parent
        self._children = children or []
        self.terminated = False

    def cmdline(self):
        return self._command

    def cwd(self):
        return self._cwd

    def parent(self):
        return self._parent

    def children(self, recursive=False):
        return self._children

    def terminate(self):
        self.terminated = True

    def kill(self):
        pass


class ProcessManagerTests(unittest.TestCase):
    def test_recovers_launcher_root_from_listening_child(self) -> None:
        project_root = Path(r"C:\project\TIA")
        launcher = FakeProcess(100, ["python.exe", "-m", "AlgoEngine.local_engine"], str(project_root))
        child = FakeProcess(200, ["python.exe", "-m", "AlgoEngine.local_engine"], str(project_root), parent=launcher)
        connection = SimpleNamespace(status=psutil.CONN_LISTEN, pid=200, laddr=SimpleNamespace(port=9500))

        with patch("app.services.process_manager.psutil.net_connections", return_value=[connection]), patch(
            "app.services.process_manager.psutil.Process", return_value=child
        ):
            self.assertEqual(
                find_service_process_roots((9500, 9501, 9502), "AlgoEngine.local_engine", project_root),
                [100],
            )

    def test_rejects_matching_module_from_another_project(self) -> None:
        project_root = Path(r"C:\project\TIA")
        process = FakeProcess(200, ["python.exe", "-m", "AlgoEngine.local_engine"], r"C:\other")
        connection = SimpleNamespace(status=psutil.CONN_LISTEN, pid=200, laddr=SimpleNamespace(port=9500))

        with patch("app.services.process_manager.psutil.net_connections", return_value=[connection]), patch(
            "app.services.process_manager.psutil.Process", return_value=process
        ):
            self.assertEqual(find_service_process_roots((9500,), "AlgoEngine.local_engine", project_root), [])

    def test_terminates_child_and_parent(self) -> None:
        child = FakeProcess(200, [], "")
        root = FakeProcess(100, [], "", children=[child])
        with patch("app.services.process_manager.psutil.Process", return_value=root), patch(
            "app.services.process_manager.psutil.wait_procs", return_value=([child, root], [])
        ):
            self.assertEqual(terminate_process_tree(100), [200, 100])
        self.assertTrue(child.terminated)
        self.assertTrue(root.terminated)


if __name__ == "__main__":
    unittest.main()
