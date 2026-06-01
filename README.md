# 60GHz FMCW Radar Breath and Heart Detection

基于 Python 的 60GHz FMCW 雷达单人呼吸率与心率实时检测程序。

本项目面向单人近距离生命体征检测场景，通过串口读取 60GHz FMCW 雷达三接收通道数据，完成数据解包、距离维 FFT、静态杂波抑制、目标距离门选择、三通道相位融合、呼吸率估计、心率估计，并提供 Tkinter + Matplotlib 图形界面进行实时显示。同时，程序支持通过 USB HID 读取指夹式心率/血氧仪数据，用于和雷达心率结果进行对比验证。

> 注意：当前工程虽然仓库名中包含 `MATLAB Code`，但本脚本实际是 Python 程序。脚本中部分类名和注释保留了 MATLAB 迁移痕迹，例如 `MatlabStrictRadarProcessor`、`Radra_Data` 等。

---

## 1. 项目定位

毫米波 FMCW 雷达可以利用人体胸腔微小运动引起的回波相位变化，非接触式估计呼吸和心跳。

呼吸运动通常较强，频率较低，主要位于：

```text
0.1 Hz ~ 0.5 Hz
```

对应：

```text
6 BPM ~ 30 BPM
```

心跳运动更弱，频率更高，主要位于：

```text
0.8 Hz ~ 2.0 Hz
```

对应：

```text
48 BPM ~ 120 BPM
```

本程序的基本思想是：

```text
雷达串口数据
    ↓
三通道 12bit 数据解码
    ↓
构造慢时间数据矩阵
    ↓
距离维 FFT
    ↓
静态杂波均值扣除
    ↓
选择人体所在距离门
    ↓
提取三通道复数相位
    ↓
相位解缠、差分、去异常点、平滑
    ↓
三通道相位加权融合
    ↓
呼吸频带 / 心率频带滤波
    ↓
FFT 主频估计 + 峰值辅助 + 输出稳定
    ↓
GUI 实时显示
```

本项目适合用于：

- 60GHz FMCW 雷达生命体征算法学习；
- 雷达非接触式呼吸检测实验；
- 雷达非接触式心率检测实验；
- 雷达心率与指夹仪心率对比；
- 三接收通道相位融合验证；
- 雷达 GUI 原型程序开发；
- 雷达原始数据保存与离线分析。

本项目不属于医疗器械软件，不能用于临床诊断、治疗判断或医疗决策。

---

## 2. 主要功能

当前脚本实现了以下功能：

```text
1. 自动搜索本机串口；
2. 选择串口与波特率；
3. 串口读取雷达在线数据；
4. 检测雷达帧同步标志；
5. 对三接收通道数据进行 12bit 解包；
6. 构造 Rx1 / Rx2 / Rx3 三通道数据；
7. 对连续帧数据进行缓存；
8. 距离维 FFT，生成 Range-Time 数据；
9. 均值扣除，抑制静态杂波；
10. 根据三通道非相干能量选择人体距离门；
11. 对目标距离门提取复数相位；
12. 对相位进行 unwrap、差分、异常点抑制和平滑；
13. 根据通道质量进行三通道加权融合；
14. 估计呼吸率；
15. 估计心率；
16. 对呼吸率和心率做连续性约束；
17. 支持 USB HID 指夹心率/血氧仪读取；
18. 实时显示雷达呼吸、雷达心率、指夹心率和心率差值；
19. 实时绘制时间-距离谱、呼吸波形、心跳波形、心率对比曲线；
20. 支持保存原始三通道雷达数据为 .mat 文件。
```

---

## 3. 代码文件说明

当前脚本主要由四个部分组成：

```text
1. 通用工具函数
2. 指夹血氧/心率仪 HID 采集
3. 雷达数据处理
4. GUI 图形界面
```

如果仓库中只有一个主脚本，建议项目结构整理为：

```text
.
├── README.md
├── LICENSE
├── main_three_channel_vitals.py
├── requirements.txt
├── images/
│   └── cover.jpg
└── data/
    └── README.md
```

其中：

| 文件或目录 | 说明 |
|---|---|
| `main_three_channel_vitals.py` | 主程序，包含雷达采集、生命体征处理、GUI 和指夹仪读取 |
| `README.md` | 项目说明文档 |
| `LICENSE` | 开源许可证，建议使用 MIT License |
| `requirements.txt` | Python 依赖列表 |
| `images/` | README 配图、运行截图、实验结果图 |
| `data/` | 可选目录，用于存放示例数据或说明，不建议上传隐私数据 |

---

## 4. 软件环境

推荐环境：

```text
Python >= 3.9
Windows 10 / Windows 11
USB 串口驱动
可选：USB HID 指夹心率/血氧仪
```

主要依赖库：

```text
numpy
scipy
pyserial
matplotlib
hidapi
tkinter
```

