"""
JEEV — Location Intelligence Service

Provides an approximate current location using network/IP geolocation.

Important:
- Does NOT use OpenRouter.
- Does NOT require an API key.
- Does NOT expose raw IP coordinates in the returned text.
- Location is approximate and must never be presented as an exact address.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

# ============================================================
# CONFIGURATION
# ============================================================

LOCATION_TIMEOUT = float(
    os.getenv("JEEV_LOCATION_TIMEOUT", "5")
)

LOCATION_API_URL = "https://ipapi.co/json/"

# ============================================================
# LOGGING
# ============================================================

logger = logging.getLogger("jeev_location")

# ============================================================
# HTTP JSON
# ============================================================


def _get_json(url: str) -> dict[str, Any]:
    """
    Fetch a JSON response from a URL.
    """

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "JEEV/1.0 location-service"
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=LOCATION_TIMEOUT,
    ) as response:

        raw = response.read().decode(
            "utf-8",
            errors="replace",
        )

    data = json.loads(raw)

    if not isinstance(data, dict):
        raise ValueError(
            "Location service returned invalid JSON."
        )

    return data


# ============================================================
# LOCATION
# ============================================================


def get_user_location() -> str:
    """
    Return an approximate human-readable location.

    Example:

        Approximate current location: Trichy, Tamil Nadu, India
        Timezone: Asia/Kolkata
        Note: location is network/IP based and may be approximate.

    This function never returns an exact street address.
    """

    try:

        logger.info(
            "[JEEV][Location] Requesting approximate location..."
        )

        data = _get_json(
            LOCATION_API_URL
        )

        city = str(
            data.get("city") or ""
        ).strip()

        region = str(
            data.get("region") or ""
        ).strip()

        country = str(
            data.get("country_name") or ""
        ).strip()

        timezone = str(
            data.get("timezone") or ""
        ).strip()

        # ----------------------------------------------------
        # Build human-readable location
        # ----------------------------------------------------

        parts = [
            value
            for value in (
                city,
                region,
                country,
            )
            if value
        ]

        if not parts:

            logger.warning(
                "[JEEV][Location] "
                "Location service returned no usable location."
            )

            return (
                "Approximate location could not "
                "be determined."
            )

        result = (
            "Approximate current location: "
            + ", ".join(parts)
        )

        if timezone:

            result += (
                f"\nTimezone: {timezone}"
            )

        result += (
            "\nNote: location is network/IP based "
            "and may be approximate."
        )

        logger.info(
            "[JEEV][Location] Location detected: "
            + ", ".join(parts)
        )

        return result

    except Exception as exc:

        logger.warning(
            "[JEEV][Location] "
            f"Location lookup failed: {exc}"
        )

        return (
            "Approximate location is currently "
            "unavailable."
        )


# ============================================================
# SIMPLE LOCATION DATA
# ============================================================


def get_location_data() -> dict[str, Any]:
    """
    Return structured approximate location data.

    This is useful for other JEEV services such as news,
    weather, maps, etc.

    Example result:

        {
            "city": "Trichy",
            "region": "Tamil Nadu",
            "country": "India",
            "timezone": "Asia/Kolkata",
            "latitude": ...,
            "longitude": ...,
            "approximate": True
        }

    Raw coordinates are returned only to internal callers.
    They should NOT automatically be spoken to the user.
    """

    try:

        data = _get_json(
            LOCATION_API_URL
        )

        return {
            "city": str(
                data.get("city") or ""
            ).strip(),

            "region": str(
                data.get("region") or ""
            ).strip(),

            "country": str(
                data.get("country_name") or ""
            ).strip(),

            "timezone": str(
                data.get("timezone") or ""
            ).strip(),

            "latitude": data.get(
                "latitude"
            ),

            "longitude": data.get(
                "longitude"
            ),

            "approximate": True,

            "source": "ipapi",
        }

    except Exception as exc:

        logger.warning(
            "[JEEV][Location] "
            f"Structured lookup failed: {exc}"
        )

        return {
            "city": "",
            "region": "",
            "country": "",
            "timezone": "",
            "latitude": None,
            "longitude": None,
            "approximate": True,
            "source": "unavailable",
            "error": str(exc),
        }


# ============================================================
# SHORT LOCATION
# ============================================================


def get_short_location() -> str:
    """
    Return only:

        City, Region, Country

    Useful when another service such as news needs
    a search query.
    """

    data = get_location_data()

    parts = [
        value
        for value in (
            data.get("city"),
            data.get("region"),
            data.get("country"),
        )
        if value
    ]

    if not parts:

        return ""

    return ", ".join(parts)


# ============================================================
# LOCATION STATUS
# ============================================================


def location_available() -> bool:
    """
    Quickly determine whether approximate location
    information is available.
    """

    data = get_location_data()

    return bool(
        data.get("city")
        or data.get("region")
        or data.get("country")
    )


# ============================================================
# COMPATIBILITY ALIASES
# ============================================================


def get_location() -> str:
    """
    Compatibility alias.
    """

    return get_user_location()


def get_current_location() -> str:
    """
    Compatibility alias.
    """

    return get_user_location()


# ============================================================
# SELF TEST
# ============================================================


if __name__ == "__main__":

    print("=" * 60)
    print("JEEV — Location Service Self-Test")
    print("=" * 60)

    print("\n[TEST 1] Location lookup...")

    location = get_user_location()

    print(
        "Location:"
    )

    print(location)

    print(
        "\n[TEST 2] Structured location..."
    )

    data = get_location_data()

    print(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )
    )

    print(
        "\n[TEST 3] Short location..."
    )

    print(
        get_short_location()
        or "Unavailable"
    )

    print(
        "\n[TEST 4] Availability..."
    )

    print(
        "Available:",
        location_available(),
    )

    print("\n" + "=" * 60)
    print(
        "JEEV — Location Service Test Complete"
    )
    print("=" * 60)