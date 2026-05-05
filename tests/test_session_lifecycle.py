from __future__ import annotations

from unittest.mock import patch

from azure.quantum.target.pasqal import PasqalTarget
from pulser import QPUBackend


def test_run_without_open_batch_closes_session(sequence, wired_connection):
    """Plain RemoteBackend.run() must not leak Azure sessions."""
    backend = QPUBackend(sequence=sequence, connection=wired_connection)

    with patch("pulser_azure.connection.Session") as session_cls:
        session_cls.return_value.id = "session-classic"
        backend.run(job_params=[{"runs": 5}], wait=False)

    wired_connection._workspace.open_session.assert_called_once()
    wired_connection._workspace.close_session.assert_called_once()


def test_run_with_open_batch_keeps_session_open_until_exit(
    sequence, wired_connection, fake_pasqal_targets
):
    """Inside an open_batch, run() must reuse the session and NOT close it.

    The session must only be closed by the context manager's __exit__.
    """
    backend = QPUBackend(sequence=sequence, connection=wired_connection)

    with patch("pulser_azure.connection.Session") as session_cls:
        session_cls.return_value.id = "session-cm"

        with backend.open_batch():
            assert wired_connection._workspace.open_session.call_count == 1
            assert wired_connection._workspace.close_session.call_count == 0

            backend.run(job_params=[{"runs": 5}], wait=False)

            assert wired_connection._workspace.open_session.call_count == 1
            assert wired_connection._workspace.close_session.call_count == 0

            backend.run(job_params=[{"runs": 3}], wait=False)
            assert wired_connection._workspace.open_session.call_count == 1
            assert wired_connection._workspace.close_session.call_count == 0

    assert wired_connection._workspace.close_session.call_count == 1
    fresnel = fake_pasqal_targets[PasqalTarget.QPU_FRESNEL]
    assert fresnel.submit.call_count == 2