其中：

- `numpy`：矩阵计算、FFT、数组处理；
- `scipy`：滤波器、峰值检测、MAT 文件保存；
- `pyserial`：串口通信；
- `matplotlib`：GUI 内嵌绘图；
- `hidapi`：USB HID 指夹仪读取；
- `tkinter`：图形界面，通常随 Python 自带。

安装依赖：

```bash
pip install numpy scipy pyserial matplotlib hidapi
```

如果不使用指夹心率/血氧仪，可以不安装 `hidapi`，雷达主流程仍然可以运行。

建议新增 `requirements.txt`：

```text
numpy
scipy
pyserial
matplotlib
hidapi
```

然后使用：

```bash
pip install -r requirements.txt
```

---

## 5. 硬件要求

本脚本默认使用如下硬件组合：

```text
1. 60GHz FMCW 雷达模块
2. 三接收通道输出
3. 串口输出原始雷达帧数据
4. PC 端 Python 程序实时解析
5. 可选 USB HID 指夹心率/血氧仪
```

默认雷达参数如下：

| 参数 | 默认值 |
|---|---:|
| 雷达中心频率 `f` | 60 GHz |
| 波长 `lambda` | 约 5 mm |
| 雷达带宽 `BW` | 4 GHz |
| ADC 采样率 `fs_adc` | 1 MHz |
| Chirp 重复周期 | 300 us |
| 帧周期 | 50 ms |
| 每帧 chirp 数 | 256 |
| 每个 chirp 采样点数 | 1 |
| 接收通道数 | 3 |
| 默认目标检测范围 | 0.20 m ~ 3.00 m |
| GUI 默认波特率 | 115200 |
| GUI 可选波特率 | 115200 / 921600 |

对应的慢时间采样率为：

```text
fs_signal = 1 / 0.05 = 20 Hz
```

也就是说，程序每 50 ms 接收一帧雷达数据，生命体征信号的慢时间采样率为 20 Hz。

---

## 6. 串口数据协议

### 6.1 帧同步标志

程序使用如下 8 字节序列作为雷达帧同步标志：

```text
00 01 02 03 04 05 06 07
```

程序启动时会调用 `_sync_header()`，逐字节搜索该同步序列。找到之后，认为雷达数据已经对齐。

每次读取一帧时，程序也会检查帧尾是否为：

```text
00 01 02 03 04 05 06 07
```

如果帧尾校验失败，会抛出异常：

```text
雷达帧尾校验失败
```

这通常说明以下问题之一：

```text
1. 串口波特率设置错误；
2. 雷达输出协议与脚本不一致；
3. 上位机读帧长度不对；
4. 串口中途丢字节；
5. 雷达没有输出原始数据；
6. 同步头/帧尾定义与实际固件不一致。
```

### 6.2 单帧长度

脚本中关键参数为：

```python
num_samples_per_chirp = 1
num_chirps_per_frame = 256
rx_antennas = [1, 1, 1]
```

每个采样点为 12bit，因此单通道数据长度为：

```text
1 × 256 × 12 / 8 = 384 bytes
```

三通道 payload 长度为：

```text
384 × 3 = 1152 bytes
```

再加上 8 字节帧尾，因此单帧总读取长度为：

```text
1152 + 8 = 1160 bytes
```

代码中对应：

```python
expected_len = sum(self.rx_antennas) * self.buffer_size + 8
```

---

## 7. 三通道 12bit 数据解码

脚本中的 `_decode_payload()` 用于将原始字节流解码成三路 12bit ADC 数据。

当前协议按照每 9 个字节解出 6 个 12bit 数据点，分别填入三接收通道的两行数据。

简化理解如下：

```text
9 bytes → 6 个 12bit 数据
       → Rx1 两个点
       → Rx2 两个点
       → Rx3 两个点
```

解码后的 `buffer` 形状为：

```text
[256, 3]
```

其中：

```text
第 1 列：Rx1
第 2 列：Rx2
第 3 列：Rx3
```

之后代码将三路数据 reshape 成：

```python
rx1 = buffer[:, 0].reshape((num_samples_per_chirp, num_chirps_per_frame), order='F')
rx2 = buffer[:, 1].reshape((num_samples_per_chirp, num_chirps_per_frame), order='F')
rx3 = buffer[:, 2].reshape((num_samples_per_chirp, num_chirps_per_frame), order='F')
```

当前默认 `num_samples_per_chirp = 1`，因此每一帧实际被整理为：

```text
Rx1: 1 × 256
Rx2: 1 × 256
Rx3: 1 × 256
```

随后构造：

```python
rx_frame = np.stack([rx1.T[:, 0], rx2.T[:, 0], rx3.T[:, 0]], axis=1)
```

得到：

```text
rx_frame: 256 × 3
```

这表示一帧中包含 256 个点，每个点有 3 个接收通道数据。

---

