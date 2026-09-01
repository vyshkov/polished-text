import atexit
import ctypes
from ctypes import Structure, byref, c_uint32, c_void_p, create_string_buffer
import os
import shutil
import signal
import struct
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .config import MIC_LEVEL_SCALE, MIN_SPEECH_DURATION, SILENCE_RMS_THRESHOLD
from .logger import get_logger
from .sound import play_sound

logger = get_logger("Audio")


def _find_binary(name: str) -> Optional[str]:
    """Find binary executable with fallback to standard Homebrew/macOS locations."""
    found = shutil.which(name)
    if found:
        return found
    common_locations = [
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
        f"/opt/homebrew/sbin/{name}",
        f"/usr/bin/{name}",
    ]
    for loc in common_locations:
        if os.path.exists(loc) and os.access(loc, os.X_OK):
            return loc
    return None


# ---------------------------------------------------------------------------
# CoreAudio Device Utilities (macOS)
# ---------------------------------------------------------------------------

class _AudioObjectPropertyAddress(Structure):
    _fields_ = [
        ("mSelector", c_uint32),
        ("mScope", c_uint32),
        ("mElement", c_uint32),
    ]


def _fourcc(s: str) -> int:
    return int.from_bytes(s.encode("ascii"), "big")


_kAudioHardwarePropertyDevices = _fourcc("dev#")
_kAudioHardwarePropertyDefaultInputDevice = _fourcc("dIn ")
_kAudioObjectPropertyScopeGlobal = _fourcc("glob")
_kAudioObjectPropertyScopeInput = _fourcc("inpt")
_kAudioObjectPropertyElementMain = 0
_kAudioObjectSystemObject = 1
_kAudioDevicePropertyDeviceNameCFString = _fourcc("lnam")
_kAudioDevicePropertyStreams = _fourcc("stm#")


def _get_coreaudio_libs():
    try:
        core_audio = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        core_foundation = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        return core_audio, core_foundation
    except Exception:
        return None, None


def get_default_input_device_name() -> str:
    """Return the name of macOS's current Default Input Device."""
    core_audio, core_foundation = _get_coreaudio_libs()
    if not core_audio or not core_foundation:
        return "Default Microphone"

    try:
        address = _AudioObjectPropertyAddress(
            _kAudioHardwarePropertyDefaultInputDevice,
            _kAudioObjectPropertyScopeGlobal,
            _kAudioObjectPropertyElementMain,
        )
        dev_id = c_uint32()
        size = c_uint32(ctypes.sizeof(dev_id))
        status = core_audio.AudioObjectGetPropertyData(
            _kAudioObjectSystemObject, byref(address), 0, None, byref(size), byref(dev_id)
        )
        if status != 0:
            return "Default Microphone"

        name_addr = _AudioObjectPropertyAddress(
            _kAudioDevicePropertyDeviceNameCFString,
            _kAudioObjectPropertyScopeGlobal,
            _kAudioObjectPropertyElementMain,
        )
        cfstr = c_void_p()
        size = c_uint32(ctypes.sizeof(cfstr))
        status = core_audio.AudioObjectGetPropertyData(
            dev_id.value, byref(name_addr), 0, None, byref(size), byref(cfstr)
        )
        if status != 0 or not cfstr.value:
            return "Default Microphone"

        core_foundation.CFStringGetLength.restype = ctypes.c_long
        length = core_foundation.CFStringGetLength(cfstr)
        max_size = core_foundation.CFStringGetMaximumSizeForEncoding(length, 0x08000100)  # UTF-8
        buffer = create_string_buffer(max_size + 1)
        core_foundation.CFStringGetCString(cfstr, buffer, max_size + 1, 0x08000100)
        core_foundation.CFRelease(cfstr)
        return buffer.value.decode("utf-8")
    except Exception:
        return "Default Microphone"


