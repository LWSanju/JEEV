"""
JEEV MARK I — Speech Performance Layer

This module adds restrained human-like vocal performance to Gemini Live PCM
without putting the logic into main.py.

It does NOT:
- call Gemini
- change prompts
- execute tools
- change tool arguments
- touch the microphone
- control Windows
- change what JEEV says

It only receives Gemini's already-generated 24 kHz mono PCM and can insert
very short, low-level vocal-performance cues before playback.

The cues are intentionally subtle and heavily rate-limited.
"""

from __future__ import annotations

import math
import random
import re
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpeechPerformanceConfig:
    enabled: bool = True

    # Human-performance intensity.
    intensity: float = 0.55

    # Long-speech breathing.
    breathing: bool = True
    breath_after_seconds: float = 8.0
    breath_probability: float = 0.28
    breath_duration_ms: int = 115

    # Tongue-twister / difficult-phrase reaction.
    tongue_twister_reaction: bool = True
    tongue_twister_probability: float = 0.20
    throat_clear_duration_ms: int = 85

    # Occasional cough. Deliberately rare.
    cough: bool = True
    cough_probability: float = 0.035
    cough_min_gap_seconds: float = 45.0

    # Small hesitation / exhale behavior.
    hesitation: bool = True
    hesitation_probability: float = 0.10
    hesitation_duration_ms: int = 42

    # Global safety limits.
    minimum_cue_gap_seconds: float = 2.2
    random_seed: int | None = None


