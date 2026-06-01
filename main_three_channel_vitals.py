import os
import threading
import time
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime
from queue import Empty, Queue
from typing import List, Optional, Tuple

import numpy as np
import serial
from serial.tools import list_ports
from scipy.io import savemat
from scipy.signal import butter, find_peaks, sosfilt, sosfiltfilt

try:
    import hid
except Exception:  # pragma: no cover
    hid = None

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib import rcParams


rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Arial Unicode MS', 'DejaVu Sans']
rcParams['axes.unicode_minus'] = False


# ============================================================
# 通用工具
# ============================================================

def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_db(x: np.ndarray) -> np.ndarray:
    return 20.0 * np.log10(np.maximum(np.abs(x), np.finfo(float).eps))


# ============================================================
# 指夹血氧/心率仪 HID 采集
# ============================================================

VID = 0x28E9
PID = 0x028A

SEQ_A = [
    "7d81a78080808080807d81a2808080808080000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "82020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "831a011c121d3844056a000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "9f1f0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "8e031100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "81010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
]

SEQ_B = [
    "80000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "81010000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "82020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "9f1f0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "8e071500000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "8e031100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "9f1f0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "9b001b00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "9b011c00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
]

KEEPALIVE_INTERVAL = 5.0
KEEPALIVE_PAYLOAD64 = bytes.fromhex("9a1a" + "00" * 62)


def hex_to_64_bytes(hexstr: str) -> bytes:
    b = bytes.fromhex(hexstr)
    return (b + b"\x00" * 64)[:64]


def write_report65(dev: "hid.device", payload64: bytes) -> int:
    return dev.write(b"\x00" + payload64)


def parse_eb_frame(r: bytes) -> Tuple[Optional[Tuple[int, int]], List[int]]:
    vitals = None
    wave: List[int] = []
    i = 0
    n = len(r)
    while i < n:
        if r[i] != 0xEB:
            i += 1
            continue
        if i + 8 <= n and r[i + 1] == 0x01 and r[i + 2] == 0x05:
            vitals = (r[i + 3], r[i + 4])  # (HR, SpO2)
            i += 8
            continue
        if i + 6 <= n and r[i + 1] == 0x00:
            v = r[i + 3] | (r[i + 4] << 8)
            wave.append(v)
            i += 6
            continue
        i += 1
    return vitals, wave


@dataclass
class FingerState:
    hr: Optional[float] = None
    spo2: Optional[float] = None
    source: str = ""
    last_update_time: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)


class FingerClipReader(threading.Thread):
    def __init__(self, state: FingerState, stop_event: threading.Event, status_queue: Queue):
        super().__init__(daemon=True)
        self.state = state
        self.stop_event = stop_event
        self.status_queue = status_queue
        self.dev: Optional["hid.device"] = None

    def log(self, msg: str):
        self.status_queue.put(("status", f"[{ts()}] [心电仪] {msg}"))

    def send_seq(self, seq: List[str], label: str):
        self.log(f"初始化 {label}...")
        for s in seq:
            payload = hex_to_64_bytes(s)
            write_report65(self.dev, payload)
            time.sleep(0.01)

    def _safe_close(self):
        try:
            if self.dev is not None:
                self.dev.close()
        except Exception:
            pass
        self.dev = None

    def _open_and_stream_once(self) -> bool:
        if hid is None:
            self.log("未安装 hid 库，无法读取心电仪。")
            return True
        devs = hid.enumerate(VID, PID)
        if not devs:
            self.log(f"找不到设备 VID=0x{VID:04X} PID=0x{PID:04X}")
            return False

        for dinfo in devs:
            if self.stop_event.is_set():
                return True
            self._safe_close()
            try:
                self.dev = hid.device()
                self.dev.open_path(dinfo["path"])
                self.dev.set_nonblocking(False)
                self.send_seq(SEQ_A, "A")
                time.sleep(2.2)
                self.send_seq(SEQ_B, "B")
                write_report65(self.dev, KEEPALIVE_PAYLOAD64)
                self.log("连接成功。")
            except Exception as e:
                self.log(f"初始化失败: {e}")
                self._safe_close()
                continue
            return self._stream_loop()
        return False

    def _stream_loop(self) -> bool:
        last_keepalive = time.time()
        last_any_rx = time.time()
        last_spo2 = None
        while not self.stop_event.is_set():
            now = time.time()
            if now - last_keepalive >= KEEPALIVE_INTERVAL:
                try:
                    write_report65(self.dev, KEEPALIVE_PAYLOAD64)
                except Exception:
                    return False
                last_keepalive = now
            try:
                data = self.dev.read(64, timeout_ms=200)
            except Exception:
                return False
            if data:
                b = bytes(data)
                last_any_rx = now
                head = b[0]
                if head == 0xEB:
                    vitals, _ = parse_eb_frame(b)
                    if vitals is not None:
                        hr, spo2 = vitals
                        last_spo2 = spo2
                        with self.state.lock:
                            self.state.hr = float(hr)
                            self.state.spo2 = float(spo2)
                            self.state.source = "EB0105"
                            self.state.last_update_time = time.time()
                elif head == 0xF3 and len(b) >= 3:
                    hr_cand = int(b[2])
                    if 35 <= hr_cand <= 220:
                        with self.state.lock:
                            self.state.hr = float(hr_cand)
                            if last_spo2 is not None:
                                self.state.spo2 = float(last_spo2)
                            self.state.source = "F3"
                            self.state.last_update_time = time.time()
                elif head == 0xF0 and len(b) >= 2:
                    spo2_cand = int(b[1])
                    if 50 <= spo2_cand <= 100:
                        last_spo2 = spo2_cand
                        with self.state.lock:
                            self.state.spo2 = float(spo2_cand)
                            self.state.source = "F0/F3"
                            self.state.last_update_time = time.time()
            if now - last_any_rx > 3.0:
                return False
        return True

    def run(self):
        try:
            while not self.stop_event.is_set():
                ok = self._open_and_stream_once()
                if ok:
                    break
                if self.stop_event.is_set():
                    break
                time.sleep(2.0)
        except Exception as e:
            self.log(f"线程异常退出: {e!r}")
        finally:
            self._safe_close()


