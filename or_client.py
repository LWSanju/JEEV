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
            "[OpenRouter] Could not load .env: "
            f"{e}"
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
# FREE ROUTING
# ============================================================

FREE_ROUTER_MODEL = "openrouter/free"


# ============================================================
# GENERATION DEFAULTS
# ============================================================

DEFAULT_MAX_TOKENS = 4096

DEFAULT_TEMPERATURE = 0.7

MEMORY_MAX_TOKENS = 1200

REQUEST_TIMEOUT = 60


# ============================================================
# STAGE CONFIGURATION
# ============================================================

# Stage 1:
# OpenRouter's free router.
#
# Stage 2:
# First discovered free model.
#
# Stage 3:
# Second/third discovered free models.
#
# We intentionally do not fire many requests at once.

MAX_STAGE_MODELS = 3


# ============================================================
# RETRY CONFIGURATION
# ============================================================

# One request per model.
#
# This is important for free endpoints.
MAX_RETRIES_PER_MODEL = 1


# Default model cooldown.
DEFAULT_RATE_LIMIT_COOLDOWN = 300


# Maximum accepted Retry-After.
MAX_RATE_LIMIT_COOLDOWN = 3600


# Temporarily failed model cooldown.
FAILED_MODEL_COOLDOWN = 600


# ============================================================
# MODEL DISCOVERY
# ============================================================

DYNAMIC_MODELS_CACHE_TTL = 300

MAX_DYNAMIC_FREE_MODELS = 20


# ============================================================
# GLOBAL STATE
# ============================================================

# Model-specific rate limits.
_rate_limited: dict[str, float] = {}


# Model-specific failures.
_failed_models: dict[str, float] = {}


# Free model cache.
_dynamic_models_cache: list[str] = []

_dynamic_vision_models_cache: list[str] = []

_dynamic_models_cache_time: float = 0.0

_dynamic_vision_models_cache_time: float = 0.0


# ============================================================
# ACCOUNT/GLOBAL RATE LIMIT
# ============================================================

