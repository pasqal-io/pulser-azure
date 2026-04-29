from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from pulser import Sequence
from pulser.result import SampledResult


def _build_job_mock(seq: Sequence, input_params: dict | None = None) -> MagicMock:
    payload = {"sequence_builder": seq.to_abstract_repr()}
    job = MagicMock()
    job.id = "job-1"
    job.details.input_data_uri = "https://blob.example/input"
    job.details.input_params = input_params or {}
    job.download_data.return_value = json.dumps(payload).encode("utf-8")
    return job


def test_parses_counter_dict_into_sampled_result(connection, sequence):
    sequence.measure("ground-rydberg")
    job = _build_job_mock(sequence)

    raw = {"counter": {"0000": 7, "1111": 3}}
    result = connection._parse_job_result(raw, job)

    assert isinstance(result, SampledResult)
    assert result.bitstring_counts == {"0000": 7, "1111": 3}
    assert result.meas_basis == "ground-rydberg"
    assert result.atom_order == ("q0", "q1", "q2", "q3")


def test_parses_raw_counts_when_no_counter_key(connection, sequence):
    sequence.measure("ground-rydberg")
    job = _build_job_mock(sequence)

    raw = {"0000": 5, "1010": 5}
    result = connection._parse_job_result(raw, job)

    assert result.bitstring_counts == {"0000": 5, "1010": 5}


def test_truncates_atom_order_to_qubit_count_variable(connection, sequence):
    sequence.measure("ground-rydberg")
    job = _build_job_mock(
        sequence, input_params={"variables": {"qubits": ["q0", "q1"]}}
    )

    raw = {"counter": {"00": 10}}
    result = connection._parse_job_result(raw, job)

    assert result.atom_order == ("q0", "q1")


def test_raises_when_input_payload_unparseable(connection):
    job = MagicMock()
    job.id = "job-2"
    job.details.input_data_uri = "https://blob.example/bad"
    job.download_data.return_value = b"not-json"

    with pytest.raises(ValueError, match="job-2"):
        connection._parse_job_result({"counter": {}}, job)
