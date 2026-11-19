import pytest

from app.config.settings import ConfigError, load_settings


def test_defaults() -> None:
    p = load_settings(_env_file=None).pipeline
    assert (p.eligibility_threshold, p.ats_target, p.max_passes, p.judge_enabled) == (
        30,
        90,
        2,
        True,
    )


def test_threshold_above_100_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE__ELIGIBILITY_THRESHOLD", "101")
    with pytest.raises(ConfigError, match="pipeline.eligibility_threshold"):
        load_settings(_env_file=None)


def test_max_passes_above_3_rejected() -> None:
    with pytest.raises(ConfigError, match="pipeline.max_passes"):
        load_settings(_env_file=None, pipeline={"max_passes": 4})