class SpeechPerformanceEngine:
    """
    Stateful speech-performance controller.

    Main integration points:
        observe_text(text)
        process_pcm24(pcm_bytes)
        begin_turn()
        end_turn()
        interrupt()

    process_pcm24() always returns valid 24 kHz mono PCM16 bytes.
    """

    _TWISTER_PATTERNS = (
        r"\b(?:sixths?|twelfths?|months?|crisps?|scripts?|strengths?)\b",
        r"\b(?:statistics|specifically|particularly|proprietary|"
        r"configuration|configurations|characteristically)\b",
        r"\b(?:regularly|literally|reliably|responsibility|"
        r"refrigerator|rural|jurisdiction)\b",
        r"\b(?:three|thirty|thirteen|thousand)\b",
        r"\b(?:artificial intelligence|speech recognition|"
        r"parallel processing|specific specification)\b",
    )

    _COMPLEX_WORD_RE = re.compile(
        r"\b[a-z]{11,}\b",
        re.IGNORECASE,
    )

    _REPEATED_CLUSTER_RE = re.compile(
        r"\b(?:[bcdfghjklmnpqrstvwxyz]{3,}[aeiou]?){2,}\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        config: SpeechPerformanceConfig | None = None,
    ):
        self.config = config or SpeechPerformanceConfig()

        seed = self.config.random_seed
        self._rng = random.Random(seed)

        self._lock = threading.RLock()

        self._turn_started_at = 0.0
        self._last_cue_at = 0.0
        self._last_cough_at = 0.0

        self._pending_throat_clear = False
        self._pending_cough = False
        self._pending_hesitation = False
        self._pending_breath = False

        self._recent_text = deque(maxlen=8)

        self._turn_had_long_text = False
        self._last_text_observed_at = 0.0

    # ------------------------------------------------------------------
    # PUBLIC STATE API
    # ------------------------------------------------------------------

    def begin_turn(self) -> None:
        with self._lock:
            self._turn_started_at = time.monotonic()
            self._turn_had_long_text = False
            self._pending_throat_clear = False
            self._pending_cough = False
            self._pending_hesitation = False
            self._pending_breath = False
            self._recent_text.clear()

    def end_turn(self) -> None:
        with self._lock:
            self._turn_started_at = 0.0
            self._pending_breath = False
            self._pending_hesitation = False
            self._pending_throat_clear = False
            self._pending_cough = False

    def interrupt(self) -> None:
        self.end_turn()

    def observe_text(self, text: str) -> None:
        """
        Feed Gemini's output transcription here.

        The text is used only to decide whether a tiny vocal reaction is
        appropriate. It never modifies the spoken words.
        """
        text = str(text or "").strip()
        if not text:
            return

        now = time.monotonic()

        with self._lock:
            if self._turn_started_at <= 0.0:
                self._turn_started_at = now

            self._recent_text.append(text)
            self._last_text_observed_at = now

            joined = " ".join(self._recent_text)
            word_count = len(re.findall(r"\b[\w'-]+\b", joined))

            if word_count >= 90:
                self._turn_had_long_text = True

            if (
                self.config.tongue_twister_reaction
                and self._looks_tongue_twisty(text)
                and self._can_cue(now)
                and self._rng.random()
                < self.config.tongue_twister_probability
            ):
                self._pending_throat_clear = True
                return

            # Very long responses can earn a restrained breath/cough,
            # but the cough remains independently rare.
            if (
                self.config.cough
                and self._turn_had_long_text
                and now - self._last_cough_at
                >= self.config.cough_min_gap_seconds
                and self._rng.random()
                < self.config.cough_probability
            ):
                self._pending_cough = True

    def process_pcm24(self, pcm_bytes: bytes) -> bytes:
        """
        Process one Gemini 24 kHz mono PCM16 chunk.

        Returns PCM16 mono at the same 24 kHz rate.
        """
        if not pcm_bytes:
            return pcm_bytes

        cfg = self.config
        if not cfg.enabled or cfg.intensity <= 0.0:
            return pcm_bytes

        try:
            samples = np.frombuffer(
                bytes(pcm_bytes),
                dtype=np.int16,
            ).copy()
        except Exception:
            return pcm_bytes

        if samples.size == 0:
            return pcm_bytes

        now = time.monotonic()

        with self._lock:
            if self._turn_started_at <= 0.0:
                self._turn_started_at = now

            cue = self._select_cue(now)

        if cue is None:
            return samples.astype(np.int16, copy=False).tobytes()

        try:
            effect = self._make_effect(cue)

            # A tiny natural pause before a performance cue.
            if cue == "hesitation":
                pause = self._silence(
                    int(
                        24000
                        * self._scaled_ms(cfg.hesitation_duration_ms)
                        / 1000.0
                    )
                )
                result = np.concatenate((pause, samples, effect))
            else:
                result = np.concatenate((effect, samples))

            # Keep the level conservative so the cue never jumps above JEEV's
            # normal voice output.
            peak = np.max(np.abs(result)) if result.size else 0
            if peak > 32000:
                result = result * (32000.0 / float(peak))

            return np.asarray(
                np.clip(result, -32768, 32767),
                dtype=np.int16,
            ).tobytes()

        except Exception:
            # Audio safety rule: if the effect ever fails, never break JEEV
            # playback. Return the original Gemini audio.
            return pcm_bytes

    # ------------------------------------------------------------------
    # CUE SELECTION
    # ------------------------------------------------------------------

    def _select_cue(self, now: float) -> str | None:
        cfg = self.config

        if not self._can_cue(now):
            return None

        # Explicitly requested reactions get priority.
        if self._pending_throat_clear:
            self._pending_throat_clear = False
            self._last_cue_at = now
            return "throat_clear"

        if self._pending_cough:
            self._pending_cough = False
            self._last_cough_at = now
            self._last_cue_at = now
            return "cough"

        elapsed = now - self._turn_started_at

        if (
            cfg.breathing
            and elapsed >= cfg.breath_after_seconds
            and self._rng.random()
            < cfg.breath_probability * cfg.intensity
        ):
            self._pending_breath = False
            self._last_cue_at = now
            return "breath"

        if (
            cfg.hesitation
            and self._rng.random()
            < cfg.hesitation_probability
            * cfg.intensity
            * 0.20
        ):
            self._last_cue_at = now
            return "hesitation"

        return None

    def _can_cue(self, now: float) -> bool:
        return (
            now - self._last_cue_at
            >= self.config.minimum_cue_gap_seconds
        )

    def _looks_tongue_twisty(self, text: str) -> bool:
        lowered = text.casefold()

        for pattern in self._TWISTER_PATTERNS:
            if re.search(pattern, lowered):
                return True

        long_words = self._COMPLEX_WORD_RE.findall(lowered)
        if len(long_words) >= 2:
            return True

        if self._REPEATED_CLUSTER_RE.search(lowered):
            return True

        # Dense consonant-heavy phrases are more likely to trip speech.
        words = re.findall(r"[a-z]+", lowered)
        if words:
            difficult = 0
            for word in words:
                if len(word) >= 7:
                    consonants = sum(
                        1 for c in word
                        if c in "bcdfghjklmnpqrstvwxyz"
                    )
                    if consonants / max(len(word), 1) >= 0.58:
                        difficult += 1
            if difficult >= 2:
                return True

        return False

    # ------------------------------------------------------------------
    # EFFECT SYNTHESIS
    # ------------------------------------------------------------------

    def _scaled_ms(self, milliseconds: int) -> float:
        return max(
            20.0,
            milliseconds
            * (0.78 + 0.42 * self.config.intensity),
        )

    def _make_effect(self, cue: str) -> np.ndarray:
        if cue == "breath":
            return self._make_breath()

        if cue == "throat_clear":
            return self._make_throat_clear()

        if cue == "cough":
            return self._make_cough()

        if cue == "hesitation":
            return self._make_exhale()

        return np.zeros(0, dtype=np.int16)

    def _make_breath(self) -> np.ndarray:
        """
        Soft broadband breath: noise shaped by a smooth inhale/exhale envelope.
        It is intentionally quieter than normal speech.
        """
        n = max(
            1,
            int(
                24000
                * self._scaled_ms(
                    self.config.breath_duration_ms
                )
                / 1000.0
            ),
        )

        noise = self._smooth_noise(n)
        t = np.linspace(0.0, 1.0, n, endpoint=False)

        # Slightly stronger at the middle, fading smoothly at both ends.
        envelope = np.sin(np.pi * t) ** 1.25
        envelope *= 0.055 + 0.035 * self.config.intensity

        # Very low-frequency body plus airy component.
        low = np.sin(
            2.0
            * math.pi
            * self._rng.uniform(75.0, 115.0)
            * np.arange(n)
            / 24000.0
        )
        signal = noise * envelope + low * envelope * 0.025

        return self._to_pcm16(signal)

    def _make_exhale(self) -> np.ndarray:
        n = max(
            1,
            int(
                24000
                * self._scaled_ms(75)
                / 1000.0
            ),
        )

        noise = self._smooth_noise(n)
        t = np.linspace(0.0, 1.0, n, endpoint=False)
        envelope = np.sin(np.pi * t) ** 1.5
        signal = noise * envelope * 0.045
        return self._to_pcm16(signal)

    def _make_throat_clear(self) -> np.ndarray:
        n = max(
            1,
            int(
                24000
                * self._scaled_ms(
                    self.config.throat_clear_duration_ms
                )
                / 1000.0
            ),
        )

        noise = self._smooth_noise(n)
        t = np.linspace(0.0, 1.0, n, endpoint=False)

        # Two compact bursts give a subtle "ahem" impression without
        # synthesizing a cartoonish cough.
        burst1 = np.exp(-((t - 0.28) / 0.16) ** 2)
        burst2 = np.exp(-((t - 0.63) / 0.14) ** 2)
        envelope = 0.65 * burst1 + 0.42 * burst2

        low = np.sin(
            2.0
            * math.pi
            * self._rng.uniform(105.0, 145.0)
            * np.arange(n)
            / 24000.0
        )

        signal = (
            noise * envelope * (0.075 * self.config.intensity + 0.035)
            + low * envelope * 0.035
        )

        return self._to_pcm16(signal)

    def _make_cough(self) -> np.ndarray:
        """
        Rare, quiet two-pulse cough-like transient.
        """
        n = max(
            1,
            int(
                24000
                * self._scaled_ms(105)
                / 1000.0
            ),
        )

        noise = self._smooth_noise(n)
        t = np.linspace(0.0, 1.0, n, endpoint=False)

        pulse1 = np.exp(-((t - 0.22) / 0.095) ** 2)
        pulse2 = np.exp(-((t - 0.57) / 0.12) ** 2)

        envelope = 0.85 * pulse1 + 0.55 * pulse2
        signal = noise * envelope * (
            0.09 + 0.045 * self.config.intensity
        )

        return self._to_pcm16(signal)

    # ------------------------------------------------------------------
    # DSP HELPERS
    # ------------------------------------------------------------------

    def _smooth_noise(self, n: int) -> np.ndarray:
        raw = np.asarray(
            [
                self._rng.uniform(-1.0, 1.0)
                for _ in range(n)
            ],
            dtype=np.float32,
        )

        # Cheap smoothing/filtering suitable for a tiny speech cue.
        if n >= 5:
            kernel = np.ones(5, dtype=np.float32) / 5.0
            raw = np.convolve(raw, kernel, mode="same")

        peak = float(np.max(np.abs(raw))) if raw.size else 1.0
        if peak > 0:
            raw /= peak

        return raw

    @staticmethod
    def _to_pcm16(signal: np.ndarray) -> np.ndarray:
        signal = np.asarray(signal, dtype=np.float32)
        signal = np.clip(signal, -1.0, 1.0)
        return np.asarray(
            signal * 32767.0,
            dtype=np.int16,
        )
