class Policy:
    """A policy to coordinate different LOERIC instances in a session.

    It collects values obtained by every LOERIC through ``set``
    and calculates an updated value using ``update``,
    which can be obtained through ``get``.
    """

    def __init__(self):
        self._inputs = {}

    def set(self, values: dict):
        """Set input values for the policy."""
        self._inputs |= values

    def _compute(self):
        """Compute new outputs from the inputs.

        Default implementation is an identity function.
        """
        return self._inputs

    def update(self):
        """Update the policy's output by processing the input.

        The processing function can be defined
        by overriding ``_compute()``.
        """
        self._outputs = self._compute()

    def get(self) -> dict:
        """Get the policy's output values."""
        return self._outputs