# ============================================================
# 雷达处理
# ============================================================


def filter_remove_impulse_noise(data_prev2: float, data_prev1: float, data_curr: float, thresh: float) -> Tuple[float, float, float]:
    backward_diff = data_prev1 - data_prev2
    forward_diff = data_prev1 - data_curr
    if ((forward_diff > thresh) and (backward_diff > thresh)) or ((forward_diff < -thresh) and (backward_diff < -thresh)):
        y = data_prev2 + ((1.0 - 0.0) * (data_curr - data_prev2)) / (2.0 - 0.0)
    else:
        y = data_prev1
    return y, backward_diff, forward_diff


def phase_noise_suppress(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float).copy()
    if x.size <= 2:
        return x
    x = x - np.median(x)
    absx = np.abs(x)
    med_abs = np.median(absx)
    if med_abs < np.finfo(float).eps:
        thr = max(0.06, 3.0 * np.std(x))
    else:
        thr = max(0.06, 5.0 * med_abs / 0.6745)
    idxs = np.where(absx > thr)[0]
    for k in idxs:
        if 0 < k < x.size - 1:
            x[k] = 0.5 * (x[k - 1] + x[k + 1])
        elif k == 0 and x.size > 1:
            x[k] = x[k + 1]
        elif k == x.size - 1 and x.size > 1:
            x[k] = x[k - 1]
    kernel = np.array([0.2, 0.6, 0.2], dtype=float)
    x = np.convolve(x, kernel, mode='same')
    return x


def estimate_heart_rate_bandlimited(heart_fre: np.ndarray, f_seg: np.ndarray, band=(0.8, 2.0)) -> tuple[float, float]:
    mask = (f_seg >= band[0]) & (f_seg <= band[1])
    if not np.any(mask):
        return 0.0, 0.0
    fb = f_seg[mask]
    pb = np.asarray(heart_fre[mask], dtype=float)
    if pb.size < 3:
        return 0.0, 0.0
    pb = np.convolve(pb, np.array([0.2, 0.6, 0.2], dtype=float), mode='same')
    idx = int(np.argmax(pb))
    peak_val = float(pb[idx])
    floor_val = float(np.median(np.maximum(pb, np.finfo(float).eps)))
    quality = peak_val / max(floor_val, np.finfo(float).eps)
    if 0 < idx < pb.size - 1:
        y1, y2, y3 = pb[idx - 1], pb[idx], pb[idx + 1]
        denom = y1 - 2.0 * y2 + y3
        if abs(denom) > np.finfo(float).eps:
            delta = 0.5 * (y1 - y3) / denom
            delta = float(np.clip(delta, -1.0, 1.0))
        else:
            delta = 0.0
    else:
        delta = 0.0
    df = float(fb[1] - fb[0]) if fb.size >= 2 else 0.0
    main_freq_hz = float(fb[idx] + delta * df)
    return main_freq_hz * 60.0, quality



# ============================================================
# 三通道生命体征增强工具函数
# ============================================================

def _next_pow2(n: int) -> int:
    if n <= 1:
        return 1
    return 1 << int(np.ceil(np.log2(n)))


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    mask = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not np.any(mask):
        return 0.0
    values = values[mask]
    weights = weights[mask]
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cdf = np.cumsum(weights) / max(float(np.sum(weights)), np.finfo(float).eps)
    return float(values[np.searchsorted(cdf, 0.5)])


def estimate_rate_fft_band(x: np.ndarray, fs: float, band: tuple[float, float], min_seconds: float) -> tuple[float, float, float]:
    """
    在指定频带内用 Hann + zero padding + 抛物线插值估计主频。
    返回: (BPM, 谱峰质量, 主频Hz)。质量约等于峰值/频带中值。
    """
    x = np.asarray(x, dtype=float).reshape(-1)
    x = x[np.isfinite(x)]
    n = x.size
    if fs <= 0 or n < max(16, int(min_seconds * fs)):
        return 0.0, 0.0, 0.0

    x = x - np.median(x)
    std_x = float(np.std(x))
    if std_x < 1e-10:
        return 0.0, 0.0, 0.0
    x = x / std_x

    nfft = max(1024, _next_pow2(n * 8))
    w = np.hanning(n)
    spec = np.abs(np.fft.rfft(w * x, nfft))
    freq = np.fft.rfftfreq(nfft, d=1.0 / fs)

    mask = (freq >= band[0]) & (freq <= band[1])
    if np.count_nonzero(mask) < 3:
        return 0.0, 0.0, 0.0

    fb = freq[mask]
    pb = spec[mask]
    pb = np.convolve(pb, np.array([0.2, 0.6, 0.2], dtype=float), mode='same')

    idx = int(np.argmax(pb))
    peak_val = float(pb[idx])
    floor_val = float(np.median(np.maximum(pb, np.finfo(float).eps)))
    quality = peak_val / max(floor_val, np.finfo(float).eps)

    delta = 0.0
    if 0 < idx < pb.size - 1:
        y1, y2, y3 = pb[idx - 1], pb[idx], pb[idx + 1]
        denom = y1 - 2.0 * y2 + y3
        if abs(denom) > np.finfo(float).eps:
            delta = 0.5 * (y1 - y3) / denom
            delta = float(np.clip(delta, -1.0, 1.0))
    df = float(fb[1] - fb[0]) if fb.size >= 2 else 0.0
    f0 = float(fb[idx] + delta * df)
    return f0 * 60.0, quality, f0