## 8. 雷达距离轴计算

脚本中的距离轴由以下参数计算：

```python
c = 3e8
f = 60e9
lambda_ = c / f
BW = 4e9
fs_adc = 1e6
chirp_repetition_time_s = 300e-06
num_chirps_per_frame = 256
```

最大距离：

```python
MaxRange = (fs_adc * c) / (2 * BW / chirp_repetition_time_s)
```

也可以写成：

```text
MaxRange = fs_adc × c / (2 × S)
```

其中调频斜率：

```text
S = BW / Tchirp
```

距离 bin 间隔：

```python
deltaR = MaxRange / num_chirps_per_frame
```

在默认参数下，距离轴大约覆盖：

```text
0 m ~ 11.25 m
```

每个距离 bin 间隔约为：

```text
11.25 / 256 ≈ 0.0439 m
```

需要注意的是，标准 FMCW 距离分辨率通常由带宽决定：

```text
ΔR = c / (2B)
```

当带宽为 4 GHz 时，理论距离分辨率约为：

```text
3e8 / (2 × 4e9) = 0.0375 m
```

脚本中的距离轴是按照当前数据组织方式和采样参数计算得到的工程距离轴。如果你更换雷达配置，需要重新核对 `BW`、`fs_adc`、`chirp_repetition_time_s` 和下位机输出协议。

---

## 9. Range-Time 数据构造

程序使用 `Rx_m` 缓存连续多帧三通道数据：

```text
Rx_m: 256 × T × 3
```

其中：

```text
256：每帧 256 个点
T：已经缓存的慢时间帧数
3：三个接收通道
```

每收到一帧数据，就在慢时间维度追加一列：

```python
self.Rx_m = np.concatenate([self.Rx_m, rx_frame[:, None, :]], axis=1)
```

为了避免内存无限增长，脚本设置最大缓存列数：

```python
max_columns = 600
```

在 50 ms 帧周期下，600 帧对应：

```text
600 × 0.05 s = 30 s
```

也就是说，程序最多缓存约 30 秒的历史雷达数据。

---

## 10. 距离维 FFT 与静态杂波抑制

### 10.1 距离维 FFT

程序对 `Rx_m` 的第 0 维做 256 点 FFT：

```python
rx_rpc_temp = np.fft.fftshift(np.fft.fft(self.Rx_m, 256, axis=0), axes=0)
```

随后取正距离半轴：

```python
posS = 129
rx_rpc = rx_rpc_temp[posS - 1:, :, :]
```

得到：

```text
rx_rpc: 128 × T × 3
```

其中：

```text
128：正距离 bin 数
T：慢时间帧数
3：接收通道数
```

### 10.2 静态杂波抑制

静态墙体、桌面、座椅、雷达外壳反射和人体静止散射，会形成较强的固定背景。程序采用慢时间均值扣除：

```python
clutter = np.mean(rx_rpc, axis=1, keepdims=True)
avg_all = rx_rpc - clutter
```

这相当于一个简单的静态背景消除方法。它可以压制不随时间变化的静态反射，突出呼吸、心跳、身体微动等时间变化成分。

该方法的优点是简单、稳定、计算量低。

缺点是：

```text
1. 需要一定长度的历史数据；
2. 人体长时间完全静止时，部分能量也可能被背景吸收；
3. 如果人体位置缓慢变化，背景估计会被污染；
4. 强体动后可能需要一段时间恢复稳定。
```

---

## 11. 目标距离门选择

程序通过 `_select_target_range_bin()` 选择人体所在距离门。

核心思路是：

```text
1. 取最近一段慢时间数据；
2. 对三个通道做非相干能量累加；
3. 只在 0.20 m ~ 3.00 m 范围内搜索目标；
4. 选择能量最大的距离门；
5. 如果上一帧目标距离门附近能量仍然足够强，则优先保持原距离门附近结果。
```

对应代码逻辑为：

```python
recent_len = min(140, avg_all.shape[1])
recent = avg_all[:, -recent_len:, :]
energy = np.sum(np.abs(recent), axis=(1, 2))

valid = (rax_plot >= target_range_min_m) & (rax_plot <= target_range_max_m)
masked_energy = np.where(valid, energy, 0.0)
candidate = int(np.argmax(masked_energy))
```

距离门稳定策略：

```python
if previous_range_bin is not None:
    search previous_range_bin ± 2
    if local_energy >= 0.65 × global_peak_energy:
        keep local bin
```

这样做的目的是避免目标在相邻距离 bin 之间来回跳变。生命体征检测非常依赖相位连续性，如果距离门频繁跳变，呼吸和心率波形会明显变差。

---

## 12. 三通道相位提取与融合

### 12.1 单通道相位提取

在选定目标距离门后，程序分别取三个接收通道的复数慢时间序列：

```python
z = avg_all[target_bin0, :, ch]
```

