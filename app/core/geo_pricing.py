"""Resolves which REGION a signup/checkout should be priced in. Not to be
confused with core/pricing.py (that's per-generation credit cost — a
completely different "pricing"). This is about which currency/Plan row a
person sees for a subscription tier — see Plan's docstring (region/
plan_group) for how the regional variants are modeled.

Deliberately NOT GeoIP-based: IP geolocation is wrong often enough (VPNs,
corporate proxies, mobile carriers routing through a different country) that
guessing a person's billing currency from it makes a bad first impression —
worse than asking. The frontend is expected to let the user pick their
region/currency explicitly (e.g. at signup, or a currency switcher), and
pass it through as `region` on requests that need it. This module's only
job is picking a sane DEFAULT before that choice is made, and validating
whatever the frontend does send.

Only two regions exist right now — IN and US (see the 2026-08-28 seed
migration) — deliberately not generalized further until real usage tells us
what else is needed.
"""

DEFAULT_REGION = "IN"
SUPPORTED_REGIONS = {"IN", "US"}


def normalize_region(region: str | None) -> str:
    """Falls back to DEFAULT_REGION for anything missing or not in
    SUPPORTED_REGIONS, rather than erroring — an unrecognized region
    (a stale frontend build, a typo, a country we don't price for yet)
    should degrade to the default price list, not break checkout."""
    if region and region.upper() in SUPPORTED_REGIONS:
        return region.upper()
    return DEFAULT_REGION