def estimate_breath_rate_peaks(x: np.ndarray, fs: float, band: tuple[float, float] = (0.1, 0.5)) -> tuple[float, float, np.ndarray, np.ndarray]:
    """用呼吸波形峰间距估计呼吸率，作为 FFT 估计的交叉验证。"""
    x = np.asarray(x, dtype=float).reshape(-1)
    n = x.size
    if fs <= 0 or n < int(10.0 * fs):
        return 0.0, 0.0, np.array([], dtype=int), np.array([], dtype=float)

    xx = x - np.median(x)
    std_x = float(np.std(xx))
    if std_x < 1e-10:
        return 0.0, 0.0, np.array([], dtype=int), np.array([], dtype=float)

    min_distance = max(1, int(0.72 * fs / band[1]))  # 呼吸最快 0.5Hz，留一点余量
    prominence = max(0.08 * std_x, 1e-8)
    pks, props = find_peaks(xx, distance=min_distance, prominence=prominence)
    peak_vals = xx[pks] if pks.size > 0 else np.array([], dtype=float)
    if pks.size < 2:
        return 0.0, 0.0, pks, peak_vals

    intervals = np.diff(pks) / fs
    if intervals.size == 0:
        return 0.0, 0.0, pks, peak_vals
    med = float(np.median(intervals))
    good = np.abs(intervals - med) <= max(0.35 * med, 0.35)
    intervals = intervals[good]
    if intervals.size == 0:
        return 0.0, 0.0, pks, peak_vals
    bpm = 60.0 / float(np.mean(intervals))
    if bpm < 6.0 or bpm > 30.0:
        return 0.0, 0.0, pks, peak_vals
    quality = float(pks.size) / max(n / fs / max(float(np.mean(intervals)), 1e-6), 1.0)
    return bpm, quality, pks, peak_vals


def bandpass_filter_sos(x: np.ndarray, fs: float, band: tuple[float, float], order: int = 2) -> np.ndarray:
    x = np.asarray(x, dtype=float).reshape(-1)
    if x.size == 0 or fs <= 0:
        return x.copy()
    lo = max(1e-6, band[0] / fs * 2.0)
    hi = min(0.999, band[1] / fs * 2.0)
    if not (0.0 < lo < hi < 1.0):
        return x - np.median(x)
    sos = butter(order, [lo, hi], btype='bandpass', output='sos')
    try:
        return sosfiltfilt(sos, x)
    except Exception:
        return sosfilt(sos, x)