然后通过 `_preprocess_phase_from_complex()` 处理：

```text
复数信号 z
    ↓
angle(z)
    ↓
unwrap 相位解缠
    ↓
相位差分
    ↓
去中值
    ↓
MAD / 标准差限幅
    ↓
脉冲噪声抑制
    ↓
三点平滑
    ↓
输出相位微动序列
```

为什么要使用相位？

因为人体胸腔的微小径向位移会造成回波相位变化。相位变化与位移之间近似满足：

```text
x = λ × Δφ / (4π)
```

其中：

```text
x：径向位移
λ：雷达波长
Δφ：相位变化
```

对于 60GHz 雷达：

```text
λ = c / f ≈ 5 mm
```

因此，60GHz 雷达对毫米级胸腔运动非常敏感。

### 12.2 为什么要相位差分

脚本中没有直接使用原始 unwrap 相位，而是使用相位差分：

```python
dphi[1:] = np.diff(phase_tmp)
```

这样做可以削弱慢变漂移、静态相位偏置和低频趋势，使呼吸、心跳的周期变化更加突出。

但相位差分也有副作用：

```text
1. 会放大高频噪声；
2. 对异常跳变敏感；
3. 对低频呼吸趋势有一定削弱；
4. 需要后续平滑和滤波。
```

所以脚本随后加入了异常点抑制和轻平滑。

### 12.3 脉冲噪声抑制

脚本使用 `filter_remove_impulse_noise()` 检测孤立突变点。

基本逻辑是：

```text
如果中间点相对于前后点同时出现异常突变，
则用前后两点线性插值替代中间点。
```

这对串口异常、相位 unwrap 错误、体动尖峰有一定抑制作用。

### 12.4 三通道质量评估

每个通道会计算一个类似 SNR 的质量指标：

```python
snr_like = median(abs(target_bin_signal)) / median(abs(full_range_signal))
```

如果某个通道目标幅度较强、背景较低、相位波动有效，那么该通道权重较高。

### 12.5 三通道符号一致性校正

由于不同接收通道的相位方向可能存在符号差异，程序以质量最高通道为参考，计算其它通道与参考通道的相关性：

```python
corr = corrcoef(reference_phase, channel_phase)
```

如果相关系数小于 -0.15，则认为该通道相位方向反了：

```python
channel_phase[:, ch] *= -1.0
```

如果相关性过低，则降低该通道权重：

```python
q[ch] *= 0.45
```

### 12.6 加权融合

最后将三个通道按质量权重融合：

```python
fused = sum(channel_phase * weights)
```

输出：

```text
fused_phase：融合相位信号
channel_phase：三个通道各自相位信号
channel_weights：三个通道权重
```

三通道融合的目的不是简单提高幅度，而是提升相位信号的稳定性。对于生命体征检测来说，稳定的相位轨迹比瞬时强幅度更重要。

---

## 13. 呼吸率估计

呼吸估计函数为：

```python
_estimate_breath()
```

### 13.1 呼吸带通滤波

首先对融合相位做呼吸频带滤波：

```python
breath_signal = bandpass_filter_sos(fused_phase, fs_signal, (0.1, 0.5), order=2)
```

对应呼吸范围：

```text
0.1 Hz ~ 0.5 Hz
6 BPM ~ 30 BPM
```

### 13.2 FFT 主频估计

程序使用 `estimate_rate_fft_band()` 在指定频带内估计主频。

主要步骤：

```text
1. 去中值；
2. 标准差归一化；
3. Hann 加窗；
4. zero padding；
5. rFFT；
6. 限定呼吸频带；
7. 频谱平滑；
8. 寻找最大峰；
9. 抛物线插值；
10. 频率换算为 BPM。
```

频率换算公式：

```text
BPM = f × 60
```

### 13.3 峰间距辅助估计

除了 FFT，程序还使用 `estimate_breath_rate_peaks()` 从呼吸波形峰间距估计呼吸率。

基本思路：

```text
1. 在呼吸波形中寻找峰值；
2. 计算相邻峰之间的时间间隔；
3. 剔除异常间隔；
4. 用平均周期换算呼吸率。
```

换算公式：

```text
Breath_BPM = 60 / mean(peak_interval_seconds)
```

### 13.4 FFT 与峰值法融合

如果 FFT 估计和峰间距估计接近：

```text
|fft_bpm - peak_bpm| <= 4 BPM
```

则融合输出：

```text
raw_breath = 0.65 × fft_bpm + 0.35 × peak_bpm
```

如果只有 FFT 有效，则用 FFT。

如果只有峰值法有效，则用峰值法。

### 13.5 呼吸率稳定

呼吸率输出不是直接使用瞬时结果，而是经过 `_stabilize_breath_rate()` 稳定处理。

主要规则：

