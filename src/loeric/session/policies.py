# This file is part of LOERIC.
#
# LOERIC is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LOERIC is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LOERIC. If not, see <https://www.gnu.org/licenses/>.

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
