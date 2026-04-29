from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from azure.quantum.target.pasqal import PasqalTarget
from pulser import QPUBackend

from pulser_azure import RemoteEmuMPSBackend


@pytest.fixture
def fake_pasqal_targets():
    targets = {}
    for pt in PasqalTarget:
        m = MagicMock()
        m.name = pt.value
        m.provider_id = "pasqal"
        m.submit.return_value = MagicMock(id=f"job-{pt.name}")
        targets[pt] = m
    return targets


@pytest.fixture
def wired_connection(connection, fake_pasqal_targets):
    connection._target_name_target_map = dict(fake_pasqal_targets)
    connection._device_name_target_map = {"AnalogDevice": PasqalTarget.QPU_FRESNEL}
    connection._workspace.list_session_jobs.return_value = []
    connection.update_sequence_device = MagicMock(side_effect=lambda s: s)
    connection._get_job_ids = MagicMock(
        side_effect=lambda batch_id: [f"job-{pt.name}" for pt in PasqalTarget]
    )
    return connection


def test_emulator_backend_submits_to_emulator_target(
    sequence, wired_connection, fake_pasqal_targets
):
    backend = RemoteEmuMPSBackend(sequence=sequence, connection=wired_connection)

    with patch("pulser_azure.connection.Session") as session_cls:
        session_cls.return_value.id = "session-1"
        backend.run(job_params=[{"runs": 5}], wait=False)

    fake_pasqal_targets[PasqalTarget.SIM_EMU_MPS].submit.assert_called_once()
    fake_pasqal_targets[PasqalTarget.QPU_FRESNEL].submit.assert_not_called()


def test_qpu_backend_submits_to_target_matching_sequence_device(
    sequence, wired_connection, fake_pasqal_targets
):
    backend = QPUBackend(sequence=sequence, connection=wired_connection)

    with patch("pulser_azure.connection.Session") as session_cls:
        session_cls.return_value.id = "session-1"
        backend.run(job_params=[{"runs": 5}], wait=False)

    fake_pasqal_targets[PasqalTarget.QPU_FRESNEL].submit.assert_called_once()
    fake_pasqal_targets[PasqalTarget.SIM_EMU_MPS].submit.assert_not_called()


def test_unknown_workspace_target_raises(sequence, wired_connection):
    wired_connection._target_name_target_map.pop(PasqalTarget.QPU_FRESNEL)

    backend = QPUBackend(sequence=sequence, connection=wired_connection)

    with pytest.raises(RuntimeError, match="isn't available on your workspace"):
        backend.run(job_params=[{"runs": 5}], wait=False)
