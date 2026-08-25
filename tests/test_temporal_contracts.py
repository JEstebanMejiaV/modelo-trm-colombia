from __future__ import annotations

import pytest

from model.config import FORECAST_FACTOR_SPECS_3, FORECAST_FACTOR_SPECS_4
from trm_model.data.fred import (
    FredConfigurationError,
    redact_fred_api_key,
    require_fred_api_key,
)
from trm_model.validation.leakage import LeakageError, validate_forecast_specs


def test_monthly_forecast_specs_have_no_contemporaneous_terms() -> None:
    assert validate_forecast_specs(FORECAST_FACTOR_SPECS_3)
    assert validate_forecast_specs(FORECAST_FACTOR_SPECS_4)


def test_temporal_validator_rejects_l0_terms() -> None:
    with pytest.raises(LeakageError):
        validate_forecast_specs(
            {"factor": {"terminos": [("D.variable", 0)]}}
        )


def test_fred_key_is_required_from_environment() -> None:
    with pytest.raises(FredConfigurationError, match="FRED_API_KEY"):
        require_fred_api_key({})
    assert require_fred_api_key({"FRED_API_KEY": "placeholder"}) == "placeholder"


def test_fred_error_redacts_api_key() -> None:
    secret = "placeholder-secret"
    message = redact_fred_api_key(
        f"HTTP Error for https://api.example.test/?api_key={secret}&series_id=VIXCLS",
        secret,
    )
    assert secret not in message
    assert "api_key=[REDACTED]" in message
