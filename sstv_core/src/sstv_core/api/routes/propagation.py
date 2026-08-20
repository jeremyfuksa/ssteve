"""Propagation endpoint.

Handles:
- GET /propagation - Should this band be carrying signal right now?

Deliberately independent of the receive chain. When a capture reads dead,
this is the one axis that cannot be wrong in the same direction as our own
gain, antenna or demodulator, which is what makes it worth asking first.
"""

from fastapi import APIRouter, HTTPException, Query, status

from sstv_core.api.models import PropagationResponse
from sstv_core.propagation import SpaceWeatherUnavailableError, fetch_report

router = APIRouter(prefix="/propagation", tags=["propagation"])


@router.get("", response_model=PropagationResponse)
async def get_propagation(
    band: str = Query(default="20m", description="Amateur band, e.g. 20m"),
) -> PropagationResponse:
    """Report whether `band` should be open, and what silence means if it is.

    A 503 here means the sources were unreachable -- not that conditions are
    fine. The caller must show that difference, because an empty propagation
    panel reads as good news and that is how a healthy receiver gets called
    broken.
    """
    try:
        report = fetch_report(band=band)
    except SpaceWeatherUnavailableError as exc:
        detail = {
            "error": "space_weather_unavailable",
            "message": str(exc),
            "suggested_action": (
                "Check the network. Until a source answers, treat silence as "
                "inconclusive rather than as a hardware fault."
            ),
        }
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from exc

    return PropagationResponse(
        band=report.band,
        band_group=report.band_group,
        time_of_day=report.time_of_day,
        condition=report.condition,
        state=report.state,
        explanation=report.explanation,
        solar_flux=report.solar_flux,
        k_index=report.k_index,
        a_index=report.a_index,
        sunspots=report.sunspots,
        xray=report.xray,
        updated=report.updated,
        source_errors=report.source_errors,
        wwv_frequencies_hz=report.wwv_frequencies_hz,
    )
