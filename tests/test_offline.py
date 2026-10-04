"""LUAR must work offline once installed: no outside connection from the page or the model."""
import re
import socket

import pytest

from .conftest import EXAMPLES

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture
def no_network(monkeypatch):
    """Fail any connection to a host other than this machine."""
    real_connect = socket.socket.connect

    def guarded(self, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOCAL_HOSTS:
            raise AssertionError(f"LUAR tried to reach {address!r} while offline")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded)
    monkeypatch.setattr(socket, "create_connection", lambda address, *a, **k: guarded(None, address))


def test_readme_screenshots_are_served_locally():
    app = pytest.importorskip("luar.app")
    for path in app.READMES.values():
        if not path.exists():
            continue
        images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", app.readme_markdown(path))
        assert len(images) == 4
        assert all(src.startswith("/gradio_api/file=") for src in images)


def test_interface_sends_no_telemetry():
    app = pytest.importorskip("luar.app")
    assert app.build().analytics_enabled is False


@pytest.mark.slow
def test_laya_runs_offline_once_downloaded(no_network):
    """Needs the models in the local cache (`luar download`)."""
    from luar.backends.laya_backend import LayaBackend, local_checkpoint
    from luar.questions import load_questions

    if local_checkpoint("convaiinnovations/laya", "multilingual") is None:
        pytest.skip("multilingual model not downloaded")
    questions = load_questions(EXAMPLES / "avaliacoes_perguntas.json")
    answers = LayaBackend("multilingual").decide(["O pacote chegou atrasado."], questions)
    # the point is that it answered with the network blocked, not what it answered
    assert answers[0]["quer_reembolso"].value in ("yes", "no")
    assert answers[0]["assunto"].confidence is not None
