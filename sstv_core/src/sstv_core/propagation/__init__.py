"""Is the band open? An axis that cannot fail the way our receiver does.

Kept out of the decode path on purpose. Space weather is the one control
that does not share a failure mode with our own receive chain, which is the
entire reason it is trustworthy when a capture reads dead.
"""

from sstv_core.propagation.space_weather import (
    PropagationReport,
    SpaceWeatherUnavailableError,
    fetch_report,
)

__all__ = ["PropagationReport", "SpaceWeatherUnavailableError", "fetch_report"]
