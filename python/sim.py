"""
GNSS / PPS photo time-stamping - flight simulation
===================================================

Simulates the balloon imaging payload timing scheme (see docs/DESIGN.md), one
second at a time, over the whole flight (1 h on the ground + 90 min ascent +
240 min float = 23,400 s).

What is modelled
----------------
* GNSS pulse (PPS): one edge per true second, with 20 ns of jitter.
* MCU counter: nominally 1,000,000 ticks per second, driven by a crystal that is
  20 ppm fast and whose frequency also changes with temperature.
* Crystal temperature: either held near 25 C by the heater (our design) or left
  to follow the box temperature (for comparison).
* NMEA message: arrives 50-300 ms after its pulse; 1 % are lost and 0.2 % fail
  their checksum.
* Two GNSS outages: 60 s during ascent and 15 min during float.
* Camera: fires on the hardware trigger with near-zero delay (0-1 us); exposure
  0.3 ms, time stamp taken at the middle of the exposure.

Our scheme (what the MCU does)
------------------------------
1. Capture the counter value at every pulse.
2. N = ticks per true second, averaged over the last 16 pulses.
3. Fire the camera at the tick where the next pulse is expected
   (last pulse + N x seconds since it).
4. If a pulse arrives within +/-1 ms of that tick: lock to it.
   If not: the photo was already taken; mark it "no pulse" (holdover).
5. Capture the strobe tick; time stamp =
       UTC second of the reference pulse (from NMEA)
     + (strobe tick - pulse tick) / N
     + half the exposure.

Two simpler methods are simulated for comparison:
  A. Stamp the photo with the computer's clock when it arrives (20-120 ms late).
  B. Free-running 1-second timer started at the first pulse and never corrected.
"""
import numpy as np

F_NOM = 1_000_000          # nominal counter ticks per second
T_TOTAL = 23_400           # seconds simulated
T_LAUNCH = 3_600           # launch time (s after switch-on)
T_FLOAT = T_LAUNCH + 5_400 # float begins
EXPOSURE = 0.0003          # s
OUTAGES = [(5_400, 5_460), (14_400, 15_300)]   # GNSS pulse missing in [start, end)
N_AVG = 16                 # pulses averaged to estimate N
WINDOW = 1_000             # ticks: a pulse must land within +/-1 ms of prediction


def crystal_temperature(t, heated, rng):
    """Crystal temperature (C) at flight time t (array)."""
    if heated:
        # heater + thermostat hold ~25 C; small cycling as the heater switches
        return 25 + 0.3 * np.sin(2 * np.pi * t / 600) + rng.normal(0, 0.05, t.size)
    T = np.full(t.size, 30.0)
    asc = (t >= T_LAUNCH) & (t < T_FLOAT)
    x = (t[asc] - T_LAUNCH) / (T_FLOAT - T_LAUNCH)
    T[asc] = 30 - 58 * np.sin(np.pi / 2 * np.clip(x * 1.25, 0, 1)) + 42 * np.clip(x * 1.25 - 1, 0, 1)
    flo = t >= T_FLOAT
    T[flo] = -16 + 9 * np.sin(2 * np.pi * (t[flo] - T_FLOAT) / 7_200)
    return T + rng.normal(0, 0.05, t.size)


def crystal_ppm(T):
    """Frequency error of a typical cheap crystal: +20 ppm offset plus a
    temperature curve (about -12 ppm at -30 C, ~0 at 25 C)."""
    return 20.0 - 0.004 * (T - 25.0) ** 2 + 0.02 * (T - 25.0)


