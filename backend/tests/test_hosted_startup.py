"""Startup clock boundaries, not a model inference performance benchmark."""
import importlib.util
from pathlib import Path
import signal
from types import SimpleNamespace

import pytest


@pytest.fixture
def launcher(monkeypatch):
    path = Path(__file__).resolve().parents[2] / 'scripts' / 'serve_demo.py'
    spec = importlib.util.spec_from_file_location('hosted_startup_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = SimpleNamespace(now=0., ready_at=35., crash_at=None, children=[], handlers={},
                            probe_delay=0., stop_at=None, timeouts=[])

    class Child:
        def __init__(self, *args, **kwargs):
            self.terminated = False
            self.index = len(state.children)
            state.children.append(self)

        def poll(self):
            if self.terminated:
                return -15
            if self.index == 0 and state.crash_at is not None and state.now >= state.crash_at:
                return 7
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout):
            return self.poll()

    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass

    def open_health(_url, timeout):
        state.timeouts.append(timeout)
        state.now += min(timeout, state.probe_delay)
        if state.stop_at is not None and state.now >= state.stop_at:
            state.handlers[signal.SIGTERM](signal.SIGTERM, None)
        if state.now < state.ready_at:
            raise ConnectionRefusedError()
        return Response()

    def sleep(seconds):
        state.now += seconds
        if len(state.children) == 2:
            state.handlers[signal.SIGTERM](signal.SIGTERM, None)

    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: state.now, sleep=sleep))
    monkeypatch.setattr(module.subprocess, 'Popen', Child)
    monkeypatch.setattr(module.signal, 'signal', lambda sig, handler: state.handlers.__setitem__(sig, handler))
    monkeypatch.setattr(module.urllib.request, 'build_opener', lambda *_: SimpleNamespace(open=open_health))
    monkeypatch.delenv('RENDER', raising=False)
    return module, state


def test_slow_healthy_model_is_not_killed_at_old_thirty_second_boundary(launcher):
    module, state = launcher
    assert module.main() == 0
    assert len(state.children) == 2
    assert all(child.terminated for child in state.children)
    assert 35 <= state.now < 36


def test_never_ready_model_has_bounded_startup_and_does_not_start_api(launcher, capsys):
    module, state = launcher
    state.ready_at = float('inf')
    assert module.main() == 1
    assert len(state.children) == 1
    assert state.children[0].terminated
    assert 89 <= state.now <= 90
    assert 'model_startup_timeout' in capsys.readouterr().err


def test_crashed_model_exits_promptly_instead_of_spending_startup_budget(launcher, capsys):
    module, state = launcher
    state.crash_at = 2
    assert module.main() == 1
    assert len(state.children) == 1
    assert state.now <= 2.25
    assert 'model_process_exited' in capsys.readouterr().err


def test_slow_health_probes_share_one_startup_deadline(launcher):
    module, state = launcher
    state.ready_at = float('inf')
    state.probe_delay = 1
    assert module.main() == 1
    assert state.now == 90
    assert len(state.timeouts) < 120
    assert all(0 < timeout <= 1 for timeout in state.timeouts)
    assert state.children[0].terminated


def test_shutdown_during_initialization_stops_child_without_starting_api(launcher):
    module, state = launcher
    state.stop_at = 5
    assert module.main() == 0
    assert len(state.children) == 1
    assert state.children[0].terminated
    assert state.now <= 5.25
