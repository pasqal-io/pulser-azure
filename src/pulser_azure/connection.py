# Copyright 2026 Pasqal Cloud Services development team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import os
import typing
from typing import Any, Mapping

import numpy as np
import urllib3
from azure.identity import DefaultAzureCredential
from azure.quantum import JobStatus as AzureJobStatus
from azure.quantum import SessionStatus
from azure.quantum.job import Job
from azure.quantum.job.session import Session
from azure.quantum.target.pasqal import Pasqal, PasqalTarget
from azure.quantum.workspace import Workspace
from pulser import Sequence
from pulser.backend.remote import (
    BatchStatus,
    JobParams,
    JobStatus,
    RemoteConnection,
    RemoteResults,
    RemoteResultsError,
)
from pulser.backend.results import Results
from pulser.channels import Rydberg, RydbergBeam, RydbergEOM
from pulser.devices import Device
from pulser.json.utils import make_json_compatible
from pulser.register import TriangularLatticeLayout
from pulser.result import SampledResult

_UNSET: Any = object()

_PASQAL_PROVIDER_ID = "pasqal"
_PASQAL_CLOUD_BASE_URL = os.getenv(
    "PASQAL_CLOUD_BASE_URL", "https://apis.pasqal.cloud/core-fast"
)

logger = logging.getLogger(__name__)

_AZURE_JOB_STATUS_MAP: dict[AzureJobStatus, JobStatus] = {
    AzureJobStatus.QUEUED: JobStatus.PENDING,
    AzureJobStatus.WAITING: JobStatus.PENDING,
    AzureJobStatus.EXECUTING: JobStatus.RUNNING,
    AzureJobStatus.SUCCEEDED: JobStatus.DONE,
    AzureJobStatus.COMPLETED: JobStatus.DONE,
    AzureJobStatus.FINISHING: JobStatus.RUNNING,
    AzureJobStatus.FAILED: JobStatus.ERROR,
    AzureJobStatus.CANCELLED: JobStatus.CANCELED,
    AzureJobStatus.CANCELLING: JobStatus.CANCELED,
    AzureJobStatus.CANCELLATION_REQUESTED: JobStatus.CANCELED,
}

_AZURE_SESSION_STATUS_MAP: dict[SessionStatus, BatchStatus] = {
    SessionStatus.WAITING: BatchStatus.PENDING,
    SessionStatus.EXECUTING: BatchStatus.RUNNING,
    SessionStatus.SUCCEEDED: BatchStatus.DONE,
    SessionStatus.FAILED: BatchStatus.ERROR,
    SessionStatus.FAILURE_S_: BatchStatus.ERROR,
    SessionStatus.TIMED_OUT: BatchStatus.TIMED_OUT,
}