def run(heated=True, seed=7):
    rng = np.random.default_rng(seed)
    secs = np.arange(T_TOTAL + 2, dtype=float)
    temp = crystal_temperature(secs, heated, rng)
    ppm = (crystal_ppm(temp) + rng.normal(0, 0.003, secs.size)        # short-term noise
           + np.cumsum(rng.normal(0, 0.0005, secs.size)))              # slow random-walk drift
    f = F_NOM * (1 + ppm * 1e-6)                                      # ticks/s during [s, s+1)
    C = np.concatenate([[123_456.0], 123_456.0 + np.cumsum(f)])       # counter at true time s

    def count_at(t):
        s = max(int(np.floor(t)), 0)
        return C[s] + f[s] * (t - s)

    def time_at(count):
        s = max(int(np.searchsorted(C, count, side="right") - 1), 0)
        return s + (count - C[s]) / f[s]

    pps_true = secs[:T_TOTAL] + 1.0 + rng.normal(0, 20e-9, T_TOTAL)   # pulse k at true time k+1 (keeps t > 0)
    pps_ok = np.ones(T_TOTAL, bool)
    for a, b in OUTAGES:
        pps_ok[a:b] = False
    nmea_delay = rng.uniform(0.05, 0.30, T_TOTAL)
    nmea_ok = rng.random(T_TOTAL) > 0.012

    out = {k: np.zeros(T_TOTAL) for k in
           ("err", "err_free", "err_arrival", "holdover", "fire_offset_us", "temp", "ppm")}
    out["locked"] = np.zeros(T_TOTAL, bool)
    out["nmea_ok"] = nmea_ok
    out["nmea_delay"] = nmea_delay
    out["temp"] = temp[:T_TOTAL]
    out["ppm"] = ppm[:T_TOTAL]

    history = []                       # (second, captured tick) of accepted pulses
    cap0 = np.floor(count_at(pps_true[0]))
    history.append((0, cap0))
    ref_k, ref_cap, ref_label = 0, cap0, 1     # UTC label of pulse k is k+1
    n_est = float(F_NOM)               # before any measurement, assume nominal
    label_prev = 1

    for k in range(T_TOTAL):
        # --- 1. when should the camera fire? -------------------------------
        if k == 0:
            fire = cap0 + 2            # first photo: fired straight from the first pulse
        else:
            fire = round(ref_cap + n_est * (k - ref_k))
        t_fire = time_at(fire)
        t_start = t_fire + rng.uniform(0, 1e-6)          # near-zero camera delay
        strobe = np.floor(count_at(t_start))

        # --- 2. did the pulse arrive where expected? -----------------------
        if k > 0:
            if pps_ok[k]:
                cap = np.floor(count_at(pps_true[k]))
                if abs(cap - fire) <= WINDOW:
                    history.append((k, cap))
                    history = history[-(N_AVG + 1):]
                    k0, c0 = history[0]
                    if k > k0:
                        n_est = (cap - c0) / (k - k0)
                    # label from NMEA (arrives 50-300 ms later); if lost, previous + 1
                    label = (k + 1) if nmea_ok[k] else label_prev + 1
                    ref_k, ref_cap, ref_label = k, cap, label
            label_prev = ref_label + (k - ref_k)

        locked = (ref_k == k)
        # --- 3. time stamp ---------------------------------------------------
        tag = ref_label + (strobe - ref_cap) / n_est + EXPOSURE / 2
        truth = t_start + EXPOSURE / 2
        out["err"][k] = tag - truth
        out["locked"][k] = locked
        out["holdover"][k] = k - ref_k
        out["fire_offset_us"][k] = (t_fire - pps_true[k]) * 1e6

        # --- comparison B: free-running timer, never corrected ---------------
        tb = time_at(cap0 + 2 + F_NOM * k)
        out["err_free"][k] = (k + 1 + EXPOSURE / 2) - (tb + EXPOSURE / 2)
        # --- comparison A: stamp on arrival at the computer -------------------
        out["err_arrival"][k] = rng.uniform(0.020, 0.120)
    return out


def summary(o, name):
    e = np.abs(o["err"]) * 1e6
    lk = o["locked"]
    rows = [f"{name}",
            f"  photos taken                  : {e.size} (none missed)",
            f"  max error, GNSS pulse present : {e[lk].max():8.2f} us",
            f"  mean error, GNSS pulse present: {e[lk].mean():8.2f} us"]
    for a, b in OUTAGES:
        seg = e[a:b + 1]
        rows.append(f"  max error, outage {b - a:4d} s       : {seg.max():8.2f} us")
    rows.append(f"  NMEA messages lost/bad        : {(~o['nmea_ok']).sum()} (labels filled as previous + 1)")
    return "\n".join(rows)


if __name__ == "__main__":
    h = run(heated=True)
    u = run(heated=False)
    print(summary(h, "Our scheme, crystal held at ~25 C"))
    print(summary(u, "Our scheme, crystal NOT heated"))
    fr = np.abs(h["err_free"])
    print("Free-running timer: exceeds 1 ms after", np.argmax(fr > 1e-3), "s; final error", fr[-1], "s")
    np.savez_compressed("sim_results.npz", **{f"h_{k}": v for k, v in h.items()},
                        **{f"u_{k}": v for k, v in u.items()})