# IMPORTANT:
#
# This is only activated when OpenRouter's response indicates
# that the ACCOUNT itself is rate-limited.
#
# A model/provider-specific 429 does NOT activate this.
#
_global_account_rate_limit_until: float = 0.0


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
                f"invalid JSON: {e}"
            )


        except Exception as e:

            logger.warning(
                "[OpenRouter] Could not read "
                f"api_keys.json: {e}"
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
            f"rate limit detected — "
            f"cooldown {cooldown}s"
        )


    # ========================================================
    # MODEL RATE LIMIT
    # ========================================================

    def _is_rate_limited(
        self,
        model: str,
    ) -> bool:

        timestamp = _rate_limited.get(
            model
        )

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
            f"{model} — cooling down for "
            f"{cooldown}s"
        )


    # ========================================================
    # FAILED MODEL
    # ========================================================

    def _is_failed_model(
        self,
        model: str,
    ) -> bool:

        timestamp = _failed_models.get(
            model
        )

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
            f"{model} for "
            f"{FAILED_MODEL_COOLDOWN}s"
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

                seconds = int(
                    float(value)
                )

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
        """
        Determine whether a 429 appears to be an
        account/global rate limit rather than merely
        a particular model/provider being unavailable.
        """

        body = ""

        try:
            body = response.text[:5000].lower()
        except Exception:
            pass


        # ----------------------------------------------------
        # Strong account/global indicators.
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # Provider/model-specific indicators.
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # If OpenRouter explicitly talks about a model/
        # provider, let the fallback stages continue.
        # ----------------------------------------------------

        if has_provider_term and not has_account_term:

            return False


        # ----------------------------------------------------
        # Explicit account-level response.
        # ----------------------------------------------------

        if has_account_term:

            return True


        # ----------------------------------------------------
        # Unknown 429:
        #
        # Treat as model-level first.
        #
        # This allows Stage 2 / Stage 3 to work.
        # ----------------------------------------------------

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
                and
                (
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
                and
                (
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
                timeout=20,
            )


            if response.status_code != 200:

                logger.warning(
                    "[OpenRouter] Model discovery "
                    f"failed: HTTP "
                    f"{response.status_code}"
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


                # ------------------------------------------------
                # Never include the router here.
                # ------------------------------------------------

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
                # Vision filtering.
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
            # Remove duplicates.
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
                "[OpenRouter] Discovered "
                f"{len(free_models)} free "
                "model(s)"
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
                f"error: {e}"
            )


        except Exception as e:

            logger.warning(
                "[OpenRouter] Unexpected model "
                f"discovery error: {e}"
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
                f"~{remaining}s remaining."
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
        # ONE REQUEST PER MODEL
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
                            "[OpenRouter] "
                            f"{model} returned invalid "
                            f"JSON: {e}"
                        )

                        return None


                    choices = data.get(
                        "choices"
                    )


                    if not choices:

                        logger.warning(
                            "[OpenRouter] "
                            f"{model} returned no choices"
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
                        "[OpenRouter] "
                        f"{model} → HTTP "
                        f"{status} "
                        "(authentication/permission "
                        "error)"
                    )


                    if body:

                        logger.error(
                            "[OpenRouter] Server "
                            f"response: {body}"
                        )


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


                    if is_account_limit:

                        self._mark_account_rate_limited(
                            cooldown
                        )


                        logger.error(
                            "[OpenRouter] "
                            f"{model} → HTTP 429 "
                            "ACCOUNT/GLOBAL RATE LIMIT"
                        )


                    else:

                        self._mark_rate_limited(
                            model,
                            cooldown,
                        )


                        logger.warning(
                            "[OpenRouter] "
                            f"{model} → HTTP 429 "
                            "MODEL/PROVIDER RATE LIMIT"
                        )


                    return None


                # =================================================
                # MODEL UNAVAILABLE
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
                        "[OpenRouter] "
                        f"{model} → HTTP "
                        f"{status} "
                        "(model/request "
                        "unavailable)"
                    )


                    if body:

                        logger.debug(
                            "[OpenRouter] "
                            f"Response: {body}"
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
                        "[OpenRouter] "
                        f"{model} → HTTP "
                        f"{status} "
                        "(server error, "
                        f"attempt "
                        f"{attempt}/"
                        f"{MAX_RETRIES_PER_MODEL})"
                    )

                else:

                    logger.warning(
                        "[OpenRouter] "
                        f"{model} → HTTP "
                        f"{status} "
                        f"(attempt "
                        f"{attempt}/"
                        f"{MAX_RETRIES_PER_MODEL})"
                    )


            except requests.exceptions.Timeout:

                logger.warning(
                    "[OpenRouter] "
                    f"{model} → Timeout "
                    f"(attempt "
                    f"{attempt}/"
                    f"{MAX_RETRIES_PER_MODEL})"
                )


            except requests.exceptions.ConnectionError as e:

                logger.warning(
                    "[OpenRouter] "
                    f"{model} → Connection "
                    f"error: {e}"
                )


            except requests.exceptions.RequestException as e:

                logger.warning(
                    "[OpenRouter] "
                    f"{model} → Request "
                    f"error: {e}"
                )


            except RuntimeError:

                raise


            except Exception as e:

                logger.error(
                    "[OpenRouter] "
                    f"{model} → Unexpected "
                    f"error: {e}"
                )


            # ----------------------------------------------------
            # Retry only non-429 request failures.
            # ----------------------------------------------------

            if (
                attempt
                < MAX_RETRIES_PER_MODEL
            ):

                time.sleep(2)


        return None


    # ========================================================
    # THREE-STAGE ROUTER
    # ========================================================

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

        # ----------------------------------------------------
        # ACCOUNT LIMIT
        # ----------------------------------------------------

        if self._account_rate_limit_active():

            remaining = (
                self._account_rate_limit_remaining()
            )


            raise RuntimeError(
                "[OpenRouter] OpenRouter account "
                "is rate-limited. "
                f"Retry in approximately "
                f"{remaining}s."
            )


        # ====================================================
        # BUILD MODEL LIST
        # ====================================================

        candidates: list[str] = []


        # ----------------------------------------------------
        # Explicit requested model.
        # ----------------------------------------------------

        if model:

            if model == FREE_ROUTER_MODEL:

                candidates.append(
                    FREE_ROUTER_MODEL
                )

            else:

                discovered = (
                    self._discover_free_models(
                        vision=vision
                    )
                )


                if model not in discovered:

                    raise RuntimeError(
                        "[OpenRouter] Requested model "
                        f"'{model}' is not confirmed "
                        "as a free model."
                    )


                candidates.append(
                    model
                )


        else:

            # =================================================
            # STAGE 1
            # =================================================

            candidates.append(
                FREE_ROUTER_MODEL
            )


            # =================================================
            # STAGE 2 + STAGE 3
            # =================================================

            discovered = (
                self._discover_free_models(
                    vision=vision
                )
            )


            for discovered_model in discovered:

                if discovered_model in candidates:
                    continue


                candidates.append(
                    discovered_model
                )


                if len(candidates) >= MAX_STAGE_MODELS:
                    break


        # ----------------------------------------------------
        # Remove duplicates.
        # ----------------------------------------------------

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


        # ====================================================
        # EXECUTE STAGES
        # ====================================================

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


                raise RuntimeError(
                    "[OpenRouter] OpenRouter account "
                    "is rate-limited. "
                    f"Retry in approximately "
                    f"{remaining}s."
                )


            # ------------------------------------------------
            # MODEL COOLDOWN
            # ------------------------------------------------

            if self._is_rate_limited(
                target_model
            ):

                logger.warning(
                    "[OpenRouter] Stage "
                    f"{index}/{len(candidates)} "
                    f"→ Skipping rate-limited model: "
                    f"{target_model}"
                )

                continue


            # ------------------------------------------------
            # FAILED MODEL
            # ------------------------------------------------

            if self._is_failed_model(
                target_model
            ):

                logger.warning(
                    "[OpenRouter] Stage "
                    f"{index}/{len(candidates)} "
                    f"→ Skipping failed model: "
                    f"{target_model}"
                )

                continue


            # ------------------------------------------------
            # STAGE LOG
            # ------------------------------------------------

            logger.info(
                "[OpenRouter] Stage "
                f"{index}/{len(candidates)} "
                f"→ Trying: "
                f"{target_model}"
            )


            # ------------------------------------------------
            # CALL
            # ------------------------------------------------

            result = self._call(
                target_model,
                messages,
                max_tokens,
                temperature,
                response_format,
            )


            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

            if result:

                logger.info(
                    "[OpenRouter] ✓ Stage "
                    f"{index} SUCCESS: "
                    f"{target_model}"
                )


                return result


            # ------------------------------------------------
            # ACCOUNT LIMIT
            # ------------------------------------------------

            if self._account_rate_limit_active():

                remaining = (
                    self._account_rate_limit_remaining()
                )


                raise RuntimeError(
                    "[OpenRouter] OpenRouter account "
                    "rate limit reached. "
                    f"Retry in approximately "
                    f"{remaining}s."
                )


            # ------------------------------------------------
            # MODEL FAILURE
            # ------------------------------------------------

            if self._is_rate_limited(
                target_model
            ):

                logger.warning(
                    "[OpenRouter] Stage "
                    f"{index} failed due to model "
                    "rate limit."
                )

                last_error = (
                    f"{target_model} rate limited"
                )

                continue


            if self._is_failed_model(
                target_model
            ):

                logger.warning(
                    "[OpenRouter] Stage "
                    f"{index} model unavailable."
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

        raise RuntimeError(
            "[OpenRouter] All free inference "
            "stages failed. "
            f"Last error: {last_error or 'unknown'}"
        )


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


        return self._call_with_fallback(
            pool=[],
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )


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


        except RuntimeError as first_error:

            # ------------------------------------------------
            # Never perform the second JSON request when
            # account-level rate limit is active.
            # ------------------------------------------------

            if self._account_rate_limit_active():

                raise first_error


            logger.warning(
                "[OpenRouter] Structured JSON "
                "request failed. Retrying "
                "without response_format: "
                f"{first_error}"
            )


            raw = self._call_with_fallback(
                pool=[],
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=0.1,
                response_format=None,
            )


        return self._parse_json_response(
            raw
        )


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
            f"Raw response: {clean[:500]}"
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

        path = Path(
            image_path
        )


        if not path.exists():

            raise FileNotFoundError(
                f"Image not found: {path}"
            )


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

        return self._call_with_fallback(
            pool=[],
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )


    # ========================================================
    # MODEL INFORMATION
    # ========================================================

    def available_models(
        self,
    ) -> dict:

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

client = OpenRouterClient()


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

        reply = client.chat(
            "Introduce yourself in one short sentence."
        )


        print(
            f"  Response       : {reply}"
        )


        print(
            "  Status         : PASS ✓"
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


        print(
            "  Status         : PASS ✓"
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


        print(
            "  Status         : PASS ✓"
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
                "  Status         : FAIL ✗"
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