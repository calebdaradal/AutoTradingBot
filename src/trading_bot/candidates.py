"""Track B: the list of strategies that can be backtested.

  * v1.0 is the permanent failed baseline. It is registered here but can never be a candidate.
  * A new idea = a NEW class with a NEW version id (never edit an old one). Register it with @candidate.
  * Candidates are for backtests only. The paper bot always runs the frozen v1.0 settings.
"""
from .strategies import TrendMomentum

BASELINE_VERSION = "trend_momentum-1.0"
_REGISTRY = {}


def candidate(version):
    """Class decorator: make a strategy selectable with 'backtest --candidate <version>'."""
    def wrap(cls):
        if version == BASELINE_VERSION or version in _REGISTRY:
            raise ValueError(f"Version id {version} is already taken; give changed behaviour a new id")
        cls.version_id = version
        _REGISTRY[version] = cls
        return cls
    return wrap


def candidate_versions():
    return sorted(_REGISTRY)


def build_candidate(version, strategy_cfg):
    """A ready-to-use strategy object for a registered candidate."""
    if version not in _REGISTRY:
        known = ", ".join(candidate_versions()) or "none registered yet"
        raise KeyError(f"Unknown candidate '{version}' (known: {known})")
    strat = _REGISTRY[version](strategy_cfg)
    strat.version = version
    return strat


def build_baseline(strategy_cfg):
    return TrendMomentum(strategy_cfg)
