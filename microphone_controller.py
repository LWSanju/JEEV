# microphone_controller.py

import queue
import threading
import time
import sys
import os
import re

import numpy as np
import sounddevice as sd


# ============================================================
# JEEV MICROPHONE CONTROLLER
# ============================================================
#
# CONFIRMED WORKING WINDOWS ENDPOINT:
#
# Device 17
# Microphone (Realtek HD Audio Mic input)
# Windows WDM-KS
# 44100 Hz
# 2 input channels
#
# Pipeline:
#
#   Device 17
#       ↓
#   44100 Hz PCM16
#       ↓
#   mono
#       ↓
#   resample
#       ↓
#   16000 Hz PCM16
#       ↓
#   Gemini Live
#
# ============================================================


class JeevMicrophone:

    # ========================================================
    # CONFIRMED HARDWARE
    # ========================================================

    DEVICE = None

    HARDWARE_SAMPLE_RATE = 44100

    GEMINI_SAMPLE_RATE = 16000

    CHANNELS = 1

    DTYPE = "int16"

    BLOCKSIZE = 512

    QUEUE_SIZE = 200

    # ========================================================
    # INITIALIZATION
    # ========================================================

    def __init__(self, device=None):

        # None means AUTO.  We deliberately do not trust a stale numeric
        # PortAudio index because Windows reorders devices when USB/Bluetooth
        # endpoints are connected or removed.
        self.requested_device = device
        self.device = device

        # Actual rate/channel configuration is selected at runtime because
        # Windows WDM-KS endpoints can expose a default rate that is not
        # openable by PortAudio at every moment. Gemini still receives 16 kHz.
        self.hardware_sample_rate = self.HARDWARE_SAMPLE_RATE
        self.capture_channels = self.CHANNELS

        self.audio_queue = queue.Queue(
            maxsize=self.QUEUE_SIZE
        )

        self.stream = None

        self.running = False

        self.callback_count = 0
        self.total_samples = 0

        self.last_peak = 0
        self.last_rms = 0.0

        self.lock = threading.Lock()

    # ========================================================
    # UNIVERSAL WINDOWS INPUT RESOLUTION
    # ========================================================

    @staticmethod
    def _hostapi_name(index):
        try:
            return str(sd.query_hostapis(index).get("name", ""))
        except Exception:
            return ""

    @staticmethod
    def _norm_name(value):
        text = str(value or "").lower()
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return set(text.split())

    def _rank_input_device(self, index, info, default_index, default_name):
        """Rank real microphone endpoints; never prefer a stale MME duplicate."""
        name = str(info.get("name", ""))
        host = self._hostapi_name(info.get("hostapi"))
        low = name.lower()
        host_low = host.lower()
        score = 0

        # Real Windows capture backends first.
        if "wdm-ks" in host_low:
            score += 500
        elif "wasapi" in host_low:
            score += 350
        elif "directsound" in host_low:
            score += 180
        elif "mme" in host_low:
            score += 40

        # Real microphone names.
        if "microphone" in low:
            score += 160
        elif re.search(r"\bmic\b", low):
            score += 150
        elif "hands-free" in low or "handsfree" in low:
            score += 130
        elif "headset" in low:
            score += 120
        elif any(x in low for x in ("airpods", "airbuds", "earbuds")):
            score += 100

        # Never let non-microphone capture endpoints outrank a real mic.
        if any(x in low for x in (
            "stereo mix", "pc speaker", "line in", "line input",
            "what u hear", "waveout", "loopback", "sound mapper"
        )):
            score -= 500

        # Windows default is useful, but cannot beat a native microphone backend.
        if index == default_index:
            score += 25

        overlap = self._norm_name(name) & self._norm_name(default_name)
        score += min(30, 6 * len(overlap))

        return score


    def _input_candidates(self):
        try:
            devices = sd.query_devices()
        except Exception as exc:
            print(f"[MIC] Could not enumerate audio devices: {exc}")
            return []

        try:
            default_index = int(sd.default.device[0])
        except Exception:
            default_index = -1

        try:
            default_name = str(sd.query_devices(default_index).get("name", ""))
        except Exception:
            default_name = ""

        candidates = []
        for index, info in enumerate(devices):
            try:
                if int(info.get("max_input_channels", 0)) <= 0:
                    continue
            except Exception:
                continue
            score = self._rank_input_device(index, info, default_index, default_name)
            candidates.append((score, index, info))

        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return candidates

    def _resolve_device(self):
        # Explicit numeric override remains available for deliberate debugging.
        if self.requested_device is not None:
            try:
                index = int(self.requested_device)
                info = sd.query_devices(index)
                if int(info.get("max_input_channels", 0)) > 0:
                    self.device = index
                    return [(9999, index, info)]
            except Exception as exc:
                print(
                    f"[MIC] Requested input device {self.requested_device} "
                    f"is unavailable: {exc}"
                )

        candidates = self._input_candidates()
        if candidates:
            self.device = candidates[0][1]
            print(
                f"[MIC] Auto-selected microphone: Device {self.device} | "
                f"{candidates[0][2].get('name')} | "
                f"{self._hostapi_name(candidates[0][2].get('hostapi'))}"
            )
        return candidates

    # ========================================================
    # DEVICE INFO
    # ========================================================

    def _get_device_info(self):

        try:

            return sd.query_devices(
                self.device
            )

        except Exception as e:

            print(
                f"[MIC] Failed to query device "
                f"{self.device}: {e}"
            )

            return None

    # ========================================================
    # PRINT DEVICE
    # ========================================================

    def print_device(self):

        info = self._get_device_info()

        if info is None:

            return None

        print()
        print("=" * 60)
        print("JEEV MICROPHONE")
        print("=" * 60)

        print(
            f"Resolved device index: {self.device}"
        )

        print(
            f"Name:                 "
            f"{info.get('name')}"
        )

        try:

            hostapi_index = info.get(
                "hostapi"
            )

            hostapi = sd.query_hostapis(
                hostapi_index
            )

            print(
                f"Host API:             "
                f"{hostapi.get('name')}"
            )

        except Exception:
            pass

        print(
            f"Input channels:       "
            f"{info.get('max_input_channels')}"
        )

        print(
            f"Default samplerate:   "
            f"{info.get('default_samplerate')}"
        )

        print("=" * 60)
        print()

        return info

    # ========================================================
    # CALLBACK
    # ========================================================

    def _callback(
        self,
        indata,
        frames,
        time_info,
        status
    ):

        if status:

            print(
                f"[MIC] PortAudio status: "
                f"{status}"
            )

        if not self.running:

            return

        try:

            # sounddevice gives us int16 directly.
            arr = np.asarray(
                indata,
                dtype=np.int16
            )

            if arr.size == 0:

                return

            # ------------------------------------------------
            # CONVERT TO MONO
            # ------------------------------------------------
            #
            # The physical device exposes two channels.
            #
            # We capture channel 0 first.
            #
            # If channel 0 is silent while channel 1 contains
            # the microphone, the diagnostic below will reveal
            # that. For now device 17's channel 0 is working.
            #

            if arr.ndim > 1 and arr.shape[1] > 1:
                # Do not assume channel 0 is the physical microphone.
                # Windows drivers sometimes expose the active mic on channel 1.
                energies = np.mean(arr.astype(np.float32) ** 2, axis=0)
                best_channel = int(np.argmax(energies))
                samples = arr[:, best_channel].copy()
            else:
                samples = arr.reshape(-1).copy()

            if samples.size == 0:

                return

            # ------------------------------------------------
            # AUDIO METRICS
            # ------------------------------------------------

            samples_float = samples.astype(
                np.float32
            )

            peak = int(
                np.max(
                    np.abs(samples_float)
                )
            )

            rms = float(
                np.sqrt(
                    np.mean(
                        samples_float *
                        samples_float
                    )
                )
            )

            with self.lock:

                self.callback_count += 1

                self.total_samples += (
                    samples.size
                )

                self.last_peak = peak

                self.last_rms = rms

            # ------------------------------------------------
            # QUEUE
            # ------------------------------------------------

            try:

                self.audio_queue.put_nowait(
                    samples
                )

            except queue.Full:

                # Never block PortAudio.
                try:

                    self.audio_queue.get_nowait()

                except queue.Empty:

                    pass

                try:

                    self.audio_queue.put_nowait(
                        samples
                    )

                except queue.Full:

                    pass

        except Exception as e:

            print(
                f"[MIC] Callback error: {e}"
            )

    # ========================================================
    # START
    # ========================================================

    def start(self):

        if self.running:

            print(
                "[MIC] Already running."
            )

            return True

        # ----------------------------------------------------
        # DEVICE / AUTO RESOLUTION
        # ----------------------------------------------------

        candidates = self._resolve_device()
        if not candidates:
            print("[MIC] No usable Windows input device was found.")
            return False

        # Try candidates in rank order. This is important when the Windows
        # default endpoint is a stale MME/WASAPI duplicate: JEEV will fall
        # through to the working WDM-KS endpoint automatically.
        last_failures = []

        for _, candidate_index, candidate_info in candidates:
            self.device = candidate_index
            info = self.print_device()
            if info is None:
                continue

            # ----------------------------------------------------
            # VALIDATE INPUT
            # ----------------------------------------------------

            input_channels = int(info.get("max_input_channels", 0))
            if input_channels <= 0:
                continue

            # ----------------------------------------------------
            # CLEAR QUEUE / RESET METRICS
            # ----------------------------------------------------
            while True:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    break

            with self.lock:
                self.callback_count = 0
                self.total_samples = 0
                self.last_peak = 0
                self.last_rms = 0.0

            # ----------------------------------------------------
            # SELECT A REAL PORTAUDIO CONFIGURATION
            # ----------------------------------------------------
            try:
                default_rate = float(info.get("default_samplerate") or 0)
            except Exception:
                default_rate = 0.0

            max_channels = input_channels
            rate_candidates = []
            for rate in (default_rate, 44100, 48000, 32000, 16000, 8000):
                if rate > 0 and int(round(rate)) not in rate_candidates:
                    rate_candidates.append(int(round(rate)))

            channel_candidates = []
            for channels in (self.CHANNELS, 2, max_channels, 1):
                if 0 < channels <= max_channels and channels not in channel_candidates:
                    channel_candidates.append(channels)

            selected_rate = None
            selected_channels = None

            for rate in rate_candidates:
                for channels in channel_candidates:
                    test_stream = None
                    try:
                        try:
                            sd.check_input_settings(
                                device=self.device,
                                samplerate=rate,
                                channels=channels,
                                dtype=self.DTYPE,
                            )
                        except Exception as exc:
                            last_failures.append(f"{self.device}: {rate}Hz/{channels}ch check: {exc}")
                            continue

                        test_stream = sd.InputStream(
                            device=self.device,
                            samplerate=rate,
                            channels=channels,
                            dtype=self.DTYPE,
                            blocksize=self.BLOCKSIZE,
                            callback=self._callback,
                        )
                        test_stream.start()
                        selected_rate = rate
                        selected_channels = channels
                        self.stream = test_stream
                        test_stream = None
                        print(f"[MIC] Selected REAL input: {rate} Hz, {channels} channel(s)")
                        break
                    except Exception as exc:
                        last_failures.append(f"{self.device}: {rate}Hz/{channels}ch open: {exc}")
                        if test_stream is not None:
                            try: test_stream.stop()
                            except Exception: pass
                            try: test_stream.close()
                            except Exception: pass
                if selected_rate is not None:
                    break

            if selected_rate is None or self.stream is None:
                self.stream = None
                continue

            self.hardware_sample_rate = selected_rate
            self.capture_channels = selected_channels
            self.running = True

            print(
                f"[MIC] Using hardware input: {selected_rate} Hz, "
                f"{selected_channels} channel(s)"
            )

            print()
            print("=" * 60)
            print(" JEEV MICROPHONE STARTED")
            print("=" * 60)
            print(f"Device:        {self.device}")
            print(f"Backend:       {self._hostapi_name(info.get('hostapi'))}")
            print(f"Hardware rate: {self.hardware_sample_rate} Hz")
            print(f"Gemini rate:   {self.GEMINI_SAMPLE_RATE} Hz")
            print(f"Channels:      {self.CHANNELS}")
            print(f"Blocksize:     {self.BLOCKSIZE}")
            print("=" * 60)
            print()
            return True

        print("[MIC] No PortAudio input configuration could actually be opened.")
        for failure in last_failures[:12]:
            print(f"[MIC]   {failure}")
        return False

    # ========================================================
    # RESAMPLE HARDWARE RATE -> 16000
    # ========================================================

    def _resample_to_16000(self, audio):

        if audio is None:

            return b""

        arr = np.asarray(
            audio,
            dtype=np.float32
        )

        if arr.size == 0:

            return b""

        old_len = arr.size

        new_len = int(
            round(
                old_len *
                self.GEMINI_SAMPLE_RATE /
                self.hardware_sample_rate
            )
        )

        if new_len <= 0:

            return b""

        # ----------------------------------------------------
        # Linear interpolation.
        #
        # This happens OUTSIDE the PortAudio callback,
        # therefore it doesn't interfere with the audio
        # driver.
        # ----------------------------------------------------

        old_positions = np.arange(
            old_len,
            dtype=np.float64
        )

        new_positions = np.linspace(
            0,
            old_len - 1,
            new_len,
            dtype=np.float64
        )

        resampled = np.interp(
            new_positions,
            old_positions,
            arr
        )

        resampled = np.clip(
            resampled,
            -32768,
            32767
        )

        return np.asarray(
            resampled,
            dtype=np.int16
        ).tobytes()

    # ========================================================
    # READ
    # ========================================================

    def read(self, timeout=0.1):

        if not self.running:

            return None

        try:

            audio = self.audio_queue.get(
                timeout=timeout
            )

        except queue.Empty:

            return None

        try:

            return self._resample_to_16000(
                audio
            )

        except Exception as e:

            print(
                f"[MIC] Resampling error: {e}"
            )

            return None

    # ========================================================
    # BLOCKING READ
    # ========================================================

    def read_blocking(self):

        while self.running:

            data = self.read(
                timeout=0.5
            )

            if data:

                return data

        return None

    # ========================================================
    # STATUS
    # ========================================================

    def get_status(self):

        with self.lock:

            return {

                "running":
                    self.running,

                "device":
                    self.device,

                "callbacks":
                    self.callback_count,

                "samples":
                    self.total_samples,

                "peak":
                    self.last_peak,

                "rms":
                    self.last_rms,

            }

    # ========================================================
    # STOP
    # ========================================================

    def stop(self):

        if not self.running:

            return

        print(
            "[MIC] Stopping microphone..."
        )

        self.running = False

        try:

            if self.stream is not None:

                try:

                    self.stream.stop()

                except Exception:

                    pass

                try:

                    self.stream.close()

                except Exception:

                    pass

                self.stream = None

        except Exception:

            pass

        # ----------------------------------------------------
        # CLEAR QUEUE
        # ----------------------------------------------------

        while True:

            try:

                self.audio_queue.get_nowait()

            except queue.Empty:

                break

        print(
            "[MIC] Microphone stopped"
        )

    # ========================================================
    # CONTEXT MANAGER
    # ========================================================

    def __enter__(self):

        if not self.start():

            raise RuntimeError(
                "JEEV microphone could not be started"
            )

        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        tb
    ):

        self.stop()