```text
1. 有效范围必须在 6 BPM ~ 30 BPM；
2. 频谱质量必须大于 1.6；
3. 低质量时短时间保持上一帧结果；
4. 相邻输出变化速度受限；
5. 使用最近几次结果的中值进行平滑。
```

这样可以避免呼吸率在 GUI 上剧烈跳动。

---

## 14. 心率估计

心率估计函数为：

```python
_estimate_heart()
```

心率比呼吸更难，主要原因是：

```text
1. 心跳位移幅度更小；
2. 呼吸谐波可能落入心率频带；
3. 体动会污染心率频带；
4. 多径会造成相位失真；
5. 距离门跳变会破坏相位连续性；
6. 不同接收通道质量差异明显。
```

### 14.1 心率带通滤波

程序对融合相位做心率频带滤波：

```python
heart_signal = bandpass_filter_sos(fused_phase, fs_signal, (0.8, 2.0), order=2)
```

对应心率范围：

```text
0.8 Hz ~ 2.0 Hz
48 BPM ~ 120 BPM
```

### 14.2 融合相位心率候选

程序首先从融合相位中估计一个心率候选：

```python
bpm, q, _ = estimate_rate_fft_band(heart_signal, fs_signal, (0.8, 2.0), min_seconds=8.0)
```

如果候选处于：

```text
45 BPM ~ 140 BPM
```

则加入候选列表，并给它较高权重：

```python
qualities.append(1.35 * q)
```

### 14.3 单通道心率候选

随后程序对三个接收通道分别估计心率候选：

```python
for ch in range(channel_phase.shape[1]):
    hs_ch = bandpass_filter_sos(channel_phase[:, ch], fs_signal, (0.8, 2.0), order=2)
    bpm_ch, q_ch, _ = estimate_rate_fft_band(hs_ch, fs_signal, (0.8, 2.0), min_seconds=8.0)
```

每个通道候选的质量权重由两部分决定：

```text
1. 该通道心率频谱质量；
2. 该通道在三通道融合中的权重。
```

对应代码：

```python
qualities.append(q_ch * (0.5 + 1.5 * channel_weights[ch]))
```

### 14.4 候选聚类

如果上一帧已有稳定心率，程序优先选择与上一帧接近的候选簇：

```text
|candidate - previous_heart_rate| <= 10 BPM
```

如果没有上一帧心率，则选择最高质量候选附近的簇：

```text
|candidate - best_candidate| <= 8 BPM
```

最终通过加权中值输出原始心率：

```python
raw_bpm = weighted_median(rates_arr[cluster], q_arr[cluster])
```

### 14.5 心率稳定

心率输出通过 `_stabilize_heart_rate()` 进行稳定。

主要规则：

```text
1. 呼吸率必须有效；
2. 心率必须在 45 BPM ~ 140 BPM；
3. 频谱质量必须大于 2.0；
4. 低质量时短时间保持上一帧；
5. 相邻帧变化速度受限；
6. 如果瞬时跳变超过 10 BPM，则强烈依赖上一帧；
7. 使用最近几次心率中值平滑。
```

这套规则能显著减少 GUI 上心率乱跳，但也会带来一定滞后。

---

## 15. 指夹心率/血氧仪读取

脚本支持通过 USB HID 读取指夹心率/血氧仪。

默认设备：

```python
VID = 0x28E9
PID = 0x028A
```

程序启动后，会创建 `FingerClipReader` 线程，尝试枚举该 VID/PID 的 HID 设备。

初始化时会发送两组初始化序列：

```text
SEQ_A
SEQ_B
```

并定期发送 keepalive：

```python
KEEPALIVE_INTERVAL = 5.0
KEEPALIVE_PAYLOAD64 = bytes.fromhex("9a1a" + "00" * 62)
```

程序支持解析几种数据头：

```text
0xEB：复合帧，可能包含心率和血氧
0xF3：心率候选
0xF0：血氧候选
```

其中 `parse_eb_frame()` 会解析：

```text
EB 01 05 ...
```

得到：

```text
HR：心率
SpO2：血氧
```

指夹仪数据会保存在：

```python
FingerState.hr
FingerState.spo2
FingerState.source
FingerState.last_update_time
```

GUI 中主要显示指夹心率，并计算：

```text
心率差值 = 雷达心率 - 指夹心率
```

如果没有接入指夹仪，GUI 会显示：

```text
心电仪心率: N/A
心率差值: N/A
```

雷达检测主流程不受影响。

---

## 16. GUI 界面说明

程序使用 Tkinter 构建 GUI，并嵌入 Matplotlib 画图。

窗口标题：

```text
60GHz单人雷达呼吸心率检测
```

默认窗口大小：

```text
1180 × 820
```

### 16.1 控制区

控制区包含：

```text
1. 串口选择；
2. 刷新串口；
3. 波特率选择；
4. 是否保存数据；
5. 保存按钮；
6. 开始按钮；
7. 结束按钮。
```

