"""Python twin of the firmware gas anomaly detector.

firmware/phone_board/lib/anomaly/anomaly.c is the reference; this file mirrors it
statement for statement so a logged survey can be replayed sample by sample
through exactly the logic the board runs. Settings come from the same header,
anomaly_config.h, so the two can never disagree on a number. After any change to
either file, run `python tools/replay.py parity`.

Everything here is causal: each output depends only on the current and earlier
samples. No GPS-derived quantity is an input, and no gas channel is ever used to
predict another.

Channels: 2 on rev B/E logs (ch4, lpg), 4 on rev F logs (plus mems_a, mems_b),
inferred from the inputs. The firmware fixes the count at compile time
(ANOM_NCH); here a Detector is built for 2 or 4.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
CONFIG_H = REPO / "firmware" / "phone_board" / "lib" / "anomaly" / "anomaly_config.h"

CH4, LPG, MEMS_A, MEMS_B = 0, 1, 2, 3
NCH = 2          # rev B/E, and the default
MAX_NCH = 4      # rev F
CHANNEL_NAMES = ("ch4", "lpg", "mems_a", "mems_b")   # fixed order everywhere
CHANNELS = CHANNEL_NAMES[:NCH]   # the rev B/E pair, as older scripts expect
COEF_KEYS = ("ANOM_COEF_CH4", "ANOM_COEF_LPG", "ANOM_COEF_MEMS_A", "ANOM_COEF_MEMS_B")
# Settings held per channel in anomaly_config.h as NAME_CH arrays.
PER_CHANNEL = ("ANOM_K_ON", "ANOM_K_OFF", "ANOM_K_HOLD", "ANOM_K_RAISE", "ANOM_SUSTAIN_S",
               "ANOM_SIGMA_FLOOR_MV")

FEATURES = (
    "bias", "dT", "dAH", "dT_rate", "dAH_rate", "dT_slow",
    "air", "air_s1", "air_s2", "co",
)
NFEAT = len(FEATURES)
(F_BIAS, F_DT, F_DAH, F_DT_RATE, F_DAH_RATE, F_DT_SLOW,
 F_AIR, F_AIR_S1, F_AIR_S2, F_CO) = range(NFEAT)

CLASS_NAMES = ("", "NATURAL_GAS", "EXHAUST", "HEAVY_HC", "THERMAL",
               "LOW_AIRFLOW", "UNRESOLVED", "UNCLASSIFIED")
(C_NONE, C_NATURAL_GAS, C_EXHAUST, C_HEAVY_HC, C_THERMAL,
 C_LOW_AIRFLOW, C_UNRESOLVED, C_UNCLASSIFIED) = range(len(CLASS_NAMES))

MAD_SCALE = 1.4826

_DEFINE = re.compile(r"^\s*#define\s+(ANOM_\w+)\s+(.+?)\s*(//.*)?$")


def load_config(path: Path = CONFIG_H) -> dict:
    """Parse the `#define ANOM_*` lines of anomaly_config.h into a dict.

    Per-channel settings come as NAME_CH lists. For older scripts each also gets a
    scalar NAME holding channel 0's value; the detector reads only the lists, so
    change a setting with set_param() (or replay.cfg_with), never the scalar.
    """
    cfg: dict = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _DEFINE.match(line)
        if not m:
            continue
        name, val = m.group(1), m.group(2).strip()
        if val.startswith("{"):
            cfg[name] = [float(x) for x in val.strip("{} ").split(",")]
        else:
            cfg[name] = float(val) if any(ch in val for ch in ".eE") else int(val)
    for key in ("ANOM_USE_AIRFLOW", "ANOM_USE_CO", "ANOM_USE_RLS"):
        cfg.setdefault(key, 0)
    for name in PER_CHANNEL:
        cfg[name] = cfg[name + "_CH"][0]
    return cfg


def set_param(cfg: dict, name: str, value, channels=None) -> None:
    """Set a setting in place. A per-channel one (PER_CHANNEL) is set on the given
    channel indices, or on all of them."""
    if name in PER_CHANNEL:
        arr = list(cfg[name + "_CH"])
        for k in (range(len(arr)) if channels is None else channels):
            arr[k] = value
        cfg[name + "_CH"] = arr
        cfg[name] = arr[0]
    else:
        cfg[name] = value


def nch_of(inputs: dict) -> int:
    """Channel count of a replay input: 4 when it carries the MEMS channels."""
    return MAX_NCH if "mems_a_mv" in inputs else NCH


def abs_humidity(temp_c: float, rh_pct: float) -> float:
    es = 6.112 * math.exp(17.67 * temp_c / (temp_c + 243.5))
    return es * rh_pct * 2.1674 / (273.15 + temp_c)


def alpha(dt_s: float, tau_s: float) -> float:
    return 1.0 - math.exp(-dt_s / tau_s)


def clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


# ---- Thermistor airflow index -------------------------------------------------------

@dataclass
class Thermistor:
    supply_mv: float = 3300.0
    series_ohm: float = 1000.0   # as the firmware's AIRFLOW_BEAD_DEFAULT
    r25_ohm: float = 1000.0
    beta_k: float = 3950.0
    g_still_mw_k: float = 0.0
    min_rise_k: float = 0.2


def thermistor_temp_c(th: Thermistor, v_mv: float) -> float:
    r = th.series_ohm * v_mv / (th.supply_mv - v_mv)
    return 1.0 / (1.0 / 298.15 + math.log(r / th.r25_ohm) / th.beta_k) - 273.15


def thermistor_conductance(th: Thermistor, v_mv: float, ambient_c: float):
    if not (v_mv > 10.0) or not (v_mv < th.supply_mv - 10.0):
        return 0.0, False
    r = th.series_ohm * v_mv / (th.supply_mv - v_mv)
    p_mw = v_mv * v_mv / (r * 1000.0)
    rise = thermistor_temp_c(th, v_mv) - ambient_c
    if not (rise > th.min_rise_k):
        return 0.0, False
    return p_mw / rise, True


def airflow_index(th: Thermistor, v_mv: float, ambient_c: float):
    g, ok = thermistor_conductance(th, v_mv, ambient_c)
    if not ok or not (th.g_still_mw_k > 0.0):
        return 0.0, False
    return g / th.g_still_mw_k - 1.0, True


# ---- Detector -------------------------------------------------------------------------

@dataclass
class Event:
    id: int = 0
    cls: int = C_NONE
    confidence: int = 0
    t_start_ms: int = 0
    t_end_ms: int = 0
    peak_res_mv: list = field(default_factory=lambda: [0.0, 0.0])
    peak_sigma: list = field(default_factory=lambda: [0.0, 0.0])
    t_peak_ms: list = field(default_factory=lambda: [0, 0])
    raised: list = field(default_factory=lambda: [0, 0])
    detected: list = field(default_factory=lambda: [0, 0])
    ratio: float = 0.0
    lead_s: float = 0.0
    lead_known: int = 0
    thermal: int = 0
    airflow_known: int = 0
    airflow_mean: float = 0.0
    airflow_min: float = 0.0
    low_airflow: int = 0
    co_known: int = 0
    co_peak_ppm: float = 0.0

    @property
    def class_name(self) -> str:
        return CLASS_NAMES[self.cls]

    @classmethod
    def for_channels(cls, nch: int) -> "Event":
        return cls(peak_res_mv=[0.0] * nch, peak_sigma=[0.0] * nch, t_peak_ms=[0] * nch,
                   raised=[0] * nch, detected=[0] * nch)

    def as_dict(self) -> dict:
        d = {
            "event_id": self.id, "class": self.class_name, "confidence": self.confidence,
            "t_start_ms": self.t_start_ms, "t_end_ms": self.t_end_ms,
            "duration_s": (self.t_end_ms - self.t_start_ms) / 1000.0,
        }
        # Grouped by field, channels in order (ch4, lpg[, mems_a, mems_b]).
        names = CHANNEL_NAMES[:len(self.peak_res_mv)]
        for key, vals in (("peak_res_mv", self.peak_res_mv), ("peak_sigma", self.peak_sigma),
                          ("t_peak_ms", self.t_peak_ms), ("raised", self.raised),
                          ("detected", self.detected)):
            for ch, v in zip(names, vals):
                d[f"{ch}_{key}"] = v
        d.update({
            "ratio": self.ratio, "lead_s": self.lead_s if self.lead_known else None,
            "thermal": self.thermal,
            "airflow_mean": self.airflow_mean if self.airflow_known else None,
            "airflow_min": self.airflow_min if self.airflow_known else None,
            "low_airflow": self.low_airflow if self.airflow_known else None,
            "co_peak_ppm": self.co_peak_ppm if self.co_known else None,
        })
        return d


class _Channel:
    def __init__(self, cfg: dict):
        self.started = False
        self.start_ms = 0
        self.last_ms = 0
        self.base = 0.0
        self.freeze_s = 0.0
        self.res_ref = 0.0
        self.ring = np.zeros(cfg["ANOM_SIGMA_N"])
        self.ring_head = 0
        self.ring_count = 0
        self.sigma = 0.0
        self.sigma_ok = False
        self.run_start_ms = 0
        self.in_run = False
        self.active = False
        self.above_lead = False
        self.lead_cross_ms = 0
        self.coef = None
        self.P = None


class Detector:
    """One board's detector state, for nch = 2 or 4 gas channels. step() takes one
    sample and returns a dict."""

    def __init__(self, cfg: dict | None = None, nch: int = NCH):
        if not NCH <= nch <= MAX_NCH:
            raise ValueError(f"nch must be {NCH}..{MAX_NCH}")
        self.cfg = cfg if cfg is not None else load_config()
        self.nch = nch
        c = self.cfg
        self.coef_shared = [list(map(float, c[COEF_KEYS[k]])) for k in range(nch)]
        # Per-channel settings, as the C file-scope arrays.
        self.k_on = [float(x) for x in c["ANOM_K_ON_CH"][:nch]]
        self.k_off = [float(x) for x in c["ANOM_K_OFF_CH"][:nch]]
        self.k_hold = [float(x) for x in c["ANOM_K_HOLD_CH"][:nch]]
        self.k_raise = [float(x) for x in c["ANOM_K_RAISE_CH"][:nch]]
        self.sigma_floor = [float(x) for x in c["ANOM_SIGMA_FLOOR_MV_CH"][:nch]]
        self.sustain_ms = [int(float(x) * 1000.0) for x in c["ANOM_SUSTAIN_S_CH"][:nch]]
        self.next_event_id = 1
        self._restart()

    def _restart(self) -> None:
        c = self.cfg
        self.started = False
        self.last_t_ms = 0
        self.start_t_ms = 0
        self.n_valid = 0
        self.t_base = self.ah_base = self.dt_slow = 0.0
        self.air_s1 = self.air_s2 = 0.0
        self.air_started = False
        self.co_base = 0.0
        self.co_started = False
        self.rate_ring = [(0, 0.0, 0.0)] * c["ANOM_RATE_RING"]
        self.rate_head = 0
        self.rate_count = 0
        self.suppress_until_ms = 0
        self.suppress_armed = False
        self.last_step_ms = 0
        self.step_seen = False
        self.ch = [self._channel_reset(k) for k in range(self.nch)]
        self.ev_open = False
        self.ev_last_active_ms = 0
        self.ev = Event.for_channels(self.nch)
        self.ev_peak_known = [False] * self.nch
        self.ev_onset_known = [False] * self.nch
        self.ev_onset_ms = [0] * self.nch
        self.ev_air_sum = 0.0
        self.ev_air_n = 0
        self.ev_air_all_low = True

    # -- helpers mirroring the C statics
    def _channel_reset(self, k: int) -> _Channel:
        c = self.cfg
        ch = _Channel(c)
        if c["ANOM_USE_RLS"]:
            ch.coef = list(self.coef_shared[k])
            ch.P = [[c["ANOM_RLS_P0"] if i == j else 0.0 for j in range(NFEAT)] for i in range(NFEAT)]
        return ch

    def _update_sigma(self, ch: _Channel, floor: float) -> None:
        n = ch.ring_count
        if n < self.cfg["ANOM_SIGMA_MIN_N"]:
            return
        vals = ch.ring[:n]  # ring order does not matter for a median
        k = n // 2
        med = np.partition(vals, k)[k]
        mad = np.partition(np.abs(vals - med), k)[k]
        sig = MAD_SCALE * float(mad)
        ch.sigma = sig if sig > floor else float(floor)
        ch.sigma_ok = True

    def _ring_push(self, ch: _Channel, r: float) -> None:
        n = self.cfg["ANOM_SIGMA_N"]
        ch.ring[ch.ring_head] = r
        ch.ring_head = (ch.ring_head + 1) % n
        if ch.ring_count < n:
            ch.ring_count += 1

    def _rls_update(self, ch: _Channel, x, target: float, w0) -> None:
        c = self.cfg
        lam = c["ANOM_RLS_LAMBDA"]
        e = target
        for i in range(NFEAT):
            e -= ch.coef[i] * x[i]
        denom = lam
        px = [0.0] * NFEAT
        for i in range(NFEAT):
            acc = 0.0
            for j in range(NFEAT):
                acc += ch.P[i][j] * x[j]
            px[i] = acc
            denom += x[i] * px[i]
        k = [px[i] / denom for i in range(NFEAT)]
        for i in range(1, NFEAT):
            lim = c["ANOM_RLS_MAX_REL"] * abs(w0[i])
            ch.coef[i] = clamp(ch.coef[i] + k[i] * e, w0[i] - lim, w0[i] + lim)
        for i in range(NFEAT):
            for j in range(NFEAT):
                ch.P[i][j] = (ch.P[i][j] - k[i] * px[j]) / lam

    def _classify(self, ev: Event) -> None:
        """Classification and confidence use channels 0 and 1 (CH4, LPG) only."""
        c = self.cfg
        for k in range(self.nch):
            ev.raised[k] = int(bool(ev.detected[k]) or ev.peak_sigma[k] >= self.k_raise[k])
        denom = ev.peak_res_mv[LPG]
        if denom < self.sigma_floor[LPG]:
            denom = self.sigma_floor[LPG]
        ev.ratio = clamp(ev.peak_res_mv[CH4] / denom, 0.0, 99.0)

        s0 = (ev.peak_sigma[CH4] - self.k_on[CH4]) / self.k_on[CH4]
        s1 = (ev.peak_sigma[LPG] - self.k_on[LPG]) / self.k_on[LPG]
        strength = clamp(s0 if s0 > s1 else s1, 0.0, 1.0)
        detect_conf = 0.5 + 0.5 * strength
        margin = 1.0

        both = ev.raised[CH4] and ev.raised[LPG]
        co_rise = bool(ev.co_known) and ev.co_peak_ppm > c["ANOM_CO_RISE_PPM"]
        if ev.thermal:
            cls = C_THERMAL
        elif both:
            if co_rise:
                cls = C_EXHAUST
            elif ev.ratio <= c["ANOM_HEAVY_RATIO_MAX"]:
                cls = C_HEAVY_HC
                margin = 0.5 + 0.5 * clamp(1.0 - ev.ratio / c["ANOM_HEAVY_RATIO_MAX"], 0.0, 1.0)
            elif (c["ANOM_NG_BAND_VALID"] and c["ANOM_NG_RATIO_LO"] <= ev.ratio <= c["ANOM_NG_RATIO_HI"]
                  and ((ev.co_known and not co_rise) or c["ANOM_NG_WITHOUT_CO"])):
                cls = C_NATURAL_GAS
                lo = c["ANOM_NG_RATIO_LO"] if c["ANOM_NG_RATIO_LO"] > 0.01 else 0.01
                hi = c["ANOM_NG_RATIO_HI"] if c["ANOM_NG_RATIO_HI"] > lo else lo * 1.01
                half = 0.5 * math.log(hi / lo)
                off = abs(math.log(ev.ratio if ev.ratio > lo else lo) - 0.5 * math.log(hi * lo))
                margin = 0.5 + 0.5 * clamp(1.0 - off / half, 0.0, 1.0)
            elif ev.low_airflow:
                cls = C_LOW_AIRFLOW
            else:
                cls = C_UNRESOLVED
        elif ev.raised[LPG]:
            cls = C_HEAVY_HC
        elif ev.low_airflow:
            cls = C_LOW_AIRFLOW
        else:
            cls = C_UNCLASSIFIED
        ev.cls = cls
        ev.confidence = int(100.0 * detect_conf * margin + 0.5)

    # -- the step
    def step(self, t_ms: int, ch4_mv: float, lpg_mv: float, temp_c: float, rh_pct: float,
             valid: bool = True, airflow_index: float = 0.0, airflow_ok: bool = False,
             co_ppm: float = 0.0, co_ok: bool = False, extra_mv=(), extra_ok=()) -> dict | None:
        """Process one sample. Returns None for an invalid sample (the C output is all zero).

        extra_mv / extra_ok: readings and validity of channels 2 and up (mems_a,
        mems_b), as many as the detector has beyond the first two. Channels 0 and 1
        follow `valid` alone.
        """
        c = self.cfg
        if not valid:
            return None
        t = int(t_ms)
        nch = self.nch
        gas = (float(ch4_mv), float(lpg_mv)) + tuple(float(x) for x in extra_mv[:nch - 2])
        ch_ok = (True, True) + tuple(bool(x) for x in extra_ok[:nch - 2])
        if self.started and t - self.last_t_ms > c["ANOM_GAP_RESET_MS"]:
            self._restart()

        ah = abs_humidity(temp_c, rh_pct)
        dt = 0.0
        if not self.started:
            self.started = True
            self.start_t_ms = t
            self.t_base = temp_c
            self.ah_base = ah
            self.dt_slow = 0.0
        else:
            dt = (t - self.last_t_ms) / 1000.0
            if dt < 0.0:
                dt = 0.0
        self.last_t_ms = t
        self.n_valid += 1

        a_base = alpha(dt, c["ANOM_TAU_BASE_S"])
        self.t_base += a_base * (temp_c - self.t_base)
        self.ah_base += a_base * (ah - self.ah_base)
        d_t = temp_c - self.t_base
        d_ah = ah - self.ah_base
        self.dt_slow += alpha(dt, c["ANOM_TAU_T_SLOW_S"]) * (d_t - self.dt_slow)

        ring_n = c["ANOM_RATE_RING"]
        self.rate_ring[self.rate_head] = (t, temp_c, ah)
        self.rate_head = (self.rate_head + 1) % ring_n
        if self.rate_count < ring_n:
            self.rate_count += 1
        t_rate = ah_rate = 0.0
        for i in range(1, self.rate_count):
            rt, rT, rA = self.rate_ring[(self.rate_head + ring_n - 1 - i) % ring_n]
            age = t - rt
            if age >= c["ANOM_RATE_WINDOW_MS"]:
                span = age / 1000.0
                t_rate = (temp_c - rT) / span
                ah_rate = (ah - rA) / span
                break

        air = air_s1 = air_s2 = co_dev = 0.0
        air_ok_used = co_ok_used = False
        if c["ANOM_USE_AIRFLOW"] and airflow_ok:
            air_ok_used = True
            air = float(airflow_index)
            if not self.air_started:
                self.air_started = True
                self.air_s1 = self.air_s2 = air
            else:
                self.air_s1 += alpha(dt, c["ANOM_AIR_TAU1_S"]) * (air - self.air_s1)
                self.air_s2 += alpha(dt, c["ANOM_AIR_TAU2_S"]) * (air - self.air_s2)
            air_s1, air_s2 = self.air_s1, self.air_s2
        if c["ANOM_USE_CO"] and co_ok:
            co_ok_used = True
            if not self.co_started:
                self.co_started = True
                self.co_base = float(co_ppm)
            else:
                self.co_base += alpha(dt, c["ANOM_TAU_CO_BASE_S"]) * (co_ppm - self.co_base)
            co_dev = co_ppm - self.co_base

        f = [1.0, d_t, d_ah, t_rate, ah_rate, self.dt_slow, air, air_s1, air_s2, co_dev]

        tr, ar = abs(t_rate), abs(ah_rate)
        if tr > c["ANOM_STEP_T_RATE"] or ar > c["ANOM_STEP_AH_RATE"]:
            self.suppress_until_ms = t + int(c["ANOM_SUPPRESS_S"] * 1000.0)
            self.suppress_armed = True
        suppressed = self.suppress_armed and self.suppress_until_ms - t > 0
        if tr > c["ANOM_THERMAL_T_RATE"] or ar > c["ANOM_THERMAL_AH_RATE"]:
            self.last_step_ms = t
            self.step_seen = True

        ready = (t - self.start_t_ms >= int(c["ANOM_SETTLE_S"] * 1000.0)
                 and self.ch[0].sigma_ok and self.ch[1].sigma_ok)

        k_lead = c["ANOM_K_LEAD"]
        hp_tau = c["ANOM_RES_HP_TAU_S"]
        gap_ms = c["ANOM_GAP_RESET_MS"]
        settle_ms = int(c["ANOM_SETTLE_S"] * 1000.0)
        out = {"ready": ready, "feat": f, "target": [0.0] * nch, "pred": [0.0] * nch,
               "model_res": [0.0] * nch, "res": [0.0] * nch, "sigma": [0.0] * nch,
               "exceed": [False] * nch, "anomaly": [False] * nch, "ch_valid": [False] * nch,
               "ch_ready": [False] * nch, "suppressed": suppressed,
               "event_open": False, "event": None}
        for k in range(nch):
            ch = self.ch[k]
            # Channels 0 and 1 follow `valid` (already checked); later ones need their flag.
            if k > LPG and not ch_ok[k]:
                ch.in_run = False
                ch.active = False
                ch.above_lead = False
                continue
            # Per-channel start and gap restart (always in step with the detector-wide
            # start for channels 0 and 1).
            if ch.started and t - ch.last_ms > gap_ms:
                ch = self.ch[k] = self._channel_reset(k)
            dt_c = 0.0
            if not ch.started:
                ch.started = True
                ch.start_ms = t
                ch.base = gas[k]
                if k > LPG:
                    # A MEMS channel usually starts after its warm-up, when the
                    # conditions features are no longer zero: start its baseline where
                    # the conditions model puts it (reading minus the non-bias part of
                    # the prediction). Conditions only, never another channel.
                    w0 = self.coef_shared[k]
                    p = 0.0
                    for i in range(F_BIAS + 1, NFEAT):
                        p += w0[i] * f[i]
                    ch.base -= p
            else:
                dt_c = (t - ch.last_ms) / 1000.0
                if dt_c < 0.0:
                    dt_c = 0.0
            ch.last_ms = t
            c_ready = ready
            if k > LPG:
                c_ready = ready and t - ch.start_ms >= settle_ms and ch.sigma_ok
            k_on, k_off = self.k_on[k], self.k_off[k]
            w = ch.coef if c["ANOM_USE_RLS"] else self.coef_shared[k]
            target = gas[k] - ch.base
            pred = 0.0
            for i in range(NFEAT):
                pred += w[i] * f[i]
            model_res = target - pred
            res = model_res
            if hp_tau > 0:
                res = model_res - ch.res_ref
            sig = ch.sigma
            exceed = c_ready and res > k_on * sig

            if exceed and not suppressed:
                if not ch.in_run:
                    ch.in_run = True
                    ch.run_start_ms = t
            else:
                ch.in_run = False
            if ch.active:
                if not (c_ready and res > k_off * sig):
                    ch.active = False
            elif ch.in_run and t - ch.run_start_ms >= self.sustain_ms[k]:
                ch.active = True
            above = c_ready and res > k_lead * sig
            if above and not ch.above_lead:
                ch.lead_cross_ms = t
            ch.above_lead = above

            hold = exceed or ch.active or (c_ready and res > self.k_hold[k] * sig)
            learn = True
            if not hold:
                ch.base += alpha(dt_c, c["ANOM_TAU_BASE_S"]) * (gas[k] - ch.base)
                if hp_tau > 0:
                    ch.res_ref += alpha(dt_c, hp_tau) * (model_res - ch.res_ref)
                ch.freeze_s = 0.0
            else:
                ch.freeze_s += dt_c
                if ch.freeze_s > c["ANOM_FREEZE_MAX_S"]:
                    ch.base += alpha(dt_c, c["ANOM_TAU_RESUME_S"]) * (gas[k] - ch.base)
                    if hp_tau > 0:
                        ch.res_ref += alpha(dt_c, c["ANOM_TAU_RESUME_S"]) * (model_res - ch.res_ref)
                else:
                    learn = False
            if learn:
                self._ring_push(ch, res)
            if c["ANOM_USE_RLS"] and not hold and c_ready:
                self._rls_update(ch, f, target, self.coef_shared[k])

            out["ch_valid"][k] = True
            out["ch_ready"][k] = c_ready
            out["target"][k] = target
            out["pred"][k] = pred
            out["model_res"][k] = model_res
            out["res"][k] = res
            out["sigma"][k] = sig
            out["exceed"][k] = exceed
            out["anomaly"][k] = ch.active
        if self.n_valid % c["ANOM_SIGMA_EVERY"] == 0:
            for k in range(nch):
                self._update_sigma(self.ch[k], self.sigma_floor[k])

        # Events open and close on the Figaro channels (0 and 1) only.
        any_active = self.ch[CH4].active or self.ch[LPG].active
        ev = self.ev
        if any_active:
            if not self.ev_open:
                self.ev_open = True
                ev = self.ev = Event.for_channels(nch)
                ev.id = self.next_event_id
                self.next_event_id = (self.next_event_id + 1) & 0xFFFF
                have_start = False
                for k in range(nch):
                    self.ev_peak_known[k] = False
                    self.ev_onset_known[k] = False
                    if (k <= LPG and self.ch[k].active
                            and (not have_start or self.ch[k].run_start_ms < ev.t_start_ms)):
                        ev.t_start_ms = self.ch[k].run_start_ms
                        have_start = True
                self.ev_air_sum = 0.0
                self.ev_air_n = 0
                self.ev_air_all_low = True
                ev.co_peak_ppm = 0.0
            self.ev_last_active_ms = t
        if self.ev_open:
            for k in range(nch):
                # Only samples on which the channel is valid and ready count.
                if not out["ch_ready"][k]:
                    continue
                r = out["res"][k]
                z = r / out["sigma"][k]
                if not self.ev_peak_known[k]:
                    self.ev_peak_known[k] = True
                    ev.peak_res_mv[k] = r
                    ev.peak_sigma[k] = z
                    ev.t_peak_ms[k] = t
                else:
                    if r > ev.peak_res_mv[k]:
                        ev.peak_res_mv[k] = r
                        ev.t_peak_ms[k] = t
                    if z > ev.peak_sigma[k]:
                        ev.peak_sigma[k] = z
                if self.ch[k].active:
                    ev.detected[k] = 1
                if k <= LPG and not self.ev_onset_known[k] and self.ch[k].above_lead:
                    self.ev_onset_known[k] = True
                    self.ev_onset_ms[k] = self.ch[k].lead_cross_ms
            if (self.step_seen
                    and ev.t_start_ms - int(c["ANOM_THERMAL_PRE_S"] * 1000.0) <= self.last_step_ms
                    <= ev.t_start_ms + int(c["ANOM_THERMAL_POST_S"] * 1000.0)):
                ev.thermal = 1
            if air_ok_used:
                if self.ev_air_n == 0 or air < ev.airflow_min:
                    ev.airflow_min = air
                self.ev_air_sum += air
                self.ev_air_n += 1
                if not (air < c["ANOM_AIR_LOW_INDEX"]):
                    self.ev_air_all_low = False
            if co_ok_used:
                if not ev.co_known or co_dev > ev.co_peak_ppm:
                    ev.co_peak_ppm = co_dev
                ev.co_known = 1
            tail_ms = int(c["ANOM_MERGE_GAP_S"] * 1000.0)
            if c["ANOM_USE_CO"] and tail_ms < int(c["ANOM_CO_TAIL_S"] * 1000.0):
                tail_ms = int(c["ANOM_CO_TAIL_S"] * 1000.0)
            if not any_active and t - self.ev_last_active_ms >= tail_ms:
                ev.t_end_ms = self.ev_last_active_ms
                if self.ev_onset_known[CH4] and self.ev_onset_known[LPG]:
                    ev.lead_known = 1
                    ev.lead_s = (self.ev_onset_ms[LPG] - self.ev_onset_ms[CH4]) / 1000.0
                if self.ev_air_n > 0:
                    ev.airflow_known = 1
                    ev.airflow_mean = self.ev_air_sum / self.ev_air_n
                    ev.low_airflow = int(self.ev_air_all_low)
                self._classify(ev)
                out["event"] = ev
                self.ev_open = False
        out["event_open"] = self.ev_open
        return out


# ---- Whole-survey replay ------------------------------------------------------------------

def replay(inputs: dict, cfg: dict | None = None) -> tuple[dict, list[Event]]:
    """Run a survey through the detector, sample by sample.

    inputs: arrays t_ms, ch4_mv, lpg_mv, temp_c, rh_pct, valid, and optionally
    airflow_index/airflow_ok and co_ppm/co_ok. With mems_a_mv/mems_a_ok and
    mems_b_mv/mems_b_ok as well it runs 4 channels (rev F), else 2. Returns
    per-sample arrays ([n, channels] for per-channel ones; NaN where a channel was
    not valid) and the list of closed events.
    """
    nch = nch_of(inputs)
    det = Detector(cfg, nch)
    n = len(inputs["t_ms"])
    o = {
        "ready": np.zeros(n, bool), "suppressed": np.zeros(n, bool), "event_open": np.zeros(n, bool),
        "feat": np.zeros((n, NFEAT)), "event_class": np.zeros(n, np.int8), "event_ratio": np.full(n, np.nan),
        "event_id": np.zeros(n, np.int32), "valid": np.zeros(n, bool),
    }
    for name in ("target", "pred", "model_res", "res", "sigma"):
        o[name] = np.full((n, nch), np.nan)
    for name in ("exceed", "anomaly", "ch_valid", "ch_ready"):
        o[name] = np.zeros((n, nch), bool)
    events: list[Event] = []
    t = np.asarray(inputs["t_ms"], dtype=np.int64)
    g4 = np.asarray(inputs["ch4_mv"], float)
    gl = np.asarray(inputs["lpg_mv"], float)
    tc = np.asarray(inputs["temp_c"], float)
    rh = np.asarray(inputs["rh_pct"], float)
    va = np.asarray(inputs["valid"], bool)
    air = inputs.get("airflow_index")
    air_ok = inputs.get("airflow_ok")
    co = inputs.get("co_ppm")
    co_ok = inputs.get("co_ok")
    xg = [np.asarray(inputs[f"{ch}_mv"], float) for ch in CHANNEL_NAMES[2:nch]]
    xo = [np.asarray(inputs[f"{ch}_ok"], bool) for ch in CHANNEL_NAMES[2:nch]]
    for i in range(n):
        r = det.step(int(t[i]), g4[i], gl[i], tc[i], rh[i], bool(va[i]),
                     float(air[i]) if air is not None else 0.0,
                     bool(air_ok[i]) if air_ok is not None else False,
                     float(co[i]) if co is not None else 0.0,
                     bool(co_ok[i]) if co_ok is not None else False,
                     [a[i] for a in xg], [a[i] for a in xo])
        if r is None:
            continue
        o["valid"][i] = True
        o["ready"][i] = r["ready"]
        o["suppressed"][i] = r["suppressed"]
        o["event_open"][i] = r["event_open"]
        o["feat"][i] = r["feat"]
        for k in range(nch):
            o["ch_valid"][i, k] = r["ch_valid"][k]
            o["ch_ready"][i, k] = r["ch_ready"][k]
            if not r["ch_valid"][k]:
                continue
            o["target"][i, k] = r["target"][k]
            o["pred"][i, k] = r["pred"][k]
            o["model_res"][i, k] = r["model_res"][k]
            o["res"][i, k] = r["res"][k]
            o["sigma"][i, k] = r["sigma"][k]
            o["exceed"][i, k] = r["exceed"][k]
            o["anomaly"][i, k] = r["anomaly"][k]
        ev = r["event"]
        if ev is not None:
            o["event_class"][i] = ev.cls
            o["event_ratio"][i] = ev.ratio
            o["event_id"][i] = ev.id
            events.append(ev)
    return o, events