def get_audio_input_devices() -> List[Dict[str, any]]:
    """Return a list of available input audio devices on macOS."""
    core_audio, core_foundation = _get_coreaudio_libs()
    if not core_audio or not core_foundation:
        return []

    try:
        address = _AudioObjectPropertyAddress(
            _kAudioHardwarePropertyDevices,
            _kAudioObjectPropertyScopeGlobal,
            _kAudioObjectPropertyElementMain,
        )
        size = c_uint32()
        status = core_audio.AudioObjectGetPropertyDataSize(
            _kAudioObjectSystemObject, byref(address), 0, None, byref(size)
        )
        if status != 0:
            return []

        num_devices = size.value // ctypes.sizeof(c_uint32)
        dev_ids = (c_uint32 * num_devices)()
        core_audio.AudioObjectGetPropertyData(
            _kAudioObjectSystemObject, byref(address), 0, None, byref(size), byref(dev_ids)
        )

        def_name = get_default_input_device_name()
        devices = []
        seen = set()

        for d in dev_ids:
            st_addr = _AudioObjectPropertyAddress(
                _kAudioDevicePropertyStreams,
                _kAudioObjectPropertyScopeInput,
                _kAudioObjectPropertyElementMain,
            )
            st_size = c_uint32()
            if core_audio.AudioObjectGetPropertyDataSize(d, byref(st_addr), 0, None, byref(st_size)) == 0 and st_size.value > 0:
                name_addr = _AudioObjectPropertyAddress(
                    _kAudioDevicePropertyDeviceNameCFString,
                    _kAudioObjectPropertyScopeGlobal,
                    _kAudioObjectPropertyElementMain,
                )
                cfstr = c_void_p()
                c_size = c_uint32(ctypes.sizeof(cfstr))
                if core_audio.AudioObjectGetPropertyData(d, byref(name_addr), 0, None, byref(c_size), byref(cfstr)) == 0 and cfstr.value:
                    core_foundation.CFStringGetLength.restype = ctypes.c_long
                    length = core_foundation.CFStringGetLength(cfstr)
                    max_size = core_foundation.CFStringGetMaximumSizeForEncoding(length, 0x08000100)
                    buffer = create_string_buffer(max_size + 1)
                    core_foundation.CFStringGetCString(cfstr, buffer, max_size + 1, 0x08000100)
                    core_foundation.CFRelease(cfstr)
                    name = buffer.value.decode("utf-8")
                    if name and name not in seen:
                        seen.add(name)
                        devices.append({
                            "id": d,
                            "name": name,
                            "is_default": (name == def_name),
                        })
        return devices
    except Exception:
        return []