默认波特率：

```text
115200
```

可选波特率：

```text
115200
921600
```

### 16.2 指标显示区

GUI 顶部实时显示：

```text
最大距离门的索引
目标距离
呼吸
心率
心电仪心率
心率差值
```

### 16.3 图像显示区

GUI 包含四个子图：

```text
左上：时间距离谱
右上：雷达心率与心电仪心率对比
左下：呼吸波形
右下：心跳波形
```

#### 时间距离谱

由三通道 MTI 幅度融合得到：

```python
mti_mag = sqrt(sum(abs(avg_all)^2, axis=channel))
db_avg = safe_db(mti_mag)
```

显示范围默认为：

```text
距离：0 m ~ 5 m
颜色范围：40 dB ~ 130 dB
```

#### 呼吸波形

显示呼吸频带滤波后的融合相位信号：

```text
0.1 Hz ~ 0.5 Hz
```

#### 心跳波形

显示心率频带滤波后的融合相位信号：

```text
0.8 Hz ~ 2.0 Hz
```

#### 心率对比图

显示最近 30 秒内：

```text
雷达心率
指夹心率
```

用于观察雷达估计结果与参考设备之间的差异。

### 16.4 状态栏

状态栏会输出：

```text
串口搜索状态
雷达帧同步状态
心电仪连接状态
每次检测结果
异常信息
```

典型日志：

```text
[2026-xx-xx xx:xx:xx] 雷达帧头同步成功，开始实时检测。
[2026-xx-xx xx:xx:xx] 目标距离: 0.88 m   雷达呼吸: 16.20   雷达心率: 75.40   心电仪心率: 76.00   心率差值: -0.60
```

---

## 17. 数据保存

如果勾选：

```text
是否保存数据
```

程序会在每帧解包后保存：

```python
Rx1
Rx2
Rx3
```

点击“保存”后，会保存为 `.mat` 文件。

当前保存结构为：

```python
savemat(path, {
    "Radra_Data": {
        "Rx1": rx1_list,
        "Rx2": rx2_list,
        "Rx3": rx3_list
    }
})
```

注意：这里变量名是 `Radra_Data`，疑似 `Radar_Data` 的拼写错误。如果后续整理项目，建议统一改为：

```text
Radar_Data
```

MATLAB 中读取方式示例：

```matlab
data = load('your_saved_file.mat');
rx1 = data.Radra_Data.Rx1;
rx2 = data.Radra_Data.Rx2;
rx3 = data.Radra_Data.Rx3;
```

如果你修改为 `Radar_Data`，则对应：

```matlab
data = load('your_saved_file.mat');
rx1 = data.Radar_Data.Rx1;
rx2 = data.Radar_Data.Rx2;
rx3 = data.Radar_Data.Rx3;
```

---

## 18. 运行方法

### 18.1 克隆仓库

```bash
git clone https://github.com/rsptiaopig/60GHz-FMCW-Radar-Breath-And-Heart-Dection-MATLAB-Code.git
cd 60GHz-FMCW-Radar-Breath-And-Heart-Dection-MATLAB-Code
```

### 18.2 安装依赖

```bash
pip install numpy scipy pyserial matplotlib hidapi
```

### 18.3 运行程序

```bash
python main_three_channel_vitals.py
```

### 18.4 操作步骤

```text
1. 连接 60GHz 雷达模块；
2. 确认雷达正在通过串口输出原始数据；
3. 运行 Python 程序；
4. 点击“刷新串口”；
5. 选择雷达对应串口；
6. 选择正确波特率；
7. 如需保存数据，勾选“是否保存数据”；
8. 点击“开始”；
9. 等待雷达帧同步成功；
10. 保持人体在雷达前方 0.2 m ~ 3.0 m 范围内；
11. 尽量保持静止，观察呼吸和心率结果；
12. 如连接指夹仪，可观察雷达心率与指夹心率差值；
13. 结束采集后点击“保存”导出 .mat 数据。
```

---

## 19. 关键参数修改指南

### 19.1 串口参数

在 GUI 中可选择：

```text
115200
921600
```

如果你的雷达波特率不是这两个，需要修改：

```python
values=["115200", "921600"]
```

例如增加 460800：

```python
values=["115200", "460800", "921600"]
```

### 19.2 雷达基础参数

在 `MatlabStrictRadarProcessor.__init__()` 中修改：

```python
self.f = 60e9
self.BW = 4e9
self.fs_adc = 1e6
self.chirp_repetition_time_s = 300e-06
self.frame_repetition_time_s = 50e-03
self.num_samples_per_chirp = 1
self.num_chirps_per_frame = 256
```

如果雷达配置变化，这些参数必须同步修改。

### 19.3 目标距离范围

默认只在 0.20 m ~ 3.00 m 搜索人体：

```python
self.target_range_min_m = 0.20
self.target_range_max_m = 3.00
```

