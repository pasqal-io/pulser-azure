# Azure quantum provider for Pulser

Azure quantum provider implementation to use neutral atoms based quantum computers.

**Pulser Azure** is a Python package to run quantum sequence on [Azure Quantum](https://azure.microsoft.com/en-us/solutions/quantum-computing/) infrastructure, providing access to [Pasqal](https://www.pasqal.com/) neutral atom quantum computers.

## Installation

```bash
pip install pulser-azure
```

## Getting started

To instantiate the `AzureConnection`, you need to provide a resource_id

```python
from pulser_azure import AzureConnection

connection = AzureConnection(
    resource_id="/subscriptions/<your-subscription-id>/resourceGroups/<your-resource-group-name>/providers/Microsoft.Quantum/Workspaces/<your-workspace-name>",
)
```

Alternatively, the `AzureConnection` can discover your resource from environment variables:

```
export PULSER_AZURE_RESOURCE_ID="/subscriptions/<your-subscription-id>/resourceGroups/<your-resource-group-name>/providers/Microsoft.Quantum/Workspaces/<your-workspace-name>"
```

Then you can instantiate the provider without any arguments:

```python
from pulser_azure import AzureConnection

connection = AzureConnection()
```

Now you have access to the supported backends and can design your pulse sequence. [See the technical documentation](https://docs.pasqal.com/pulser/sequence/) on how to write a sequence.


```python
from pulser_azure import AzureConnection
from pulser.pulse import Pulse
from pulser import QPUBackend, Sequence, Register

connection = AzureConnection()

# Retrieve all QPU devices
devices = connection.fetch_available_devices()
device = devices["pasqal.qpu.fresnel-can1"]

# Create a register of trapped atoms before performing operation on them
register = Register.square(5, 5).with_automatic_layout(device)

# Declare the sequence of pulses to perform on the register
sequence = Sequence(register, device)
sequence.declare_channel("rydberg", "rydberg_global")
omega_max = sequence.declare_variable("omega_max")

# Add a pulse to that channel with the amplitude omega_max
generic_pulse = Pulse.ConstantPulse(100, omega_max, 2, 0.0)
sequence.add(generic_pulse, "rydberg")

# Declare a backend based on the sequence and remote connection
backend = QPUBackend(sequence=sequence, connection=connection)

# Run jobs with different arguments over the same sequence and register
results = backend.run(
    job_params=[
        {"runs": 5, "variables": {"omega_max": 12}},
        {"runs": 10, "variables": {"omega_max": 6}},
    ],
    wait=True,
)
```

### Development install

If you wish to **install the development version of Pulser from source** instead, do the following from within this repository after cloning it:

```bash
uv sync
```

## License
[License Apache 2.0](LICENSE)

