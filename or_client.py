from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests


# ============================================================
# OPTIONAL DOTENV SUPPORT
# ============================================================

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("openrouter_client")


# ============================================================
# PATHS
# ============================================================

def _get_base_dir() -> Path:
    """
    Return the directory containing JEEV.

    Works with:
        - normal Python execution
        - packaged/frozen execution
    """

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


BASE_DIR = _get_base_dir()

ENV_PATH = BASE_DIR / ".env"

API_KEY_PATH = (
    BASE_DIR
    / "config"
    / "api_keys.json"
)


# ============================================================
# LOAD .ENV
# ============================================================

if load_dotenv is not None:
    try:
        load_dotenv(
            dotenv_path=ENV_PATH,
            override=False,
        )
    except Exception as e:
        logger.warning(
            "[OpenRouter] Could not load .env: %s",
            e,
        )


# ============================================================
# OPENROUTER
# ============================================================

API_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

MODELS_URL = (
    "https://openrouter.ai/api/v1/models"
)


# ============================================================
# FREE-ONLY ROUTING
# ============================================================
# JEEV must NEVER send an inference request to a paid/non-free model.
# Coding, normal chat, JSON, vision, and multi-turn requests all use
# OpenRouter's free router and dynamically discovered zero-price models.
FREE_ROUTER_MODEL = "openrouter/free"


# ============================================================
# GENERATION DEFAULTS
# ============================================================

DEFAULT_MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.7

MEMORY_MAX_TOKENS = 1200

# IMPORTANT:
#
# The old value was 60 seconds.
# If the listener shares a thread with an AI call, that can
# make JEEV appear frozen for a long time.
#
# Keep network operations bounded.
REQUEST_TIMEOUT = 20


# ============================================================
# STAGE CONFIGURATION
# ============================================================

MAX_STAGE_MODELS = 6


# ============================================================
# RETRY CONFIGURATION
# ============================================================

MAX_RETRIES_PER_MODEL = 1


# ============================================================
# COOLDOWNS
# ============================================================

DEFAULT_RATE_LIMIT_COOLDOWN = 300

MAX_RATE_LIMIT_COOLDOWN = 3600

FAILED_MODEL_COOLDOWN = 600

# Short provider-failure circuit breaker. Once the entire fallback chain has
# failed, do not immediately hammer OpenRouter again from another JEEV task.
# This is intentionally much shorter than the 429/account cooldown.
PROVIDER_FAILURE_COOLDOWN = 30


# ============================================================
# MODEL DISCOVERY
# ============================================================

DYNAMIC_MODELS_CACHE_TTL = 300

MAX_DYNAMIC_FREE_MODELS = 20
MAX_DYNAMIC_PAID_MODELS = 12


# ============================================================
# GLOBAL STATE
# ============================================================

_rate_limited: dict[str, float] = {}

_failed_models: dict[str, float] = {}

_dynamic_models_cache: list[str] = []

_dynamic_vision_models_cache: list[str] = []

_dynamic_models_cache_time: float = 0.0

_dynamic_vision_models_cache_time: float = 0.0

_dynamic_paid_models_cache: list[str] = []
_dynamic_paid_models_cache_time: float = 0.0


# ============================================================
# ACCOUNT/GLOBAL RATE LIMIT
# ============================================================

_global_account_rate_limit_until: float = 0.0

_provider_failure_until: float = 0.0


# ============================================================
# API KEY
# ============================================================

def _load_api_key() -> str:
    """
    Load OpenRouter API key.

    Priority:

        1. OPENROUTER_API_KEY from environment/.env
        2. config/api_keys.json
    """

    # --------------------------------------------------------
    # 1. Environment / .env
    # --------------------------------------------------------

    env_key = os.getenv(
        "OPENROUTER_API_KEY",
        "",
    ).strip()

    if env_key:
        logger.info(
            "[OpenRouter] API key loaded from "
            "environment/.env"
        )
        return env_key

    # --------------------------------------------------------
    # 2. config/api_keys.json
    # --------------------------------------------------------

    if API_KEY_PATH.exists():
        try:
            with open(
                API_KEY_PATH,
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)

            key = str(
                data.get(
                    "openrouter_api_key",
                    "",
                )
            ).strip()

            if key:
                logger.info(
                    "[OpenRouter] API key loaded from "
                    "config/api_keys.json"
                )
                return key

        except json.JSONDecodeError as e:
            logger.warning(
                "[OpenRouter] api_keys.json contains "
                "invalid JSON: %s",
                e,
            )

        except Exception as e:
            logger.warning(
                "[OpenRouter] Could not read "
                "api_keys.json: %s",
                e,
            )

    # --------------------------------------------------------
    # Nothing found
    # --------------------------------------------------------

    raise RuntimeError(
        "OpenRouter API key not found.\n\n"
        f"Expected .env at:\n{ENV_PATH}\n\n"
        "Add:\n"
        "OPENROUTER_API_KEY=YOUR_KEY_HERE"
    )


# ============================================================
# CLIENT
# ============================================================