如果你的雷达安装距离更远，可以改为：

```python
self.target_range_min_m = 0.50
self.target_range_max_m = 5.00
```

但不建议范围过大，否则容易选到墙体、桌面、风扇、窗帘等干扰目标。

### 19.4 呼吸频带

默认呼吸频带：

```python
(0.1, 0.5)
```

如果需要覆盖更慢呼吸，可以改为：

```python
(0.08, 0.5)
```

如果只关注成人安静呼吸，可以使用：

```python
(0.12, 0.45)
```

### 19.5 心率频带

默认心率频带：

```python
(0.8, 2.0)
```

对应：

```text
48 BPM ~ 120 BPM
```

如果需要覆盖更高心率，例如运动后心率，可以改为：

```python
(0.8, 2.5)
```

对应：

```text
48 BPM ~ 150 BPM
```

但心率频带越宽，越容易引入噪声和呼吸谐波。

### 19.6 缓存长度

最大缓存帧数：

```python
self.max_columns = 600
```

在 20 Hz 慢时间采样率下，对应 30 秒数据。

如果希望响应更快，可以减小窗口，例如：

```python
self.max_columns = 400
```

对应 20 秒。

如果希望频率估计更稳定，可以增大窗口，例如：

```python
self.max_columns = 800
```

对应 40 秒。

需要注意：窗口越长，频率分辨率越好，但响应越慢。

---

## 20. 常见问题

### 20.1 找不到串口

可能原因：

```text
1. 雷达没有连接；
2. USB 转串口驱动未安装；
3. 串口被其它软件占用；
4. 数据线只支持充电，不支持通信；
5. 设备管理器中串口异常。
```

解决方法：

```text
1. 检查设备管理器；
2. 重新插拔雷达；
3. 关闭串口助手；
4. 更换 USB 数据线；
5. 点击“刷新串口”。
```

### 20.2 雷达帧尾校验失败

可能原因：

```text
1. 波特率错误；
2. 雷达数据协议不一致；
3. 帧长度计算错误；
4. 雷达没有输出当前脚本期望的原始数据；
5. 串口丢包；
6. 下位机帧尾不是 00 01 02 03 04 05 06 07。
```

排查建议：

```text
1. 用串口助手抓一帧原始数据；
2. 确认帧尾标志；
3. 确认每帧 payload 字节数；
4. 确认是否三通道交织；
5. 确认是否 12bit 打包；
6. 确认波特率与下位机一致。
```

### 20.3 时间距离谱没有目标

可能原因：

```text
1. 雷达未正确输出数据；
2. 距离轴参数错误；
3. 人体不在 0.20 m ~ 3.00 m 范围内；
4. 雷达方向没有对准胸腔；
5. 静态杂波扣除后目标太弱；
6. 数据解包通道顺序错误。
```

建议：

```text
1. 先靠近雷达测试；
2. 将 target_range_max_m 临时调大；
3. 检查 mti_db 是否有明显能量带；
4. 检查 Rx1/Rx2/Rx3 原始波形是否正常；
5. 确认雷达天线朝向。
```

### 20.4 呼吸率为 0

可能原因：

```text
1. 缓存时间不足；
2. 呼吸频谱质量低于阈值；
3. 人体距离门选错；
4. 呼吸太浅；
5. 人体移动过大；
6. 雷达没有对准胸腹部。
```

脚本中呼吸 FFT 至少需要：

```text
min_seconds = 12 s
```

因此刚启动时呼吸率可能暂时为 0，这是正常现象。

### 20.5 心率不稳定

心率不稳定是雷达生命体征检测中最常见的问题。

可能原因：

```text
1. 心跳信号本身很弱；
2. 呼吸谐波进入心率频带；
3. 人体有体动；
4. 衣物较厚；
5. 雷达角度不合适；
6. 目标距离门跳变；
7. 三通道相位质量差异大；
8. 环境多径严重；
9. 指夹仪自身延迟与雷达不同步。
```

建议：

```text
1. 人体尽量正对雷达；
2. 保持 0.5 m ~ 1.5 m 测试距离；
3. 先让呼吸稳定，再观察心率；
4. 使用指夹仪对比时，不要要求两者秒级完全一致；
5. 观察心率波形是否存在明显周期；
6. 观察 channel_weights，判断是否某个通道质量明显较好；
7. 增加相位圆拟合、呼吸谐波抑制等算法。
```

### 20.6 雷达心率与指夹心率有延迟

这是正常现象。

原因包括：

```text
1. 雷达算法使用滑动窗口；
2. 心率稳定器限制了跳变速度；
3. 指夹仪本身也有平滑；
4. 两个设备采样位置不同；
5. 雷达测的是胸壁微动，指夹仪测的是末梢血氧脉搏。
```

因此，评估时不要只看瞬时差值，更应该看一段时间内的平均误差和趋势一致性。

