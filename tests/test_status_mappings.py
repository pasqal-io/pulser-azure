from azure.quantum import JobStatus as AzureJobStatus
from azure.quantum import SessionStatus

from pulser_azure.connection import (
    _AZURE_JOB_STATUS_MAP,
    _AZURE_SESSION_STATUS_MAP,
)


def test_every_azure_job_status_is_mapped():
    for status in AzureJobStatus:
        assert status in _AZURE_JOB_STATUS_MAP, (
            f"Azure {status} has no pulser JobStatus mapping"
        )


def test_every_azure_session_status_is_mapped():
    for status in SessionStatus:
        assert status in _AZURE_SESSION_STATUS_MAP, (
            f"Azure {status} has no pulser BatchStatus mapping"
        )
