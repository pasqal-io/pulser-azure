from __future__ import annotations

from unittest.mock import MagicMock, patch

from pulser import QPUBackend

from tests.conftest import _DEFAULT_QPU_TARGET


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
    fresnel = fake_pasqal_targets[_DEFAULT_QPU_TARGET]
    assert fresnel.submit.call_count == 2


def test_open_batch_run_reattaches_session_to_fresh_target(sequence, wired_connection):
    """Every run() inside open_batch must re-attach the session to the target.

    open_batch() creates the session on one target object, but each run()
    call fetches a *fresh* target via get_targets() — just like the real
    Azure SDK. Without re-attaching the session, target.submit() creates
    jobs outside the session, causing RemoteResults to raise:
        RuntimeError: Batch '...' does not contain jobs ['...']

    This already fails on the very first run() after open_batch().
    """
    # Jobs that were submitted *inside* the session (latest_session was set)
    session_jobs: list[str] = []
    job_counter = iter(range(100))

    def _make_fresh_target():
        """Mimics the real Azure SDK: get_targets() returns a new object
        with no latest_session attached."""
        target = MagicMock()
        target.name = _DEFAULT_QPU_TARGET
        target.provider_id = "pasqal"
        target.latest_session = None  # no session attached

        def _submit(**kwargs):
            job_id = f"job-{next(job_counter)}"
            # Only register the job in the session if it was re-attached
            if target.latest_session is not None:
                session_jobs.append(job_id)
            return MagicMock(id=job_id)

        target.submit.side_effect = _submit
        return target

    wired_connection._workspace.get_targets.side_effect = (
        lambda name, provider_id=None: _make_fresh_target()
    )

    # _get_job_ids mirrors what Azure would return: only jobs in the session
    wired_connection._get_job_ids = MagicMock(
        side_effect=lambda batch_id: list(session_jobs)
    )

    backend = QPUBackend(sequence=sequence, connection=wired_connection)

    with patch("pulser_azure.connection.Session") as session_cls:
        session_cls.return_value.id = "session-reattach"

        with backend.open_batch():
            # First run — must re-attach the session; without it the job
            # would be created outside the session and RemoteResults would
            # raise RuntimeError
            backend.run(job_params=[{"runs": 1}], wait=False)
            backend.run(job_params=[{"runs": 1}], wait=False)

    # Both jobs ended up inside the session
    assert len(session_jobs) == 2