def kill_stale_recorder_processes():
    """Terminate any orphaned 'rec' or 'sox' processes from previous interrupted or crashed runs."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", "(rec|sox).*gemini_dictation_temp"],
            capture_output=True, text=True
        ).stdout.strip()
        if out:
            for pid_str in out.splitlines():
                try:
                    pid = int(pid_str.strip())
                    if pid != os.getpid():
                        os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
    except Exception:
        pass


def get_audio_stats(path: Path) -> dict:
    """Run 'sox <file> -n stat' and parse its stderr report into a dict of floats."""
    try:
        result = subprocess.run(
            ["sox", str(path), "-n", "stat"],
            capture_output=True, text=True, timeout=5
        )
    except Exception:
        return {}
    stats = {}
    for line in result.stderr.splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = " ".join(key.split())  # collapse sox's column padding ("RMS     amplitude")
        try:
            stats[key] = float(value.strip())
        except ValueError:
            continue
    return stats


def has_speech(path: Path) -> bool:
    """Heuristic check: is there enough signal/duration to be actual speech, not just silence/noise?"""
    stats = get_audio_stats(path)
    duration = stats.get("Length (seconds)", 0.0)
    rms = stats.get("RMS amplitude", 0.0)
    if duration < MIN_SPEECH_DURATION:
        return False
    if rms < SILENCE_RMS_THRESHOLD:
        return False
    return True


class AudioRecorder:
    def __init__(
        self,
        output_path: Path,
        on_level: Optional[Callable[[float], None]] = None,
        device_name: Optional[str] = None,
    ):
        self.output_path = output_path
        self.device_name = device_name.strip() if device_name and device_name.strip().lower() != "default" else None
        # Clean up any leftover 'rec' or 'sox' processes from previous sessions
        kill_stale_recorder_processes()
        # Recorded as raw WAV first so the level-monitor thread can tail it while it's being
        # written; encoded to FLAC (smaller upload) only once recording has stopped.
        self._raw_wav_path = output_path.with_suffix(".raw.wav")
        self.on_level = on_level
        self.process = None
        self.is_recording = False
        self._level_thread = None
        self._stop_level_event = threading.Event()
        # Ensure microphone is released if Python exits or crashes
        atexit.register(self.cancel)

    @property
    def active_device_display(self) -> str:
        """User-friendly name of the recording microphone."""
        if self.device_name:
            return f"{self.device_name} (Configured)"
        default_name = get_default_input_device_name()
        return f"{default_name} (System Default)"

    def start(self):
        if self.is_recording:
            return
        self._cleanup_temp_files()

        # Check if SoX is available
        sox_path = _find_binary("sox")
        rec_path = _find_binary("rec")
        if not sox_path and not rec_path:
            raise RuntimeError("SoX ('rec' / 'sox' command) is not found. Please install it using 'brew install sox'.")

        # Build recording command
        if self.device_name and sox_path:
            cmd = [
                sox_path,
                "-q",
                "-t", "coreaudio", self.device_name,
                "-r", "16000",
                "-c", "1",
                "-b", "16",
                str(self._raw_wav_path)
            ]
        else:
            bin_path = rec_path if rec_path else sox_path
            cmd = [
                bin_path,
                "-q",
                "-r", "16000",
                "-c", "1",
                "-b", "16",
                str(self._raw_wav_path)
            ]

        self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.is_recording = True
        play_sound("Tink")
        logger.info("Recording started (device=%s)", self.active_device_display)

        if self.on_level:
            self._stop_level_event.clear()
            self._level_thread = threading.Thread(target=self._monitor_levels, daemon=True)
            self._level_thread.start()

    def _monitor_levels(self):
        """Poll the growing WAV file and report a rough 0-1 mic level for the HUD equalizer."""
        last_pos = 44  # skip the 44-byte WAV header
        while not self._stop_level_event.is_set():
            time.sleep(0.08)
            try:
                if not self._raw_wav_path.exists():
                    continue
                with open(self._raw_wav_path, "rb") as f:
                    f.seek(0, 2)
                    size = f.tell()
                    if size <= last_pos:
                        continue
                    f.seek(last_pos)
                    chunk = f.read(size - last_pos)
                    last_pos = size
                sample_count = len(chunk) // 2
                if sample_count == 0:
                    continue
                samples = struct.unpack(f"<{sample_count}h", chunk[:sample_count * 2])
                rms = (sum(s * s for s in samples) / sample_count) ** 0.5
                level = min(1.0, (rms / MIC_LEVEL_SCALE) ** 0.5)
                logger.debug("Microphone level: rms=%.0f level=%.2f", rms, level)
                self.on_level(level)
            except Exception:
                continue

    def _stop_level_monitor(self):
        self._stop_level_event.set()
        if self._level_thread:
            self._level_thread.join(timeout=1.0)
            self._level_thread = None

    def _cleanup_temp_files(self):
        for path in (self._raw_wav_path, self.output_path):
            if path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass

    def _cleanup_raw(self):
        if self._raw_wav_path.exists():
            try:
                self._raw_wav_path.unlink()
            except Exception:
                pass

    def stop(self) -> Path:
        if not self.is_recording or self.process is None:
            return None
        self.is_recording = False
        self._stop_level_monitor()
        play_sound("Pop")
        logger.info("Recording stopped (processing audio)")

        # Terminate SoX gracefully to flush WAV headers
        try:
            self.process.send_signal(signal.SIGINT)
            self.process.wait(timeout=2.0)
        except Exception:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                pass
        self.process = None

        if not self._raw_wav_path.exists() or self._raw_wav_path.stat().st_size <= 44:
            self._cleanup_temp_files()
            return None

        # Encode to FLAC now that recording is complete (lossless, smaller upload than raw WAV)
        try:
            subprocess.run(
                ["sox", str(self._raw_wav_path), "-C", "8", str(self.output_path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=True
            )
        except Exception:
            self._cleanup_temp_files()
            return None
        self._cleanup_raw()

        # FLAC header alone is ~100+ bytes; anything smaller means no real audio was captured
        if self.output_path.exists() and self.output_path.stat().st_size > 128:
            return self.output_path
        return None

    def cancel(self):
        """Cancel recording without saving."""
        if self.is_recording and self.process:
            self.is_recording = False
            self._stop_level_monitor()
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                pass
            self.process = None
        self._cleanup_temp_files()