# ============================================================
# STANDALONE TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 60)
    print(" JEEV MICROPHONE CONTROLLER TEST")
    print("=" * 60)
    print()

    mic = JeevMicrophone()

    if not mic.start():

        print(
            "[MIC] TEST FAILED TO START"
        )

        sys.exit(1)

    try:

        print(
            "Speak normally/loudly for 10 seconds..."
        )

        print()

        start = time.time()

        blocks = 0

        bytes_received = 0

        while time.time() - start < 10:

            data = mic.read(
                timeout=0.5
            )

            if data:

                blocks += 1

                bytes_received += len(
                    data
                )

            status = mic.get_status()

            print(
                "\r"
                f"Device: {status['device']} | "
                f"Callbacks: {status['callbacks']} | "
                f"Peak: {status['peak']} | "
                f"RMS: {status['rms']:.1f} | "
                f"16k bytes: {bytes_received}",
                end="",
                flush=True
            )

        print()
        print()

        print("=" * 60)
        print(" TEST COMPLETE")
        print("=" * 60)

        status = mic.get_status()

        print(
            f"Device:        {status['device']}"
        )

        print(
            f"Callbacks:     {status['callbacks']}"
        )

        print(
            f"Latest peak:   {status['peak']}"
        )

        print(
            f"Latest RMS:    {status['rms']:.1f}"
        )

        print(
            f"Gemini blocks: {blocks}"
        )

        print(
            f"16k bytes:     {bytes_received}"
        )

        if (
            status["peak"] > 100
            and status["rms"] > 5
        ):

            print()
            print(
                "RESULT: MICROPHONE AUDIO DETECTED"
            )

        else:

            print()
            print(
                "RESULT: MICROPHONE AUDIO NOT DETECTED"
            )

    finally:

        mic.stop()