### 20.7 GUI 卡顿

可能原因：

```text
1. Matplotlib 每次 clear + redraw 开销较大；
2. 日志输出过多；
3. 数据窗口过长；
4. 电脑性能较低；
5. 串口数据量较大。
```

优化方向：

```text
1. 减少绘图刷新频率；
2. 不要每次 clear 全部坐标轴；
3. 使用 set_data 更新曲线；
4. 限制状态栏日志行数；
5. 将绘图和计算进一步解耦。
```

---

## 21. 当前脚本的工程特点

这个脚本不是一个最小 demo，而是一个接近实验工具的完整原型。它包含：

```text
1. 在线采集；
2. 雷达解包；
3. 实时处理；
4. 三通道融合；
5. 结果稳定；
6. 指夹仪对比；
7. GUI 显示；
8. MAT 数据保存。
```

相比简单的单通道 FFT 示例，它更接近真实实验流程。

但当前脚本也有一些工程上可以继续整理的地方：

```text
1. 参数较多，建议迁移到 config.yaml；
2. GUI、雷达处理、HID 读取耦合在一个文件中；
3. 建议拆分为 radar_processor.py、finger_reader.py、app.py；
4. 建议增加离线回放模式；
5. 建议增加日志等级；
6. 建议增加 requirements.txt；
7. 建议统一变量命名；
8. 建议修正 Radra_Data 拼写；
9. 建议补充原始数据协议说明图；
10. 建议增加示例运行截图。
```

---

## 22. 后续优化方向

### 22.1 增加离线回放模式

当前程序主要面向在线串口分析。建议增加：

```text
load .mat
    ↓
按帧回放
    ↓
复用同一套处理算法
    ↓
输出呼吸/心率曲线
```

这样可以避免每次调算法都必须连接雷达。

### 22.2 增加配置文件

建议把以下参数放入配置文件：

```text
串口波特率
雷达中心频率
带宽
采样率
chirp 周期
帧周期
目标距离范围
呼吸频带
心率频带
保存路径
HID VID/PID
```

例如：

```yaml
radar:
  center_frequency: 60e9
  bandwidth: 4e9
  adc_fs: 1e6
  frame_period: 0.05
  min_range: 0.2
  max_range: 3.0

vitals:
  breath_band: [0.1, 0.5]
  heart_band: [0.8, 2.0]
```

### 22.3 增加相位圆拟合

当前脚本使用均值扣除和相位差分。后续可以增加圆拟合去 DC：

```text
I/Q 轨迹
    ↓
圆拟合估计 DC 偏置
    ↓
I/Q 去中心
    ↓
相位提取
```

这对零中频接收机、静态泄漏、I/Q 偏置有帮助。

### 22.4 增加呼吸谐波抑制

呼吸信号很强，二次谐波、三次谐波可能落入心率频带，干扰心率估计。

可以增加：

```text
1. 根据呼吸率预测谐波位置；
2. 在心率频谱中削弱呼吸谐波附近峰；
3. 结合上一帧心率做连续性判断；
4. 结合指夹仪数据验证算法效果。
```

### 22.5 增加体动检测

体动会严重破坏心率估计。可以增加体动指标：

```text
1. 目标距离门跳变；
2. 相位差分异常能量；
3. 宽频能量突然升高；
4. 时间距离谱大面积变化；
5. 多通道相位相关性下降。
```

当体动发生时，可以暂停心率更新，只保持上一稳定值。

### 22.6 增加多通道相干波束形成

当前脚本主要在目标距离门做三通道相位融合。后续可以进一步加入：

```text
1. DBF 角度扫描；
2. 目标角度估计；
3. 目标方向相干合成；
4. 距离-角度谱显示；
5. 多目标分离。
```

这可以提高多人场景下的扩展能力。

---

## 23. 免责声明

本项目仅用于雷达信号处理学习、科研实验和工程验证。

本项目输出的呼吸率、心率、血氧或其它生命体征信息不具备医疗诊断效力，不能用于疾病诊断、治疗决策、健康风险判断或任何临床用途。

使用者需要自行确认：

```text
1. 雷达硬件安全；
2. 电磁合规；
3. 数据隐私；
4. 实验伦理；
5. 开源代码合规；
6. 所使用硬件与协议的一致性。
```

---

## 24. License

建议使用 MIT License。

如果仓库已经包含 `LICENSE` 文件，请以仓库中的许可证为准。

---

## 25. 致谢

本项目用于 60GHz FMCW 雷达生命体征检测学习和实验验证。欢迎基于本项目继续改进：

```text
1. 更稳定的呼吸率检测；
2. 更鲁棒的心率估计；
3. 更清晰的数据协议说明；
4. 更完整的离线数据集；
5. 更规范的工程结构；
6. 更适合嵌入式移植的算法版本。
```