class MatlabStrictRadarProcessor:
    def __init__(self, port: str, baudrate: int = 115200, save_enabled: bool = False):
        self.port = port
        self.baudrate = baudrate
        self.save_enabled = save_enabled
        self.serial_port: Optional[serial.Serial] = None

        # MATLAB 参数
        self.c = 3e8
        self.f = 60e9
        self.lambda_ = self.c / self.f
        self.BW = 4e9
        self.fs_adc = 1e6
        self.chirp_repetition_time_s = 300e-06
        self.frame_repetition_time_s = 50e-03
        self.rx_antennas = [1, 1, 1]
        self.num_samples_per_chirp = 1
        self.num_chirps_per_frame = 256
        self.MaxRange = (self.fs_adc * self.c) / (2 * self.BW / self.chirp_repetition_time_s)
        self.deltaR = self.MaxRange / self.num_chirps_per_frame
        self.buffer_size = int(self.num_samples_per_chirp * self.num_chirps_per_frame * 12 / 8)
        self.buffer = np.zeros((self.buffer_size // 3 * 2, 3), dtype=np.float64)
        self.frame_count = 0
        self.count_disp = 20
        self.max_columns = 600

        # 三通道时间缓存: [range_sample/chirp_index, slow_time_frame, rx_channel]
        # 原代码虽然解出了 Rx1/Rx2/Rx3，但后续只把 Rx3.T 存入 Rx3_m 做生命体征估计。
        self.Rx_m = np.empty((256, 0, 3), dtype=np.float64)
        self.saved_frames: List[dict] = []

        # 单人胸腔检测建议范围，可根据实际安装距离调整
        self.target_range_min_m = 0.20
        self.target_range_max_m = 3.00
        self.prev_range_bin0: Optional[int] = None

        # 呼吸/心率稳定器：避免瞬时频谱峰跳变直接映射到输出
        self.prev_breath_rate = 0.0
        self.prev_heart_rate = 0.0
        self.breath_rate_hist = deque(maxlen=5)
        self.heart_rate_hist = deque(maxlen=7)
        self.low_quality_breath_hold_count = 0
        self.low_quality_heart_hold_count = 0

    def open(self):
        self.serial_port = serial.Serial(self.port, self.baudrate, timeout=None)
        self.serial_port.reset_input_buffer()
        self._sync_header()

    def close(self):
        if self.serial_port is not None:
            try:
                self.serial_port.reset_input_buffer()
            except Exception:
                pass
            try:
                self.serial_port.close()
            except Exception:
                pass
            self.serial_port = None

    def _sync_header(self):
        while True:
            b = self.serial_port.read(1)
            if not b:
                continue
            if b[0] == 0x00:
                rest = self.serial_port.read(7)
                if len(rest) == 7 and all(rest[i] == i + 1 for i in range(7)):
                    return

    def _decode_payload(self, payload: bytes):
        data = np.frombuffer(payload, dtype=np.uint8)
        self.buffer.fill(0.0)
        step = 3 * sum(self.rx_antennas)  # 固定 9: 三个 RX，每个 RX 两个 12bit 点，共 9 字节
        for i in range(0, len(data), step):
            if i + 8 >= len(data):
                break
            row1 = (i // 9) * 2
            row2 = row1 + 1
            self.buffer[row1, 0] = (int(data[i]) << 4) + (int(data[i + 1]) >> 4)
            self.buffer[row1, 1] = ((int(data[i + 1]) & 0x0F) << 8) + int(data[i + 2])
            self.buffer[row1, 2] = (int(data[i + 3]) << 4) + (int(data[i + 4]) >> 4)
            self.buffer[row2, 0] = ((int(data[i + 4]) & 0x0F) << 8) + int(data[i + 5])
            self.buffer[row2, 1] = (int(data[i + 6]) << 4) + (int(data[i + 7]) >> 4)
            self.buffer[row2, 2] = ((int(data[i + 7]) & 0x0F) << 8) + int(data[i + 8])

    def _preprocess_phase_from_complex(self, z: np.ndarray) -> np.ndarray:
        """复数距离门 -> 解缠相位差 -> 脉冲噪声抑制 -> 轻平滑。"""
        z = np.asarray(z).reshape(-1)
        n = z.size
        if n == 0:
            return np.array([], dtype=float)
        if n < 3 or np.median(np.abs(z)) < np.finfo(float).eps:
            return np.zeros(n, dtype=float)

        phase_tmp = np.unwrap(np.angle(z))
        dphi = np.zeros(n, dtype=float)
        dphi[1:] = np.diff(phase_tmp)
        dphi = dphi - np.median(dphi)

        # 先做 robust clipping，避免某一帧相位跳变污染 filtfilt
        mad = float(np.median(np.abs(dphi - np.median(dphi))))
        sigma = 1.4826 * mad if mad > 0 else float(np.std(dphi))
        if sigma > 1e-8:
            dphi = np.clip(dphi, -6.0 * sigma, 6.0 * sigma)

        dphi_deg = np.rad2deg(dphi)
        y = dphi_deg.copy()
        threshold = 90.0
        for i in range(1, n - 1):
            y[i], _, _ = filter_remove_impulse_noise(
                dphi_deg[i - 1], dphi_deg[i], dphi_deg[i + 1], threshold
            )
        y = np.deg2rad(y)
        y = phase_noise_suppress(y)
        y = y - np.median(y)
        return np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

    def _select_target_range_bin(self, avg_all: np.ndarray, rax_plot: np.ndarray) -> int:
        """三通道非相干累加选距离门，并对距离门跳变做轻约束。"""
        recent_len = min(140, avg_all.shape[1])
        recent = avg_all[:, -recent_len:, :]
        energy = np.sum(np.abs(recent), axis=(1, 2))

        valid = (rax_plot >= self.target_range_min_m) & (rax_plot <= self.target_range_max_m)
        if not np.any(valid):
            valid = np.ones_like(energy, dtype=bool)
        masked_energy = np.where(valid, energy, 0.0)
        candidate = int(np.argmax(masked_energy))

        # 距离门稳定：如果上一距离门附近能量接近全局峰，则优先保持，避免人体微动时在相邻门间来回跳。
        if self.prev_range_bin0 is not None:
            lo = max(0, self.prev_range_bin0 - 2)
            hi = min(len(energy), self.prev_range_bin0 + 3)
            local = lo + int(np.argmax(masked_energy[lo:hi]))
            if masked_energy[local] >= 0.65 * max(masked_energy[candidate], np.finfo(float).eps):
                candidate = local

        self.prev_range_bin0 = candidate
        return candidate

    def _extract_fused_phase(self, avg_all: np.ndarray, target_bin0: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        从同一个距离门提取三个通道的相位微动，并按通道质量加权融合。
        返回: fused_phase, channel_phase[T,3], normalized_weights[3]
        """
        n = avg_all.shape[1]
        ch_num = avg_all.shape[2]
        channel_phase = np.zeros((n, ch_num), dtype=float)
        q = np.zeros(ch_num, dtype=float)

        # 距离门目标幅度 / 全图中值作为通道质量的第一指标
        for ch in range(ch_num):
            z = avg_all[target_bin0, :, ch]
            sig = self._preprocess_phase_from_complex(z)
            channel_phase[:, ch] = sig

            amp_target = np.abs(z[-min(120, n):])
            noise_floor = np.median(np.abs(avg_all[:, -min(120, n):, ch])) + np.finfo(float).eps
            snr_like = float(np.median(amp_target) / noise_floor)
            phase_power = float(np.std(sig))
            if phase_power < 1e-8:
                snr_like = 0.0
            q[ch] = max(0.0, snr_like)

        # 以质量最高通道为参考，对其它通道做符号一致性校正。
        ref_ch = int(np.argmax(q)) if np.any(q > 0) else 0
        ref = channel_phase[:, ref_ch]
        for ch in range(ch_num):
            if ch == ref_ch:
                continue
            a = ref[-min(160, n):]
            b = channel_phase[-min(160, n):, ch]
            if np.std(a) > 1e-8 and np.std(b) > 1e-8:
                corr = float(np.corrcoef(a, b)[0, 1])
                if np.isfinite(corr) and corr < -0.15:
                    channel_phase[:, ch] *= -1.0
                elif (not np.isfinite(corr)) or abs(corr) < 0.05:
                    q[ch] *= 0.45

        if np.sum(q) <= np.finfo(float).eps:
            weights = np.ones(ch_num, dtype=float) / ch_num
        else:
            weights = np.clip(q, 0.0, np.percentile(q, 90) + np.finfo(float).eps)
            weights = weights / max(float(np.sum(weights)), np.finfo(float).eps)

        fused = np.sum(channel_phase * weights[None, :], axis=1)
        fused = fused - np.median(fused)
        return fused, channel_phase, weights

    def _stabilize_breath_rate(self, raw_bpm: float, quality: float) -> float:
        if raw_bpm < 6.0 or raw_bpm > 30.0 or quality < 1.6:
            if self.prev_breath_rate > 0 and self.low_quality_breath_hold_count < 6:
                self.low_quality_breath_hold_count += 1
                return float(self.prev_breath_rate)
            return 0.0

        self.low_quality_breath_hold_count = 0
        out = float(raw_bpm)
        if self.prev_breath_rate > 0:
            max_step = 1.2 if quality < 2.5 else 2.0
            out = float(np.clip(out, self.prev_breath_rate - max_step, self.prev_breath_rate + max_step))
        self.breath_rate_hist.append(out)
        if len(self.breath_rate_hist) >= 3:
            out = float(np.median(np.asarray(self.breath_rate_hist, dtype=float)[-5:]))
        self.prev_breath_rate = out
        return out

    def _stabilize_heart_rate(self, raw_bpm: float, quality: float, breathing_rate: float) -> float:
        if breathing_rate <= 0 or raw_bpm < 45.0 or raw_bpm > 140.0 or quality < 2.0:
            if self.prev_heart_rate > 0 and self.low_quality_heart_hold_count < 6:
                self.low_quality_heart_hold_count += 1
                return float(self.prev_heart_rate)
            return 0.0

        self.low_quality_heart_hold_count = 0
        out = float(raw_bpm)
        if self.prev_heart_rate > 0:
            diff_bpm = abs(out - self.prev_heart_rate)
            max_step = 2.0 if quality < 3.0 else (3.5 if quality < 5.0 else 5.0)
            out = float(np.clip(out, self.prev_heart_rate - max_step, self.prev_heart_rate + max_step))
            if diff_bpm > 10.0:
                out = 0.82 * self.prev_heart_rate + 0.18 * out
        self.heart_rate_hist.append(out)
        if len(self.heart_rate_hist) >= 3:
            out = float(np.median(np.asarray(self.heart_rate_hist, dtype=float)[-5:]))
        self.prev_heart_rate = out
        return out

    def _estimate_breath(self, fused_phase: np.ndarray, fs_signal: float) -> tuple[float, np.ndarray, np.ndarray, float]:
        breath_signal = bandpass_filter_sos(fused_phase, fs_signal, (0.1, 0.5), order=2)
        fft_bpm, fft_q, _ = estimate_rate_fft_band(breath_signal, fs_signal, (0.1, 0.5), min_seconds=12.0)
        peak_bpm, peak_q, locs, peak_vals = estimate_breath_rate_peaks(breath_signal, fs_signal, band=(0.1, 0.5))

        if fft_bpm > 0 and peak_bpm > 0 and abs(fft_bpm - peak_bpm) <= 4.0:
            raw = 0.65 * fft_bpm + 0.35 * peak_bpm
            quality = max(fft_q, 1.0 + peak_q)
        elif fft_bpm > 0:
            raw = fft_bpm
            quality = fft_q
        elif peak_bpm > 0:
            raw = peak_bpm
            quality = 1.0 + peak_q
        else:
            raw = 0.0
            quality = 0.0

        return self._stabilize_breath_rate(raw, quality), locs, peak_vals, quality

    def _estimate_heart(self, fused_phase: np.ndarray, channel_phase: np.ndarray, channel_weights: np.ndarray,
                        fs_signal: float, breathing_rate: float) -> tuple[float, float, float]:
        heart_signal = bandpass_filter_sos(fused_phase, fs_signal, (0.8, 2.0), order=2)
        rates = []
        qualities = []

        bpm, q, _ = estimate_rate_fft_band(heart_signal, fs_signal, (0.8, 2.0), min_seconds=8.0)
        if 45.0 <= bpm <= 140.0 and q > 0:
            rates.append(bpm)
            qualities.append(1.35 * q)

        # 三个通道各自估计心率，作为融合结果的冗余校验。
        for ch in range(channel_phase.shape[1]):
            hs_ch = bandpass_filter_sos(channel_phase[:, ch], fs_signal, (0.8, 2.0), order=2)
            bpm_ch, q_ch, _ = estimate_rate_fft_band(hs_ch, fs_signal, (0.8, 2.0), min_seconds=8.0)
            if 45.0 <= bpm_ch <= 140.0 and q_ch > 0:
                rates.append(bpm_ch)
                qualities.append(q_ch * (0.5 + 1.5 * float(channel_weights[ch])))

        if not rates:
            return self._stabilize_heart_rate(0.0, 0.0, breathing_rate), 0.0, 0.0

        rates_arr = np.asarray(rates, dtype=float)
        q_arr = np.asarray(qualities, dtype=float)

        # 候选聚类：优先选择与上一帧心率接近的可信簇，否则选择最高质量附近的簇。
        if self.prev_heart_rate > 0 and np.any(np.abs(rates_arr - self.prev_heart_rate) <= 10.0):
            cluster = np.abs(rates_arr - self.prev_heart_rate) <= 10.0
        else:
            best = int(np.argmax(q_arr))
            cluster = np.abs(rates_arr - rates_arr[best]) <= 8.0
        raw_bpm = _weighted_median(rates_arr[cluster], q_arr[cluster])
        quality = float(np.max(q_arr[cluster])) if np.any(cluster) else float(np.max(q_arr))

        return self._stabilize_heart_rate(raw_bpm, quality, breathing_rate), quality, raw_bpm

    def process_frame(self) -> Optional[dict]:
        expected_len = sum(self.rx_antennas) * self.buffer_size + 8
        data = self.serial_port.read(expected_len)
        if len(data) < expected_len:
            return None
        frame_header = data[-8:]
        if frame_header != bytes([0, 1, 2, 3, 4, 5, 6, 7]):
            raise RuntimeError("雷达帧尾校验失败")
        payload = data[:-8]
        self.frame_count += 1
        self._decode_payload(payload)

        rx1 = self.buffer[:, 0].reshape((self.num_samples_per_chirp, self.num_chirps_per_frame), order='F')
        rx2 = self.buffer[:, 1].reshape((self.num_samples_per_chirp, self.num_chirps_per_frame), order='F')
        rx3 = self.buffer[:, 2].reshape((self.num_samples_per_chirp, self.num_chirps_per_frame), order='F')

        if self.save_enabled:
            self.saved_frames.append({
                "Rx1": rx1.copy(),
                "Rx2": rx2.copy(),
                "Rx3": rx3.copy(),
            })

        rx_frame = np.stack([rx1.T[:, 0], rx2.T[:, 0], rx3.T[:, 0]], axis=1)  # 256 x 3
        if self.Rx_m.size == 0:
            self.Rx_m = rx_frame[:, None, :].copy()
        else:
            self.Rx_m = np.concatenate([self.Rx_m, rx_frame[:, None, :]], axis=1)

        if self.frame_count % self.count_disp != 0:
            return None

        rx_m_size = self.Rx_m.shape[1]
        if rx_m_size > self.max_columns:
            self.Rx_m = self.Rx_m[:, self.count_disp:, :]
            rx_m_size = self.Rx_m.shape[1]

        rax = np.arange(256, dtype=float) * self.deltaR
        tax = np.arange(rx_m_size + 1, dtype=float) * self.frame_repetition_time_s
        t_plot = tax[:rx_m_size]
        posS = 129
        rax_plot = rax[:posS - 1]

        # 三通道 Range-Time 谱：FFT 后只取正距离半轴。
        rx_rpc_temp = np.fft.fftshift(np.fft.fft(self.Rx_m, 256, axis=0), axes=0)
        rx_rpc = rx_rpc_temp[posS - 1:, :, :]  # 128 x T x 3

        if rx_m_size >= 2:
            clutter = np.mean(rx_rpc, axis=1, keepdims=True)
            avg_all = rx_rpc - clutter
        else:
            avg_all = np.zeros_like(rx_rpc)

        # 显示用三通道非相干融合 MTI 图。
        mti_mag = np.sqrt(np.sum(np.abs(avg_all) ** 2, axis=2))
        db_avg = safe_db(mti_mag)

        max_range_bin0 = self._select_target_range_bin(avg_all, rax_plot)
        max_range_bin1 = max_range_bin0 + 1

        fused_phase, channel_phase, channel_weights = self._extract_fused_phase(avg_all, max_range_bin0)

        # 相位变化换算为位移变化，主要用于调试/保存；生命体征滤波仍使用相位量。
        filt_phase_magnitude = fused_phase * self.lambda_ / (4.0 * np.pi)

        fs_signal = 1.0 / self.frame_repetition_time_s

        breathing_rate, locs, peak_vals, breath_quality = self._estimate_breath(fused_phase, fs_signal)
        data_out_phase_breath = bandpass_filter_sos(fused_phase, fs_signal, (0.1, 0.5), order=2)

        heart_rate_bpm, heart_quality, raw_heart_bpm = self._estimate_heart(
            fused_phase, channel_phase, channel_weights, fs_signal, breathing_rate
        )
        data_out_phase_heart = bandpass_filter_sos(fused_phase, fs_signal, (0.8, 2.0), order=2)

        target_range_m = float(rax_plot[max_range_bin0]) if max_range_bin0 < len(rax_plot) else 0.0

        return {
            "range_m": target_range_m,
            "range_bin_index": max_range_bin1,
            "breath_bpm": float(breathing_rate),
            "heart_bpm": float(heart_rate_bpm),
            "t_plot": t_plot,
            "rax_plot": rax_plot,
            "mti_db": db_avg,
            "magnitude": filt_phase_magnitude,
            "breath_signal": data_out_phase_breath,
            "breath_locs": locs,
            "breath_pks": peak_vals,
            "heart_signal": data_out_phase_heart,
            "channel_weights": channel_weights,
            "breath_quality": float(breath_quality),
            "heart_quality": float(heart_quality),
            "raw_heart_bpm": float(raw_heart_bpm),
        }

    def save_raw_data(self, path: str):
        if not self.saved_frames:
            raise RuntimeError("当前没有可保存的数据")
        rx1_list = [f["Rx1"] for f in self.saved_frames]
        rx2_list = [f["Rx2"] for f in self.saved_frames]
        rx3_list = [f["Rx3"] for f in self.saved_frames]
        savemat(path, {"Radra_Data": {"Rx1": rx1_list, "Rx2": rx2_list, "Rx3": rx3_list}})


# ============================================================
# GUI
# ============================================================

class RadarMatlabStrictApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("60GHz单人雷达呼吸心率检测")
        self.root.geometry("1180x820")

        self.status_queue: Queue = Queue()
        self.result_queue: Queue = Queue()
        self.stop_event = threading.Event()
        self.radar_thread: Optional[threading.Thread] = None
        self.finger_thread: Optional[FingerClipReader] = None
        self.radar_processor: Optional[MatlabStrictRadarProcessor] = None
        self.finger_state = FingerState()

        self._build_ui()
        self._refresh_ports(initial=True)
        self.root.after(100, self._poll_queues)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        controls = ttk.Frame(self.root, padding=8)
        controls.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(controls, text="在线分析：", font=("Microsoft YaHei", 11, "bold")).grid(row=0, column=0, padx=4)
        ttk.Label(controls, text="串口").grid(row=0, column=1, padx=4)
        self.port_var = tk.StringVar(value="")
        self.port_cb = ttk.Combobox(controls, textvariable=self.port_var, width=12, state="readonly")
        self.port_cb.grid(row=0, column=2, padx=4)
        self.port_cb.bind("<<ComboboxSelected>>", self._on_port_changed)
        ttk.Button(controls, text="刷新串口", command=self._refresh_ports).grid(row=0, column=3, padx=4)

        ttk.Label(controls, text="波特率").grid(row=0, column=4, padx=4)
        self.baud_var = tk.StringVar(value="115200")
        self.baud_cb = ttk.Combobox(controls, textvariable=self.baud_var, width=10, state="readonly",
                                    values=["115200", "921600"])
        self.baud_cb.grid(row=0, column=5, padx=4)

        self.save_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls, text="是否保存数据", variable=self.save_var).grid(row=0, column=6, padx=12)
        ttk.Button(controls, text="保存", command=self._save_data).grid(row=0, column=7, padx=4)

        ttk.Button(controls, text="开始", command=self.start).grid(row=0, column=8, padx=12)
        ttk.Button(controls, text="结束", command=self.stop).grid(row=0, column=9, padx=4)

        metrics = ttk.Frame(self.root, padding=(8, 0, 8, 0))
        metrics.pack(side=tk.TOP, fill=tk.X)
        self.range_bin_var = tk.StringVar(value="最大距离门的索引是: ")
        self.range_var = tk.StringVar(value="目标距离: ")
        self.breath_var = tk.StringVar(value="呼吸: ")
        self.heart_var = tk.StringVar(value="心率: ")
        self.finger_hr_var = tk.StringVar(value="心电仪心率: ")
        self.diff_var = tk.StringVar(value="心率差值: ")
        for idx, var in enumerate([self.range_bin_var, self.range_var, self.breath_var, self.heart_var,
                                   self.finger_hr_var, self.diff_var]):
            ttk.Label(metrics, textvariable=var, foreground="#1f77b4", font=("Microsoft YaHei", 12, "bold")).grid(
                row=0, column=idx, padx=8, pady=4, sticky="w"
            )

        fig = Figure(figsize=(11, 6.6), dpi=100)
        fig.subplots_adjust(left=0.07, right=0.98, top=0.93, bottom=0.08, wspace=0.20, hspace=0.34)
        self.ax_breath = fig.add_subplot(223)
        self.ax_heart = fig.add_subplot(224)
        self.ax_mti = fig.add_subplot(221)
        self.ax_compare = fig.add_subplot(222)

        self.ax_breath.set_title("呼吸波形", pad=10)
        self.ax_heart.set_title("心跳波形", pad=10)
        self.ax_mti.set_title("时间距离谱", pad=8)
        self.ax_compare.set_title("雷达心率与心电仪心率对比", pad=8)

        self.ax_breath.set_xlabel("时间")
        self.ax_breath.set_ylabel("幅度")
        self.ax_breath.set_ylim(-1.5, 1.5)
        self.ax_breath.grid(True)

        self.ax_heart.set_xlabel("时间 (s)")
        self.ax_heart.set_ylabel("幅度")
        self.ax_heart.set_ylim(-1.5, 1.5)
        self.ax_heart.grid(True)

        self.ax_mti.set_xlabel("时间 (s)")
        self.ax_mti.set_ylabel("距离 (m)")
        self.ax_mti.set_ylim(0, 5)
        self.ax_mti.grid(True)

        self.ax_compare.set_xlabel("时间 (s)")
        self.ax_compare.set_ylabel("心率 (BPM)")
        self.ax_compare.set_ylim(40, 140)
        self.ax_compare.grid(True)

        self.compare_window_sec = 30.0
        self.compare_t = deque()
        self.compare_radar_hr = deque()
        self.compare_finger_hr = deque()
        self.plot_start_time = time.time()

        self.canvas = FigureCanvasTkAgg(fig, master=self.root)
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        status_frame = ttk.Frame(self.root, padding=8)
        status_frame.pack(side=tk.BOTTOM, fill=tk.BOTH)
        ttk.Label(status_frame, text="状态栏", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w")
        self.status_text = tk.Text(status_frame, height=4, font=("Microsoft YaHei", 10))
        self.status_text.pack(fill=tk.BOTH, expand=False)
        self._append_status("正在寻找串口...")

        self._mti_im = None

    def _append_status(self, msg: str):
        self.status_text.insert(tk.END, msg + "\n")
        lines = int(float(self.status_text.index('end-1c').split('.')[0]))
        if lines > 100:
            self.status_text.delete('1.0', f'{lines-100}.0')
        self.status_text.see(tk.END)

    def _refresh_ports(self, initial: bool = False):
        ports = [p.device for p in list_ports.comports()]
        if not ports:
            self.port_cb["values"] = ["无可用串口"]
            self.port_var.set("无可用串口")
            self._append_status("无可用串口！")
        else:
            self.port_cb["values"] = ports
            if initial or self.port_var.get() not in ports:
                self.port_var.set(ports[0])
            self._append_status("找到串口！")
            self._append_status(f"成功打开串口: {self.port_var.get()}（待开始时连接）")

    def _on_port_changed(self, _event=None):
        port = self.port_var.get()
        if port and port != "无可用串口":
            self._append_status(f"成功打开串口: {port}（待开始时连接）")
        else:
            self._append_status("没有可用的串口，无法打开串口。")

    def start(self):
        if self.radar_thread is not None and self.radar_thread.is_alive():
            self._append_status("程序已经在运行。")
            return
        port = self.port_var.get().strip()
        if not port or port == "无可用串口":
            messagebox.showerror("错误", "请先选择有效串口")
            return
        self.stop_event.clear()
        baud = int(self.baud_var.get())
        self.radar_processor = MatlabStrictRadarProcessor(port=port, baudrate=baud, save_enabled=self.save_var.get())
        self.radar_thread = threading.Thread(target=self._radar_worker, daemon=True)
        self.radar_thread.start()
        self.finger_thread = FingerClipReader(self.finger_state, self.stop_event, self.status_queue)
        self.finger_thread.start()
        self._append_status("开始采集。")

    def stop(self):
        self.stop_event.set()
        self._append_status("停止采集。")

    def _save_data(self):
        if self.radar_processor is None or not self.radar_processor.saved_frames:
            messagebox.showerror("错误", "需要保存的数据为空")
            return
        path = filedialog.asksaveasfilename(defaultextension=".mat", filetypes=[("MAT 文件", "*.mat")])
        if not path:
            return
        try:
            self.radar_processor.save_raw_data(path)
            messagebox.showinfo("保存成功", "保存成功！")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def _radar_worker(self):
        try:
            self.status_queue.put(("status", f"[{ts()}] 正在搜索雷达帧头..."))
            self.radar_processor.open()
            self.status_queue.put(("status", f"[{ts()}] 雷达帧头同步成功，开始实时检测。"))
            while not self.stop_event.is_set():
                result = self.radar_processor.process_frame()
                if result is not None:
                    self.result_queue.put(result)
        except Exception as e:
            self.status_queue.put(("status", f"[{ts()}] 雷达线程异常: {e}"))
        finally:
            if self.radar_processor is not None:
                self.radar_processor.close()

    def _poll_queues(self):
        try:
            while True:
                kind, msg = self.status_queue.get_nowait()
                if kind == "status":
                    self._append_status(msg)
        except Empty:
            pass

        latest = None
        try:
            while True:
                latest = self.result_queue.get_nowait()
        except Empty:
            pass

        if latest is not None:
            self._apply_result(latest)

        self.root.after(100, self._poll_queues)

    def _apply_result(self, result: dict):
        with self.finger_state.lock:
            finger_hr = self.finger_state.hr

        breath_bpm = result["breath_bpm"]
        heart_bpm = result["heart_bpm"]
        diff = (heart_bpm - finger_hr) if (finger_hr is not None) else None

        self.range_bin_var.set(f"最大距离门的索引是: {result['range_bin_index']}")
        self.range_var.set(f"目标距离: {result['range_m']:.2f} m")
        self.breath_var.set(f"呼吸: {breath_bpm:.2f}")
        self.heart_var.set(f"心率: {heart_bpm:.2f}")
        self.finger_hr_var.set("心电仪心率: N/A" if finger_hr is None else f"心电仪心率: {finger_hr:.2f}")
        self.diff_var.set("心率差值: N/A" if diff is None else f"心率差值: {diff:+.2f}")

        t_plot = result["t_plot"]
        rax_plot = result["rax_plot"]
        mti_db = result["mti_db"]

        self.ax_mti.clear()
        self.ax_mti.imshow(
            mti_db,
            origin='lower',
            aspect='auto',
            extent=[0.0 if len(t_plot) == 0 else t_plot[0], 0.0 if len(t_plot) == 0 else t_plot[-1], rax_plot[0], rax_plot[-1]],
            cmap='jet',
            vmin=40,
            vmax=130,
        )
        self.ax_mti.set_title("时间距离谱")
        self.ax_mti.set_xlabel("时间 (s)")
        self.ax_mti.set_ylabel("距离 (m)")
        self.ax_mti.set_ylim(0, 5)
        self.ax_mti.grid(True)

        self.ax_breath.clear()
        self.ax_breath.plot(t_plot, result["breath_signal"])
        self.ax_breath.set_title("呼吸波形")
        self.ax_breath.set_xlabel("时间")
        self.ax_breath.set_ylabel("幅度")
        self.ax_breath.set_ylim(-1.5, 1.5)
        self.ax_breath.grid(True)

        self.ax_heart.clear()
        self.ax_heart.plot(t_plot, result["heart_signal"])
        self.ax_heart.set_title("心跳波形")
        self.ax_heart.set_xlabel("时间 (s)")
        self.ax_heart.set_ylabel("幅度")
        self.ax_heart.set_ylim(-1.5, 1.5)
        self.ax_heart.grid(True)

        now_t = time.time() - self.plot_start_time
        self.compare_t.append(now_t)
        self.compare_radar_hr.append(float(heart_bpm))
        self.compare_finger_hr.append(np.nan if finger_hr is None else float(finger_hr))
        while self.compare_t and (self.compare_t[-1] - self.compare_t[0] > self.compare_window_sec):
            self.compare_t.popleft()
            self.compare_radar_hr.popleft()
            self.compare_finger_hr.popleft()

        self.ax_compare.clear()
        tx = np.asarray(self.compare_t, dtype=float)
        if tx.size > 0:
            tx = tx - tx[0]
        radar_arr = np.asarray(self.compare_radar_hr, dtype=float)
        finger_arr = np.asarray(self.compare_finger_hr, dtype=float)
        self.ax_compare.plot(tx, radar_arr, label="雷达心率")
        self.ax_compare.plot(tx, finger_arr, label="心电仪心率")
        self.ax_compare.set_title("雷达心率与心电仪心率对比")
        self.ax_compare.set_xlabel("时间 (s)")
        self.ax_compare.set_ylabel("心率 (BPM)")
        self.ax_compare.set_ylim(40, 140)
        self.ax_compare.grid(True)
        self.ax_compare.legend(loc='upper left')

        self.canvas.draw_idle()

        diff_text = "N/A" if diff is None else f"{diff:+.2f}"
        finger_text = "N/A" if finger_hr is None else f"{finger_hr:5.2f}"
        self._append_status(
            f"[{ts()}] 目标距离: {result['range_m']:5.2f} m   雷达呼吸: {breath_bpm:5.2f}   雷达心率: {heart_bpm:5.2f}   心电仪心率: {finger_text}   心率差值: {diff_text}"
        )

    def on_close(self):
        self.stop_event.set()
        self.root.after(200, self.root.destroy)


def main():
    root = tk.Tk()
    app = RadarMatlabStrictApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
