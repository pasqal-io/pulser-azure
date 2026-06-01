# Getting started

## Authenticating

To instantiate the [`AzureConnection`][pulser_azure.connection.AzureConnection],
you need to provide a `resource_id`:

```python
from pulser_azure import AzureConnection

connection = AzureConnection(
    resource_id="/subscriptions/<your-subscription-id>/resourceGroups/<your-resource-group-name>/providers/Microsoft.Quantum/Workspaces/<your-workspace-name>",
)
```

Alternatively, the `AzureConnection` can discover your resource from environment
variables:

```bash
export PULSER_AZURE_RESOURCE_ID="/subscriptions/<id>/resourceGroups/<rg>/providers/Microsoft.Quantum/Workspaces/<ws>"
```

Then you can instantiate the provider without any arguments:

```python
from pulser_azure import AzureConnection

connection = AzureConnection()
```

## Running a sequence on a QPU

See the [Pulser sequence documentation](https://docs.pasqal.com/pulser/sequence/)
for the full sequence-writing reference.

```python
--8<-- "examples/using_qpu.py"
```

## Running on emulators

Pulser Azure exposes several remote emulator backends:

- [`EmuSVBackend`][pulser_azure.EmuSVBackend] — state vector emulator
- [`EmuMPSBackend`][pulser_azure.EmuMPSBackend] — matrix product states emulator
- [`EmuFreeBackend`][pulser_azure.EmuFreeBackend] — free-tier emulator

Use them in place of `QPUBackend` to run the same sequences without consuming
real QPU time:

```python
--8<-- "examples/using_emulators.py"
```