class AzureConnection(RemoteConnection):
    """Azure Quantum connection bridge.

    :param resource_id: option resource ID of the Azure workspace, if the provided `resource_id` is None, the value is loaded from the `PULSER_AZURE_RESOURCE_ID` environment variable
    """

    def __init__(self, resource_id: str | None = None):
        credential = DefaultAzureCredential(
            exclude_interactive_browser_credential=False
        )
        self._workspace = Workspace(
            resource_id=resource_id or os.getenv("PULSER_AZURE_RESOURCE_ID"),
            credential=credential,
        )
        self._device_name_target_map: dict[str, tuple[Device, Pasqal]] = {}

    def submit(
        self,
        sequence: Sequence,
        wait: bool = False,
        open: bool = _UNSET,
        batch_id: str | None = None,
        **kwargs: Any,
    ) -> RemoteResults:
        """Submit a job for execution."""
        open_explicit = open is not _UNSET
        open = True if open is _UNSET else open

        target = self._device_name_target_map[sequence.device.name][1]
        job_params = make_json_compatible(kwargs.get("job_params", []))

        # Context manager use case (eg: with backend.open_batch()), even
        # if connection had a session, create a new one as we're supposed to
        # be in another context now.
        if open_explicit is True and open:
            batch_id = self._setup_session(target)

            return RemoteResults(batch_id=batch_id, connection=self)

        # Present when running backend.run() inside context manager
        if batch_id:
            job_ids = self._submit_jobs(
                target=target,
                sequence=sequence,
                job_params=job_params,
            )
        # Classic backend.run() call
        else:
            batch_id = self._setup_session(target)

            job_ids = self._submit_jobs(
                target=target,
                sequence=sequence,
                job_params=job_params,
            )

        if wait:
            for job_id in job_ids:
                job = self._workspace.get_job(job_id)
                job.wait_until_completed()

        if not open:
            self._close_batch(batch_id)

        return RemoteResults(batch_id=batch_id, connection=self, job_ids=job_ids)

    def _setup_session(self, target: Pasqal) -> str:
        session = Session(
            workspace=self._workspace,
            target=target.name,
            provider_id=target.provider_id,
        )
        self._workspace.open_session(session)
        target.latest_session = session

        return session.id

    def _submit_jobs(
        self,
        target: Pasqal,
        sequence: Sequence,
        job_params: list[JobParams],
    ) -> list[str]:
        sequence = self._add_measurement_to_sequence(sequence)

        if sequence.is_parametrized() or sequence.is_register_mappable():
            for params in job_params:
                vars = params.get("variables", {})
                sequence.build(**vars)

        input_data = {"sequence_builder": sequence.to_abstract_repr()}
        job_ids: list[str] = []

        if job_params:
            for params in job_params:
                job = target.submit(input_data=input_data, input_params=params)
                job_ids.append(job.id)
        else:
            job = target.submit(input_data=input_data)
            job_ids.append(job.id)

        return job_ids

    def _fetch_result(
        self, batch_id: str, job_ids: list[str] | None
    ) -> typing.Sequence[Results]:
        """Fetches the results of a completed batch."""
        jobs = self._query_job_progress(batch_id)

        if job_ids is None:
            job_ids = list(jobs.keys())

        results: list[Results] = []
        for id in job_ids:
            status, result = jobs[id]
            if status in [JobStatus.PENDING, JobStatus.RUNNING]:
                raise RemoteResultsError(
                    f"The results are not yet available, job {id} status is {status}."
                )

            if result is None:
                raise RemoteResultsError(f"No results found for job {id}.")

            results.append(result)

        return results

    def _query_job_progress(
        self, batch_id: str
    ) -> Mapping[str, tuple[JobStatus, Results | None]]:
        """Fetches the status and results of all the jobs in a batch.

        Unlike `_fetch_result`, this method does not raise an error if some
        jobs in the batch do not have results.

        It returns a dictionary mapping the job ID to its status and results.
        """
        jobs = self._workspace.list_session_jobs(session_id=batch_id)

        progress: dict[str, tuple[JobStatus, Results | None]] = {}

        for job in jobs:
            job.refresh()

            status = _AZURE_JOB_STATUS_MAP.get(job.details.status, JobStatus.ERROR)

            result: Results | None = None
            if status == JobStatus.DONE:
                try:
                    raw_results = job.get_results()
                    result = self._parse_job_result(raw_results, job)
                except Exception:
                    logger.warning(
                        "Failed to parse results for job %s",
                        job.id,
                        exc_info=True,
                    )

            progress[job.id] = (status, result)

        return progress

    def _parse_job_result(
        self,
        raw_results: Any,
        job: Job,
    ) -> SampledResult:
        input_data_uri = job.details.input_data_uri
        input_payload = job.download_data(input_data_uri)

        try:
            input_json = json.loads(input_payload.decode("utf8"))
            sequence = Sequence.from_abstract_repr(input_json["sequence_builder"])
        except Exception:
            pass

        if sequence is None:
            raise ValueError(f"Cannot reconstruct sequence for job {job.id}")

        reg = sequence.get_register(include_mappable=True)
        meas_basis = sequence.get_measurement_basis()
        all_qubit_ids = reg.qubit_ids

        counter = raw_results.get("counter", raw_results)
        if not isinstance(counter, dict):
            counter = raw_results

        size = None
        vars = job.details.input_params.get("variables")

        if vars and "qubits" in vars:
            size = len(vars["qubits"])

        return SampledResult(
            atom_order=all_qubit_ids[slice(size)],
            meas_basis=meas_basis,
            bitstring_counts=counter,
        )

    def _get_batch_status(self, batch_id: str) -> BatchStatus:
        """Gets the status of a batch from its ID."""
        session = self._workspace.get_session(session_id=batch_id)
        return _AZURE_SESSION_STATUS_MAP.get(session.details.status, BatchStatus.ERROR)

    def _get_job_ids(self, batch_id: str) -> list[str]:
        """Gets all the job IDs within a batch."""
        jobs = self._workspace.list_session_jobs(session_id=batch_id)
        return [job.id for job in jobs]

    def fetch_available_devices(self) -> dict[str, Device]:
        """Fetches the devices available through this connection."""

        # Use the cached map to avoid calling retrieving devices again for
        # nothing when update_sequence_device is called
        if self._device_name_target_map:
            return {k: v[0] for k, v in self._device_name_target_map.items()}

        targets = [
            t for t in self._workspace.get_targets(provider_id=_PASQAL_PROVIDER_ID)
        ]
        device_specs = self._get_device_specs()

        def _target_to_device(target: Pasqal) -> Device:
            target_enum = PasqalTarget(target.name)

            if target_enum.value in PasqalTarget.simulators():
                return Device(
                    name=target_enum.name.removeprefix("SIM_"),
                    max_atom_num=PasqalTarget(target_enum).num_qubits(),
                    dimensions=2,
                    rydberg_level=60,
                    max_radial_distance=38,
                    min_atom_distance=5,
                    max_sequence_duration=6000,
                    max_runs=2000,
                    requires_layout=True,
                    accepts_new_layouts=True,
                    optimal_layout_filling=0.45,
                    channel_objects=(
                        Rydberg.Global(
                            max_abs_detuning=2 * np.pi * 20,
                            max_amp=2 * np.pi * 2,
                            clock_period=4,
                            min_duration=16,
                            mod_bandwidth=8,
                            eom_config=RydbergEOM(
                                limiting_beam=RydbergBeam.RED,
                                max_limiting_amp=30 * 2 * np.pi,
                                intermediate_detuning=450 * 2 * np.pi,
                                mod_bandwidth=40,
                                controlled_beams=(RydbergBeam.BLUE,),
                                custom_buffer_time=240,
                            ),
                        ),
                    ),
                    pre_calibrated_layouts=(TriangularLatticeLayout(61, 5),),
                    short_description="A realistic device for analog sequence execution.",
                )
            else:
                device_spec = next(
                    spec
                    for spec in device_specs
                    if spec["device_type"] == target_enum.name.removeprefix("QPU_")
                )

                return Device.from_abstract_repr(device_spec["specs"])

        devices = []

        for target in targets:
            try:
                device = _target_to_device(target)
            except StopIteration:
                logger.warning("Could not build a device for target: %s", target)
                continue

            self._device_name_target_map[device.name] = (device, target)
            devices.append(device)

        return {device.name: device for device in devices}

    def _get_device_specs(self) -> dict:
        response = urllib3.request(
            "GET",
            f"{_PASQAL_CLOUD_BASE_URL}/api/v1/devices/public-specs",
            timeout=5,
            retries=urllib3.Retry(10, backoff_factor=0.5),
        )

        return response.json()["data"]

    def _close_batch(self, batch_id: str) -> None:
        """Closes a batch using its ID."""
        session = self._workspace.get_session(session_id=batch_id)

        self._workspace.close_session(session)

    def supports_open_batch(self) -> bool:
        """Flag to confirm this class can support creating an open batch."""
        return True