class OpenRouterClient:

    def __init__(self) -> None:

        self.api_key = _load_api_key()

        self._headers = {
            "Authorization": (
                f"Bearer {self.api_key}"
            ),
            "Content-Type": "application/json",
            "HTTP-Referer": (
                "https://github.com/mark-xxv"
            ),
            "X-Title": "JEEV",
        }

        logger.info(
            "[OpenRouter] Client initialized successfully"
        )

    # ========================================================
    # ACCOUNT RATE LIMIT
    # ========================================================

    def _account_rate_limit_active(self) -> bool:

        return (
            time.time()
            < _global_account_rate_limit_until
        )

    def _account_rate_limit_remaining(self) -> int:

        remaining = (
            _global_account_rate_limit_until
            - time.time()
        )

        if remaining <= 0:
            return 0

        return max(
            1,
            int(remaining),
        )

    def _mark_account_rate_limited(
        self,
        cooldown: int,
    ) -> None:

        global _global_account_rate_limit_until

        cooldown = max(
            1,
            min(
                int(cooldown),
                MAX_RATE_LIMIT_COOLDOWN,
            ),
        )

        new_until = (
            time.time()
            + cooldown
        )

        if (
            new_until
            > _global_account_rate_limit_until
        ):
            _global_account_rate_limit_until = (
                new_until
            )

        logger.warning(
            "[OpenRouter] ACCOUNT/GLOBAL "
            "rate limit detected — "
            "cooldown %ss",
            cooldown,
        )

    # ========================================================
    # MODEL RATE LIMIT
    # ========================================================

    def _is_rate_limited(
        self,
        model: str,
    ) -> bool:

        timestamp = _rate_limited.get(model)

        if timestamp is None:
            return False

        if (
            time.time()
            - timestamp
            >= DEFAULT_RATE_LIMIT_COOLDOWN
        ):
            del _rate_limited[model]
            return False

        return True

    def _mark_rate_limited(
        self,
        model: str,
        cooldown: Optional[int] = None,
    ) -> None:

        if cooldown is None:
            cooldown = DEFAULT_RATE_LIMIT_COOLDOWN

        _rate_limited[model] = time.time()

        logger.warning(
            "[OpenRouter] Model rate limited: "
            "%s — cooling down for %ss",
            model,
            cooldown,
        )

    # ========================================================
    # FAILED MODEL
    # ========================================================

    def _is_failed_model(
        self,
        model: str,
    ) -> bool:

        timestamp = _failed_models.get(model)

        if timestamp is None:
            return False

        if (
            time.time()
            - timestamp
            >= FAILED_MODEL_COOLDOWN
        ):
            del _failed_models[model]
            return False

        return True

    def _mark_failed_model(
        self,
        model: str,
    ) -> None:

        _failed_models[model] = time.time()

        logger.warning(
            "[OpenRouter] Temporarily disabling "
            "%s for %ss",
            model,
            FAILED_MODEL_COOLDOWN,
        )

    # ========================================================
    # RETRY-AFTER
    # ========================================================

    @staticmethod
    def _get_retry_after(
        response: requests.Response,
    ) -> int:

        value = response.headers.get(
            "Retry-After"
        )

        if value:
            try:
                seconds = int(float(value))

                return max(
                    1,
                    min(
                        seconds,
                        MAX_RATE_LIMIT_COOLDOWN,
                    ),
                )

            except (ValueError, TypeError):
                pass

        return DEFAULT_RATE_LIMIT_COOLDOWN

    # ========================================================
    # DETECT ACCOUNT/GLOBAL 429
    # ========================================================

    @staticmethod
    def _is_account_rate_limit_response(
        response: requests.Response,
    ) -> bool:

        body = ""

        try:
            body = response.text[:5000].lower()
        except Exception:
            pass

        account_terms = (
            "account",
            "credits",
            "credit limit",
            "monthly limit",
            "daily limit",
            "free limit",
            "rate limit exceeded",
            "rate-limit exceeded",
            "global rate limit",
            "too many requests",
        )

        provider_terms = (
            "provider",
            "model",
            "upstream",
            "temporarily unavailable",
            "capacity",
            "overloaded",
        )

        has_account_term = any(
            term in body
            for term in account_terms
        )

        has_provider_term = any(
            term in body
            for term in provider_terms
        )

        if (
            has_provider_term
            and not has_account_term
        ):
            return False

        if has_account_term:
            return True

        return False

    # ========================================================
    # DYNAMIC FREE MODEL DISCOVERY
    # ========================================================

    def _discover_free_models(
        self,
        vision: bool = False,
    ) -> list[str]:

        global _dynamic_models_cache
        global _dynamic_vision_models_cache
        global _dynamic_models_cache_time
        global _dynamic_vision_models_cache_time

        now = time.time()

        # ----------------------------------------------------
        # CACHE
        # ----------------------------------------------------

        if vision:

            if (
                _dynamic_vision_models_cache
                and (
                    now
                    - _dynamic_vision_models_cache_time
                    < DYNAMIC_MODELS_CACHE_TTL
                )
            ):
                return list(
                    _dynamic_vision_models_cache
                )

        else:

            if (
                _dynamic_models_cache
                and (
                    now
                    - _dynamic_models_cache_time
                    < DYNAMIC_MODELS_CACHE_TTL
                )
            ):
                return list(
                    _dynamic_models_cache
                )

        # ----------------------------------------------------
        # MODEL LIST REQUEST
        # ----------------------------------------------------

        try:

            response = requests.get(
                MODELS_URL,
                headers={
                    "Authorization":
                        f"Bearer {self.api_key}",
                },
                timeout=10,
            )

            if response.status_code != 200:

                logger.warning(
                    "[OpenRouter] Model discovery "
                    "failed: HTTP %s",
                    response.status_code,
                )

                return []

            data = response.json()

            models = data.get(
                "data",
                [],
            )

            free_models: list[str] = []

            # ------------------------------------------------
            # FIND FREE MODELS
            # ------------------------------------------------

            for model_data in models:

                model_id = model_data.get(
                    "id"
                )

                if not model_id:
                    continue

                # Never include router itself.

                if model_id == FREE_ROUTER_MODEL:
                    continue

                pricing = model_data.get(
                    "pricing",
                    {},
                )

                prompt_price = str(
                    pricing.get(
                        "prompt",
                        "",
                    )
                ).strip()

                completion_price = str(
                    pricing.get(
                        "completion",
                        "",
                    )
                ).strip()

                is_free = (
                    prompt_price
                    in {
                        "0",
                        "0.0",
                        "0.00",
                        "0.000000",
                    }
                    and
                    completion_price
                    in {
                        "0",
                        "0.0",
                        "0.00",
                        "0.000000",
                    }
                )

                if not is_free:
                    continue

                # ------------------------------------------------
                # Vision filtering
                # ------------------------------------------------

                if vision:

                    architecture = (
                        model_data.get(
                            "architecture",
                            {},
                        )
                    )

                    input_modalities = (
                        architecture.get(
                            "input_modalities",
                            [],
                        )
                    )

                    if (
                        "image"
                        not in input_modalities
                    ):
                        continue

                free_models.append(
                    model_id
                )

            # ------------------------------------------------
            # Remove duplicates
            # ------------------------------------------------

            unique_models = []

            seen = set()

            for model in free_models:

                if model in seen:
                    continue

                seen.add(model)

                unique_models.append(
                    model
                )

            free_models = unique_models[
                :MAX_DYNAMIC_FREE_MODELS
            ]

            # ------------------------------------------------
            # CACHE
            # ------------------------------------------------

            if vision:

                _dynamic_vision_models_cache = (
                    list(free_models)
                )

                _dynamic_vision_models_cache_time = (
                    now
                )

            else:

                _dynamic_models_cache = (
                    list(free_models)
                )

                _dynamic_models_cache_time = (
                    now
                )

            logger.info(
                "[OpenRouter] Discovered %s free "
                "model(s)",
                len(free_models),
            )

            return free_models

        except requests.exceptions.Timeout:

            logger.warning(
                "[OpenRouter] Model discovery "
                "timed out"
            )

        except requests.exceptions.RequestException as e:

            logger.warning(
                "[OpenRouter] Model discovery "
                "error: %s",
                e,
            )

        except Exception as e:

            logger.warning(
                "[OpenRouter] Unexpected model "
                "discovery error: %s",
                e,
            )

        return []

    # ========================================================
    # CODING MODEL DISCOVERY
    # ========================================================

    @staticmethod
    def _is_coding_request(messages: list[dict]) -> bool:
        """Detect JEEV Coding Agent conversations without changing callers."""
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = message.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    str(item.get("text", ""))
                    for item in content
                    if isinstance(item, dict)
                )
            text = str(content).lower()
            if "jeev coding agent" in text:
                return True
        return False

    @staticmethod
    def _model_is_free(model_data: dict) -> bool:
        pricing = model_data.get("pricing", {}) or {}
        prompt = str(pricing.get("prompt", "")).strip()
        completion = str(pricing.get("completion", "")).strip()
        zero = {"0", "0.0", "0.00", "0.000000", "0.0000000"}
        return prompt in zero and completion in zero

    def _discover_paid_models(self, vision: bool = False) -> list[str]:
        """
        Compatibility stub.

        JEEV is configured FREE-ONLY. Paid model discovery is intentionally
        disabled so this method can never contribute a paid inference target.
        """
        logger.info(
            "[OpenRouter] Paid model discovery disabled by FREE-ONLY policy."
        )
        return []

    # ========================================================
    # RAW API CALL
    # ========================================================

    def _call(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        response_format: Optional[dict] = None,
    ) -> Optional[str]:

        # ----------------------------------------------------
        # ACCOUNT GLOBAL LIMIT
        # ----------------------------------------------------

        if self._account_rate_limit_active():

            remaining = (
                self._account_rate_limit_remaining()
            )

            logger.warning(
                "[OpenRouter] Request blocked by "
                "account rate-limit cooldown. "
                "~%ss remaining.",
                remaining,
            )

            return None

        # ----------------------------------------------------
        # PAYLOAD
        # ----------------------------------------------------

        payload: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if response_format:
            payload["response_format"] = (
                response_format
            )

        # ----------------------------------------------------
        # REQUEST
        # ----------------------------------------------------

        for attempt in range(
            1,
            MAX_RETRIES_PER_MODEL + 1,
        ):

            try:

                response = requests.post(
                    API_URL,
                    headers=self._headers,
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                )

                status = response.status_code

                # =================================================
                # SUCCESS
                # =================================================

                if status == 200:

                    try:
                        data = response.json()

                    except Exception as e:

                        logger.warning(
                            "[OpenRouter] %s returned "
                            "invalid JSON: %s",
                            model,
                            e,
                        )

                        return None

                    choices = data.get(
                        "choices"
                    )

                    if not choices:

                        logger.warning(
                            "[OpenRouter] %s returned "
                            "no choices",
                            model,
                        )

                        return None

                    message = choices[0].get(
                        "message",
                        {},
                    )

                    content = message.get(
                        "content",
                        "",
                    )

                    # ------------------------------------------------
                    # Provider may return list content.
                    # ------------------------------------------------

                    if isinstance(
                        content,
                        list,
                    ):

                        text_parts = []

                        for item in content:

                            if isinstance(
                                item,
                                dict,
                            ):

                                text = item.get(
                                    "text"
                                )

                                if text:
                                    text_parts.append(
                                        str(text)
                                    )

                            elif isinstance(
                                item,
                                str,
                            ):

                                text_parts.append(
                                    item
                                )

                        content = "\n".join(
                            text_parts
                        )

                    if content is None:
                        return None

                    content = str(
                        content
                    ).strip()

                    if not content:
                        logger.warning(
                            "[OpenRouter] %s returned "
                            "empty content",
                            model,
                        )
                        return None

                    return content

                # =================================================
                # AUTHENTICATION
                # =================================================

                if status in {
                    401,
                    403,
                }:

                    body = ""

                    try:
                        body = response.text[:1000]
                    except Exception:
                        pass

                    logger.error(
                        "[OpenRouter] %s → HTTP %s "
                        "(authentication/permission error)",
                        model,
                        status,
                    )

                    if body:
                        logger.error(
                            "[OpenRouter] Server "
                            "response: %s",
                            body,
                        )

                    # IMPORTANT:
                    #
                    # Authentication is not a provider/model
                    # failure. Marking it as failed would hide
                    # the actual configuration problem.
                    #
                    # Raise here so the higher-level safe wrapper
                    # can log it properly.

                    raise RuntimeError(
                        "OpenRouter authentication "
                        f"failed (HTTP {status}). "
                        "Check OPENROUTER_API_KEY."
                    )

                # =================================================
                # RATE LIMIT
                # =================================================

                if status == 429:

                    cooldown = (
                        self._get_retry_after(
                            response
                        )
                    )

                    is_account_limit = (
                        self._is_account_rate_limit_response(
                            response
                        )
                    )

                    body_lower = ""
                    try:
                        body_lower = response.text[:5000].lower()
                    except Exception:
                        pass

                    # A free-model daily quota is NOT an account-wide paid-model
                    # outage.  Do not poison the global cooldown; immediately let
                    # the coding fallback move to a paid model.
                    free_quota_limit = (
                        "free-models-per-day" in body_lower
                        or "free models per day" in body_lower
                        or "free-model limit" in body_lower
                        or "free limit" in body_lower
                    )

                    if is_account_limit and not free_quota_limit:

                        self._mark_account_rate_limited(cooldown)

                        logger.error(
                            "[OpenRouter] %s → HTTP 429 ACCOUNT/GLOBAL RATE LIMIT",
                            model,
                        )

                    else:

                        self._mark_rate_limited(model, cooldown)

                        if free_quota_limit:
                            logger.warning(
                                "[OpenRouter] %s → HTTP 429 FREE-MODEL DAILY QUOTA; "
                                "paid inference is disabled.",
                                model,
                            )

                        logger.warning(
                            "[OpenRouter] %s → HTTP 429 "
                            "MODEL/PROVIDER RATE LIMIT",
                            model,
                        )

                    return None

                # =================================================
                # MODEL / REQUEST UNAVAILABLE
                # =================================================

                if status in {
                    400,
                    404,
                    405,
                    408,
                    409,
                    422,
                }:

                    body = ""

                    try:
                        body = response.text[:1000]
                    except Exception:
                        pass

                    logger.warning(
                        "[OpenRouter] %s → HTTP %s "
                        "(model/request unavailable)",
                        model,
                        status,
                    )

                    if body:
                        logger.debug(
                            "[OpenRouter] Response: %s",
                            body,
                        )

                    self._mark_failed_model(
                        model
                    )

                    return None

                # =================================================
                # SERVER ERROR
                # =================================================

                if 500 <= status <= 599:

                    logger.warning(
                        "[OpenRouter] %s → HTTP %s "
                        "(server error, attempt %s/%s)",
                        model,
                        status,
                        attempt,
                        MAX_RETRIES_PER_MODEL,
                    )

                else:

                    logger.warning(
                        "[OpenRouter] %s → HTTP %s "
                        "(attempt %s/%s)",
                        model,
                        status,
                        attempt,
                        MAX_RETRIES_PER_MODEL,
                    )

            except requests.exceptions.Timeout:

                logger.warning(
                    "[OpenRouter] %s → Timeout "
                    "(attempt %s/%s)",
                    model,
                    attempt,
                    MAX_RETRIES_PER_MODEL,
                )

            except requests.exceptions.ConnectionError as e:

                logger.warning(
                    "[OpenRouter] %s → Connection "
                    "error: %s",
                    model,
                    e,
                )

            except requests.exceptions.RequestException as e:

                logger.warning(
                    "[OpenRouter] %s → Request "
                    "error: %s",
                    model,
                    e,
                )

            except RuntimeError:
                raise

            except Exception as e:

                logger.error(
                    "[OpenRouter] %s → Unexpected "
                    "error: %s",
                    model,
                    e,
                )

            # ----------------------------------------------------
            # Retry only non-429 request failures.
            # ----------------------------------------------------

            if (
                attempt
                < MAX_RETRIES_PER_MODEL
            ):

                time.sleep(1)

        return None

    # ========================================================
    # THREE-STAGE ROUTER
    # ========================================================

    def _provider_failure_active(self) -> bool:
        return time.time() < _provider_failure_until

    @staticmethod
    def _mark_provider_failure() -> None:
        global _provider_failure_until
        _provider_failure_until = max(
            _provider_failure_until,
            time.time() + PROVIDER_FAILURE_COOLDOWN,
        )


    def _call_with_fallback(
        self,
        pool: list[str],
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        response_format: Optional[dict] = None,
        vision: bool = False,
    ) -> str:
        """
        Execute inference through the configured fallback chain.

        IMPORTANT SAFETY CONTRACT:

        This method NEVER allows ordinary provider/model
        unavailability to escape into JEEV's main runtime.

        On complete provider failure it returns "".

        Only explicit configuration/authentication errors are
        retained internally and converted to a safe empty result
        at the public API boundary.
        """

        try:

            # ------------------------------------------------
            # PROVIDER FAILURE CIRCUIT BREAKER
            # ----------------------------------------------------
            # OpenRouter is optional. A recently failed fallback chain should
            # fail fast instead of making JEEV look frozen.
            if self._provider_failure_active():
                remaining = max(1, int(_provider_failure_until - time.time()))
                logger.warning(
                    "[OpenRouter] Provider circuit open; skipping inference for ~%ss.",
                    remaining,
                )
                return ""

            # ------------------------------------------------
            # ACCOUNT LIMIT
            # ------------------------------------------------

            if self._account_rate_limit_active():

                remaining = self._account_rate_limit_remaining()

                logger.warning(
                    "[OpenRouter] Account rate-limited. Inference skipped. "
                    "Retry in approximately %ss.",
                    remaining,
                )

                return ""

            # ====================================================
            # BUILD MODEL LIST — FREE ONLY
            # ====================================================
            #
            # IMPORTANT:
            # No inference request is ever allowed to use a paid model.
            # This applies equally to normal chat, coding, JSON, vision,
            # and multi-turn requests.
            #
            # If a caller supplies a model explicitly, we validate it
            # against OpenRouter's zero-price model list. If it is not
            # known to be free, it is ignored and the free pool is used.
            candidates: list[str] = []

            discovered = self._discover_free_models(vision=vision)

            # The OpenRouter free router is always the first choice.
            candidates.append(FREE_ROUTER_MODEL)

            # Add dynamically discovered zero-price models.
            for discovered_model in discovered:
                if discovered_model not in candidates:
                    candidates.append(discovered_model)
                if len(candidates) >= MAX_STAGE_MODELS:
                    break

            # An explicitly requested model is allowed ONLY if it is
            # confirmed free by discovery. Never trust a caller-provided
            # model name by itself.
            if model:
                requested_model = str(model).strip()
                if requested_model == FREE_ROUTER_MODEL:
                    pass
                elif requested_model in discovered:
                    # Put a confirmed-free explicit model first.
                    candidates = [
                        requested_model,
                        *[m for m in candidates if m != requested_model],
                    ][:MAX_STAGE_MODELS]
                    logger.info(
                        "[OpenRouter] Explicit model accepted as FREE: %s",
                        requested_model,
                    )
                else:
                    logger.warning(
                        "[OpenRouter] Ignoring requested model '%s' because "
                        "it is not confirmed FREE. FREE-ONLY policy enforced.",
                        requested_model,
                    )

            if self._is_coding_request(messages):
                logger.info(
                    "[OpenRouter] Coding route: FREE models only. "
                    "Paid/non-free inference is disabled."
                )

            # ------------------------------------------------
            # Remove duplicates
            # ------------------------------------------------

            unique_candidates = []

            seen = set()

            for candidate in candidates:

                if candidate in seen:
                    continue

                seen.add(candidate)

                unique_candidates.append(
                    candidate
                )

            candidates = unique_candidates

            if not candidates:

                logger.warning(
                    "[OpenRouter] No usable free "
                    "inference candidates found."
                )

                return ""

            # ====================================================
            # EXECUTE STAGES — FREE ONLY
            # ====================================================

            # Final defense: every candidate must be the free router or a
            # model discovered from OpenRouter with zero prompt/completion
            # pricing. This prevents future routing changes from
            # accidentally sending a paid inference request.
            free_set = set(discovered)
            free_set.add(FREE_ROUTER_MODEL)
            candidates = [
                candidate
                for candidate in candidates
                if candidate in free_set
            ]

            if not candidates:
                logger.warning(
                    "[OpenRouter] No confirmed FREE inference candidates found."
                )
                return ""

            last_error = None

            for index, target_model in enumerate(
                candidates,
                start=1,
            ):

                # ------------------------------------------------
                # ACCOUNT LIMIT CHECK
                # ------------------------------------------------

                if self._account_rate_limit_active():

                    remaining = (
                        self._account_rate_limit_remaining()
                    )

                    logger.warning(
                        "[OpenRouter] Free-only account/global rate limit "
                        "activated during fallback. Stopping inference. "
                        "Retry in approximately %ss.",
                        remaining,
                    )

                    return ""

                # ------------------------------------------------
                # MODEL COOLDOWN
                # ------------------------------------------------

                if self._is_rate_limited(
                    target_model
                ):

                    logger.warning(
                        "[OpenRouter] Stage %s/%s "
                        "→ Skipping rate-limited model: %s",
                        index,
                        len(candidates),
                        target_model,
                    )

                    last_error = (
                        f"{target_model} rate limited"
                    )

                    continue

                # ------------------------------------------------
                # FAILED MODEL
                # ------------------------------------------------

                if self._is_failed_model(
                    target_model
                ):

                    logger.warning(
                        "[OpenRouter] Stage %s/%s "
                        "→ Skipping failed model: %s",
                        index,
                        len(candidates),
                        target_model,
                    )

                    last_error = (
                        f"{target_model} unavailable"
                    )

                    continue

                # ------------------------------------------------
                # STAGE LOG
                # ------------------------------------------------

                logger.info(
                    "[OpenRouter] Stage %s/%s → Trying: %s",
                    index,
                    len(candidates),
                    target_model,
                )

                # ------------------------------------------------
                # CALL
                # ------------------------------------------------

                try:

                    result = self._call(
                        target_model,
                        messages,
                        max_tokens,
                        temperature,
                        response_format,
                    )

                except RuntimeError as e:

                    # Authentication/configuration failure.
                    #
                    # Do NOT allow this to kill the caller.

                    logger.error(
                        "[OpenRouter] Stage %s "
                        "configuration/authentication failure: %s",
                        index,
                        e,
                    )

                    last_error = str(e)

                    # No point hammering other models when the
                    # same API key is invalid.

                    break

                except Exception as e:

                    # Absolute final safety barrier.
                    #
                    # A provider bug must NEVER terminate JEEV.

                    logger.exception(
                        "[OpenRouter] Stage %s unexpected "
                        "failure: %s",
                        index,
                        e,
                    )

                    last_error = str(e)

                    continue

                # ------------------------------------------------
                # SUCCESS
                # ------------------------------------------------

                if result:

                    logger.info(
                        "[OpenRouter] ✓ Stage %s SUCCESS: %s",
                        index,
                        target_model,
                    )

                    return result

                # ------------------------------------------------
                # ACCOUNT LIMIT
                # ------------------------------------------------

                if self._account_rate_limit_active():

                    remaining = (
                        self._account_rate_limit_remaining()
                    )

                    logger.warning(
                        "[OpenRouter] Account rate limit "
                        "reached. Retry in approximately %ss.",
                        remaining,
                    )

                    return ""

                # ------------------------------------------------
                # MODEL FAILURE
                # ------------------------------------------------

                if self._is_rate_limited(
                    target_model
                ):

                    logger.warning(
                        "[OpenRouter] Stage %s failed "
                        "due to model rate limit.",
                        index,
                    )

                    last_error = (
                        f"{target_model} rate limited"
                    )

                    continue

                if self._is_failed_model(
                    target_model
                ):

                    logger.warning(
                        "[OpenRouter] Stage %s model unavailable.",
                        index,
                    )

                    last_error = (
                        f"{target_model} unavailable"
                    )

                    continue

                last_error = (
                    f"{target_model} returned "
                    "no usable response"
                )

            # ====================================================
            # NOTHING WORKED
            # ====================================================

            logger.warning(
                "[OpenRouter] All inference stages failed. Last error: %s",
                last_error or "unknown",
            )

            if not self._account_rate_limit_active():
                self._mark_provider_failure()

            # ====================================================
            # CRITICAL:
            #
            # DO NOT raise RuntimeError here.
            #
            # Returning an empty string keeps OpenRouter failure
            # isolated from JEEV's listening/runtime loop.
            # ====================================================

            return ""

        except Exception as e:

            # ====================================================
            # ABSOLUTE SAFETY BARRIER
            # ====================================================
            #
            # This is deliberately broad.
            #
            # The OpenRouter client is an optional external
            # service. It must never be capable of terminating
            # JEEV's core runtime.
            # ====================================================

            logger.exception(
                "[OpenRouter] Fallback controller failed "
                "safely: %s",
                e,
            )

            return ""

    # ========================================================
    # NORMAL CHAT
    # ========================================================

    def chat(
        self,
        prompt: str,
        system: str = (
            "You are Jeev, a helpful AI assistant. "
            "Be concise, helpful, precise, and natural."
        ),
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:

        try:

            messages = [
                {
                    "role": "system",
                    "content": system,
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]

            result = self._call_with_fallback(
                pool=[],
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            if not result:

                logger.warning(
                    "[OpenRouter] chat() unavailable; "
                    "returning empty response."
                )

                return ""

            return result

        except Exception as e:

            # ------------------------------------------------
            # CRITICAL LISTENER SAFETY BARRIER
            # ------------------------------------------------

            logger.exception(
                "[OpenRouter] chat() failed safely: %s",
                e,
            )

            return ""

    # ========================================================
    # JSON CHAT
    # ========================================================

    def chat_json(
        self,
        prompt: str,
        system: str = (
            "Return ONLY valid JSON. "
            "No markdown fences. "
            "No explanation. "
            "No extra text."
        ),
        model: Optional[str] = None,
        max_tokens: int = MEMORY_MAX_TOKENS,
    ) -> dict:

        messages = [
            {
                "role": "system",
                "content": system,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        try:

            raw = self._call_with_fallback(
                pool=[],
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=0.1,
                response_format={
                    "type": "json_object"
                },
            )

            if not raw:
                logger.warning(
                    "[OpenRouter] Structured JSON "
                    "inference unavailable."
                )

                return {}

        except Exception as first_error:

            logger.warning(
                "[OpenRouter] Structured JSON "
                "request failed safely: %s",
                first_error,
            )

            # ------------------------------------------------
            # DO NOT make a second request if account-level
            # rate limiting is active.
            # ------------------------------------------------

            if self._account_rate_limit_active():
                return {}

            # ------------------------------------------------
            # Second attempt without response_format.
            # ------------------------------------------------

            try:

                logger.info(
                    "[OpenRouter] Retrying JSON request "
                    "without response_format."
                )

                raw = self._call_with_fallback(
                    pool=[],
                    messages=messages,
                    model=model,
                    max_tokens=max_tokens,
                    temperature=0.1,
                    response_format=None,
                )

            except Exception as second_error:

                logger.warning(
                    "[OpenRouter] JSON fallback failed "
                    "safely: %s",
                    second_error,
                )

                return {}

            if not raw:
                return {}

        # ----------------------------------------------------
        # Parse safely.
        # ----------------------------------------------------

        try:

            return self._parse_json_response(
                raw
            )

        except Exception as e:

            logger.warning(
                "[OpenRouter] JSON response could "
                "not be parsed safely: %s",
                e,
            )

            return {}

    # ========================================================
    # JSON PARSER
    # ========================================================

    @staticmethod
    def _parse_json_response(
        raw: str,
    ) -> dict:

        if not raw:
            return {}

        clean = str(
            raw
        ).strip()

        # ----------------------------------------------------
        # Remove markdown fences.
        # ----------------------------------------------------

        if clean.startswith("```"):

            parts = clean.split("```")

            if len(parts) >= 2:

                clean = parts[1].strip()

                if clean.lower().startswith(
                    "json"
                ):
                    clean = clean[
                        4:
                    ].strip()

        clean = clean.strip()

        clean = clean.rstrip(
            "`"
        ).strip()

        # ----------------------------------------------------
        # Direct JSON.
        # ----------------------------------------------------

        try:

            data = json.loads(
                clean
            )

            if isinstance(
                data,
                dict,
            ):
                return data

            return {}

        except json.JSONDecodeError:
            pass

        # ----------------------------------------------------
        # Find object embedded in text.
        # ----------------------------------------------------

        start = clean.find(
            "{"
        )

        end = clean.rfind(
            "}"
        )

        if (
            start >= 0
            and end > start
        ):

            candidate = clean[
                start:
                end + 1
            ]

            try:

                data = json.loads(
                    candidate
                )

                if isinstance(
                    data,
                    dict,
                ):
                    return data

            except json.JSONDecodeError:
                pass

        logger.error(
            "[OpenRouter] JSON parse failed. "
            "Raw response: %s",
            clean[:500],
        )

        raise ValueError(
            "Model returned unparseable JSON. "
            f"Raw output: {clean[:300]}"
        )

    # ========================================================
    # VISION
    # ========================================================

    def vision(
        self,
        prompt: str,
        image_b64: str,
        mime: str = "image/png",
        system: str = (
            "Analyze the image carefully and "
            "describe what you see clearly "
            "and concisely."
        ),
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:

        try:

            messages = [
                {
                    "role": "system",
                    "content": system,
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{mime};base64,"
                                    f"{image_b64}"
                                )
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                },
            ]

            return self._call_with_fallback(
                pool=[],
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=0.2,
                vision=True,
            )

        except Exception as e:

            logger.exception(
                "[OpenRouter] vision() failed safely: %s",
                e,
            )

            return ""

    # ========================================================
    # VISION FROM FILE
    # ========================================================

    def vision_from_file(
        self,
        prompt: str,
        image_path: str,
        system: str = (
            "Analyze the image carefully and "
            "describe what you see clearly "
            "and concisely."
        ),
        model: Optional[str] = None,
        max_tokens: int = 1024,
    ) -> str:

        try:

            path = Path(
                image_path
            )

            if not path.exists():

                logger.error(
                    "[OpenRouter] Image not found: %s",
                    path,
                )

                return ""

            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
            }

            mime = mime_map.get(
                path.suffix.lower(),
                "image/png",
            )

            with open(
                path,
                "rb",
            ) as f:

                image_b64 = (
                    base64.b64encode(
                        f.read()
                    ).decode(
                        "utf-8"
                    )
                )

            return self.vision(
                prompt=prompt,
                image_b64=image_b64,
                mime=mime,
                system=system,
                model=model,
                max_tokens=max_tokens,
            )

        except Exception as e:

            logger.exception(
                "[OpenRouter] vision_from_file() "
                "failed safely: %s",
                e,
            )

            return ""

    # ========================================================
    # MULTI-TURN
    # ========================================================

    def multi_turn(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:

        try:

            if self._is_coding_request(messages) and not model:
                logger.info(
                    "[OpenRouter] multi_turn(): coding request detected; "
                    "FREE-ONLY routing is enforced."
                )

            return self._call_with_fallback(
                pool=[],
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        except Exception as e:

            logger.exception(
                "[OpenRouter] multi_turn() "
                "failed safely: %s",
                e,
            )

            return ""

    # ========================================================
    # MODEL INFORMATION
    # ========================================================

    def available_models(
        self,
    ) -> dict:

        try:

            discovered = (
                self._discover_free_models()
            )

            vision_models = (
                self._discover_free_models(
                    vision=True
                )
            )

            return {
                "primary_text_router":
                    FREE_ROUTER_MODEL,

                "text_models": [
                    FREE_ROUTER_MODEL,
                    *discovered,
                ],

                "vision_models": [
                    FREE_ROUTER_MODEL,
                    *vision_models,
                ],

                "rate_limited":
                    list(
                        _rate_limited.keys()
                    ),

                "temporarily_failed":
                    list(
                        _failed_models.keys()
                    ),

                "global_rate_limit":
                    self._account_rate_limit_active(),

                "global_rate_limit_remaining":
                    self._account_rate_limit_remaining(),

                "total_text":
                    1 + len(discovered),

                "total_vision":
                    1 + len(vision_models),
            }

        except Exception as e:

            logger.exception(
                "[OpenRouter] available_models() "
                "failed safely: %s",
                e,
            )

            return {
                "primary_text_router":
                    FREE_ROUTER_MODEL,

                "text_models": [
                    FREE_ROUTER_MODEL
                ],

                "vision_models": [
                    FREE_ROUTER_MODEL
                ],

                "rate_limited":
                    list(
                        _rate_limited.keys()
                    ),

                "temporarily_failed":
                    list(
                        _failed_models.keys()
                    ),

                "global_rate_limit":
                    self._account_rate_limit_active(),

                "global_rate_limit_remaining":
                    self._account_rate_limit_remaining(),

                "total_text": 1,

                "total_vision": 1,
            }

    # ========================================================
    # HEALTH CHECK
    # ========================================================

    def health_check(
        self,
    ) -> dict:

        result = {
            "available": False,
            "model": FREE_ROUTER_MODEL,
            "message": "",
            "rate_limited": False,
            "retry_after": 0,
        }

        # ----------------------------------------------------
        # Don't request if account is already limited.
        # ----------------------------------------------------

        if self._account_rate_limit_active():

            remaining = (
                self._account_rate_limit_remaining()
            )

            result["message"] = (
                "OpenRouter free inference is "
                "currently rate-limited."
            )

            result["rate_limited"] = True

            result["retry_after"] = remaining

            return result

        # ----------------------------------------------------
        # Actual health request.
        # ----------------------------------------------------

        try:

            reply = self.chat(
                "Reply with exactly: JEEV ONLINE",
                max_tokens=20,
                temperature=0.0,
            )

            if reply:

                result["available"] = True

                result["message"] = reply

                return result

        except Exception as e:

            # This is intentionally defensive.
            #
            # chat() already catches its own failures.

            result["message"] = str(e)

            if self._account_rate_limit_active():

                result["rate_limited"] = True

                result["retry_after"] = (
                    self._account_rate_limit_remaining()
                )

            return result

        result["message"] = (
            "OpenRouter returned no usable response."
        )

        return result


# ============================================================
# GLOBAL CLIENT
# ============================================================

try:

    client = OpenRouterClient()

except Exception as e:

    # ========================================================
    # IMPORTANT RELEASE SAFETY
    # ========================================================
    #
    # If OpenRouter configuration is broken, importing this
    # module should not necessarily destroy the whole JEEV
    # process.
    #
    # However, a client object still needs to exist so callers
    # can safely invoke the normal methods.
    # ========================================================

    logger.exception(
        "[OpenRouter] Client initialization failed: %s",
        e,
    )

    client = None


# ============================================================
# PUBLIC CLIENT ACCESSOR
# ============================================================

def get_client() -> "OpenRouterClient | None":
    """Return a usable OpenRouter client, creating it lazily when needed."""
    global client
    if client is not None:
        return client
    try:
        client = OpenRouterClient()
        return client
    except Exception as exc:
        logger.error("[OpenRouter] Lazy client initialization failed: %s", exc)
        return None


# ============================================================
# SELF TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)

    print(
        "  JEEV — OpenRouter Client Self-Test"
    )

    print("=" * 70)

    # ========================================================
    # TEST 1 — API KEY
    # ========================================================

    print(
        "\n[TEST 1] API key..."
    )

    try:

        if client is None:
            raise RuntimeError(
                "OpenRouter client initialization failed."
            )

        print(
            "  API key loaded : YES"
        )

        print(
            "  Source         : "
            ".env / environment / "
            "config fallback"
        )

        print(
            "  Status         : PASS ✓"
        )

    except Exception as e:

        print(
            f"  Status         : FAIL ✗ — {e}"
        )

    # ========================================================
    # TEST 2 — FREE MODEL DISCOVERY
    # ========================================================

    print(
        "\n[TEST 2] Free model discovery..."
    )

    try:

        if client is None:
            raise RuntimeError(
                "OpenRouter client unavailable."
            )

        info = client.available_models()

        print(
            "  Primary router : "
            f"{info['primary_text_router']}"
        )

        print(
            "  Text models    : "
            f"{info['total_text']}"
        )

        print(
            "  Vision models  : "
            f"{info['total_vision']}"
        )

        print(
            "  Rate limited   : "
            f"{info['rate_limited'] or 'none'}"
        )

        print(
            "  Failed models  : "
            f"{info['temporarily_failed'] or 'none'}"
        )

        print(
            "  Global limit   : "
            f"{info['global_rate_limit']}"
        )

        if info[
            "global_rate_limit_remaining"
        ]:

            print(
                "  Retry in       : "
                f"{info['global_rate_limit_remaining']}s"
            )

        print(
            "  Status         : PASS ✓"
        )

    except Exception as e:

        print(
            f"  Status         : FAIL ✗ — {e}"
        )

    # ========================================================
    # TEST 3 — BASIC CHAT
    # ========================================================

    print(
        "\n[TEST 3] Basic chat..."
    )

    try:

        if client is None:
            raise RuntimeError(
                "OpenRouter client unavailable."
            )

        reply = client.chat(
            "Introduce yourself in one short sentence."
        )

        if reply:

            print(
                f"  Response       : {reply}"
            )

            print(
                "  Status         : PASS ✓"
            )

        else:

            print(
                "  Response       : "
                "No usable response."
            )

            print(
                "  Status         : SAFE FALLBACK"
            )

    except Exception as e:

        print(
            f"  Status         : FAIL ✗ — {e}"
        )

    # ========================================================
    # TEST 4 — JSON
    # ========================================================

    print(
        "\n[TEST 4] JSON mode..."
    )

    try:

        if client is None:
            raise RuntimeError(
                "OpenRouter client unavailable."
            )

        data = client.chat_json(
            (
                "Return a JSON object containing "
                "exactly three programming languages. "
                'Format: {"languages":'
                '["Python","JavaScript","C++"]}'
            )
        )

        print(
            f"  Response       : {data}"
        )

        if data:
            print(
                "  Status         : PASS ✓"
            )
        else:
            print(
                "  Status         : SAFE FALLBACK"
            )

    except Exception as e:

        print(
            f"  Status         : FAIL ✗ — {e}"
        )

    # ========================================================
    # TEST 5 — MULTI-TURN
    # ========================================================

    print(
        "\n[TEST 5] Multi-turn conversation..."
    )

    try:

        if client is None:
            raise RuntimeError(
                "OpenRouter client unavailable."
            )

        history = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. "
                    "Be brief."
                ),
            },
            {
                "role": "user",
                "content": "My name is Tony.",
            },
            {
                "role": "assistant",
                "content": (
                    "Hello Tony, how can I help you?"
                ),
            },
            {
                "role": "user",
                "content": "What is my name?",
            },
        ]

        reply = client.multi_turn(
            history
        )

        print(
            f"  Response       : {reply}"
        )

        if reply:
            print(
                "  Status         : PASS ✓"
            )
        else:
            print(
                "  Status         : SAFE FALLBACK"
            )

    except Exception as e:

        print(
            f"  Status         : FAIL ✗ — {e}"
        )

    # ========================================================
    # TEST 6 — HEALTH CHECK
    # ========================================================

    print(
        "\n[TEST 6] OpenRouter health check..."
    )

    try:

        if client is None:
            raise RuntimeError(
                "OpenRouter client unavailable."
            )

        health = client.health_check()

        print(
            "  Available      : "
            f"{health['available']}"
        )

        print(
            "  Message        : "
            f"{health['message']}"
        )

        if health.get(
            "rate_limited",
            False,
        ):

            print(
                "  Rate limited   : YES"
            )

            print(
                "  Retry after    : "
                f"{health.get('retry_after', 0)}s"
            )

        if health["available"]:

            print(
                "  Status         : PASS ✓"
            )

        else:

            print(
                "  Status         : "
                "UNAVAILABLE — JEEV SAFE"
            )

    except Exception as e:

        print(
            f"  Status         : FAIL ✗ — {e}"
        )

    # ========================================================
    # COMPLETE
    # ========================================================

    print(
        "\n" + "=" * 70
    )

    print(
        "  JEEV — OpenRouter Client Test Complete"
    )

    print(
        "=" * 70
    )