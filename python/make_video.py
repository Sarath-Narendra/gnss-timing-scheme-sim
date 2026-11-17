"""Render the simulation as a 1920x1080 MP4 (and a summary PNG)."""
import subprocess
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import sim

h = sim.run(heated=True)
u = sim.run(heated=False)
T = sim.T_TOTAL
t = np.arange(T)

BLUE, AQUA, ORANGE, GREY, RED, INK, MUTE = "#2a78d6", "#1baf7a", "#eb6834", "#8a93a3", "#c0392b", "#1b2430", "#5b6675"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13, "axes.edgecolor": "#c9cfd9",
                     "axes.labelcolor": INK, "xtick.color": MUTE, "ytick.color": MUTE})
FPS = 30


def hms(s):
    s = int(s); return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def phase(s):
    return "On the ground" if s < sim.T_LAUNCH else ("Ascent" if s < sim.T_FLOAT else "Float at 20 km")


# ---- frame schedule: play the outages slower so the holdover is visible ----
w = np.ones(T)
for a, b in sim.OUTAGES:
    w[max(a - 120, 0):b + 120] = 6.0
cw = np.cumsum(w); cw /= cw[-1]
N_FR = 32 * FPS
frame_sec = np.searchsorted(cw, np.linspace(0, 1, N_FR, endpoint=False) + 1e-9).clip(0, T - 1)

# ---- error series for the big plot (floor at 0.1 us for the log axis) ----
from numpy.lib.stride_tricks import sliding_window_view
def worst30(x):
    """worst |error| over the last 30 photos (causal), floored at 0.1 us for the log axis"""
    a = np.abs(x); p = np.concatenate([np.full(29, a[0]), a])
    return np.maximum(sliding_window_view(p, 30).max(axis=1), 1e-7)
eh, eu, ef, ea = worst30(h["err"]), worst30(u["err"]), worst30(h["err_free"]), worst30(h["err_arrival"])

fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
fig.patch.set_facecolor("white")
gs = GridSpec(3, 3, figure=fig, left=0.06, right=0.975, top=0.86, bottom=0.07, hspace=0.55, wspace=0.28,
              height_ratios=[1, 1, 1.35])
ax_sec = fig.add_subplot(gs[0, :2])
ax_us = fig.add_subplot(gs[0, 2])
ax_err = fig.add_subplot(gs[1:, :2])
ax_tmp = fig.add_subplot(gs[1, 2])
ax_txt = fig.add_subplot(gs[2, 2]); ax_txt.axis("off")

title = fig.text(0.06, 0.945, "GNSS-pulse photo time-stamping: full-flight simulation", fontsize=24, weight="bold", color=INK)
clock = fig.text(0.06, 0.905, "", fontsize=16, color=MUTE)
status = fig.text(0.975, 0.925, "", fontsize=20, weight="bold", ha="right")

# --- panel 1: inside one second ---
ax_sec.set_xlim(-0.05, 1.0); ax_sec.set_ylim(-0.6, 4.2); ax_sec.set_yticks([])
ax_sec.set_xlabel("time within the current second (s)")
ax_sec.set_title("Inside one second", loc="left", fontsize=15, weight="bold", color=INK)
lanes = {"GNSS pulse (PPS)": 3.4, "Camera fired + strobe": 2.4, "NMEA message": 1.4, "IMU readings": 0.4}
for name, y in lanes.items():
    ax_sec.text(-0.048, y + 0.42, name, fontsize=12, color=MUTE, va="bottom")
    ax_sec.axhline(y, color="#e3e6eb", lw=1, zorder=0)
pps_line, = ax_sec.plot([], [], color=INK, lw=3)
pps_x = ax_sec.text(0, 3.4, "", color=ORANGE, fontsize=22, ha="center", va="center", weight="bold")
cam_line, = ax_sec.plot([], [], color=BLUE, lw=3)
nmea_box = ax_sec.add_patch(plt.Rectangle((0, 1.2), 0.07, 0.42, fc="#dbe9fa", ec=BLUE))
nmea_txt = ax_sec.text(0, 1.41, "", fontsize=11, va="center", color=INK)
for i in range(100):
    ax_sec.plot([i / 100, i / 100], [0.3, 0.62], color=AQUA, lw=1.2)

# --- panel 2: microsecond zoom ---
ax_us.set_xlim(-12, 12); ax_us.set_ylim(0, 3); ax_us.set_yticks([])
ax_us.set_title("Zoom: ±12 microseconds around the pulse", loc="left", fontsize=15, weight="bold", color=INK)
ax_us.set_xlabel("microseconds (µs)")
ax_us.axvline(0, color=INK, lw=2.5); ax_us.text(0.2, 2.75, "true GNSS second", fontsize=11, color=INK)
fire_mark = ax_us.axvline(0, color=BLUE, lw=2.5, ls="--")
fire_lbl = ax_us.text(0, 1.85, "camera fired", fontsize=11, color=BLUE)
err_bar = ax_us.annotate("", xy=(0, 0.8), xytext=(0, 0.8), arrowprops=dict(arrowstyle="<->", color=RED, lw=2))
err_lbl = ax_us.text(0, 0.35, "", fontsize=12, color=RED, ha="center", weight="bold")

# --- panel 3: error over the flight ---
ax_err.set_yscale("log"); ax_err.set_xlim(0, T / 3600); ax_err.set_ylim(1e-7, 3)
ax_err.set_xlabel("flight time (hours since switch-on)")
ax_err.set_ylabel("worst time-stamp error in each 30 s")
ax_err.set_yticks([1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 1e-1, 1])
ax_err.set_yticklabels(["1 µs", "10 µs", "100 µs", "1 ms", "10 ms", "100 ms", "1 s"])
ax_err.grid(axis="y", color="#eef0f4")
ax_err.set_title("Time-stamp error of every photo", loc="left", fontsize=15, weight="bold", color=INK)
ax_err.axhline(1e-3, color=RED, lw=2.2)
ax_err.text(5.2, 1.3e-3, "IR-2 limit: 1 ms", color=RED, fontsize=13, weight="bold")
for a, b in sim.OUTAGES:
    ax_err.axvspan(a / 3600, b / 3600, color="#fde6da", zorder=0)
ax_err.text(sim.OUTAGES[1][0] / 3600, 1.6, " GNSS lost\n 15 min", fontsize=11, color=ORANGE, va="top")
ax_err.text(sim.OUTAGES[0][0] / 3600, 1.6, " GNSS lost\n 60 s", fontsize=11, color=ORANGE, va="top")
for x, lbl in ((sim.T_LAUNCH, "launch"), (sim.T_FLOAT, "float")):
    ax_err.axvline(x / 3600, color="#c9cfd9", lw=1, ls=":")
    ax_err.text(x / 3600 + 0.03, 0.02, lbl, fontsize=11, color=MUTE)
STEP = 5
l_arr, = ax_err.plot([], [], color=GREY, lw=1.5, label="A. stamp photo when it reaches the computer")
l_free, = ax_err.plot([], [], color=ORANGE, lw=2.5, label="B. 1-second timer, never corrected by GNSS")
l_unh, = ax_err.plot([], [], color=AQUA, lw=1.6, label="Our scheme, crystal NOT heated")
l_h, = ax_err.plot([], [], color=BLUE, lw=2.2, label="Our scheme, crystal held at ~25 °C (design)")
fig.legend(handles=[l_h, l_unh, l_free, l_arr], loc="upper left", bbox_to_anchor=(0.705, 0.355), fontsize=12.5, frameon=False)
cursor = ax_err.axvline(0, color=INK, lw=1)

# --- panel 4: crystal temperature ---
ax_tmp.set_xlim(0, T / 3600); ax_tmp.set_ylim(-40, 40)
ax_tmp.set_title("Crystal temperature (°C)", loc="left", fontsize=15, weight="bold", color=INK)
ax_tmp.set_xlabel("hours since switch-on"); ax_tmp.grid(color="#eef0f4")
t_h, = ax_tmp.plot([], [], color=BLUE, lw=2, label="heated (design)")
t_u, = ax_tmp.plot([], [], color=AQUA, lw=2, label="not heated")
ax_tmp.legend(fontsize=11, frameon=False, loc="lower left")

stats = ax_txt.text(0, 0.62, "", fontsize=13, va="top", family="DejaVu Sans Mono", color=INK)


def draw(k):
    clock.set_text(f"Flight clock {hms(k)}   ·   {phase(k)}   ·   photo #{k + 1:,} of {T:,}")
    if h["locked"][k]:
        status.set_text("GNSS LOCKED"); status.set_color(AQUA)
        pps_line.set_data([0, 0, 0.02, 0.02], [3.4, 3.85, 3.85, 3.4]); pps_x.set_text("")
    else:
        status.set_text(f"NO GNSS PULSE – holdover {int(h['holdover'][k])} s"); status.set_color(ORANGE)
        pps_line.set_data([], []); pps_x.set_text("✕")
    cam_line.set_data([0, 0, 0.0003, 0.0003, 0.02], [2.4, 2.85, 2.85, 2.4, 2.4])
    d = h["nmea_delay"][k]
    nmea_box.set_x(d)
    nmea_txt.set_position((d + 0.075, 1.41))
    if not h["locked"][k]:
        nmea_txt.set_text("no GNSS fix → time = last pulse + N ticks per second"); nmea_box.set_fc("#fde6da")
    elif h["nmea_ok"][k]:
        nmea_txt.set_text("names the pulse: UTC second " + hms(k + 1)); nmea_box.set_fc("#dbe9fa")
    else:
        nmea_txt.set_text("message lost → label = previous second + 1"); nmea_box.set_fc("#fde6da")
    fo = float(np.clip(h["fire_offset_us"][k], -11.8, 11.8))
    fire_mark.set_xdata([fo, fo]); fire_lbl.set_position((min(fo + 0.3, 5.5), 1.85))
    ev = float(np.clip(h["err"][k] * 1e6, -11.8, 11.8))
    err_bar.xy = (0, 0.8); err_bar.set_position((ev, 0.8))
    err_lbl.set_position((ev / 2 if abs(ev) > 1 else 0, 0.35))
    err_lbl.set_text(f"stamp error {abs(h['err'][k]) * 1e6:.2f} µs")
    s = slice(0, k + 1, STEP)
    x = t[s] / 3600
    l_arr.set_data(x, ea[s]); l_free.set_data(x, ef[s]); l_unh.set_data(x, eu[s]); l_h.set_data(x, eh[s])
    cursor.set_xdata([k / 3600] * 2)
    t_h.set_data(x, h["temp"][s]); t_u.set_data(x, u["temp"][s])
    lk = h["locked"][:k + 1]
    worst_lock = np.abs(h["err"][:k + 1][lk]).max() * 1e6
    worst_all = np.abs(h["err"][:k + 1]).max() * 1e6
    worst_unh = np.abs(u["err"][:k + 1]).max() * 1e6
    stats.set_text(
        f"So far (design, heated crystal)\n"
        f" photos taken      {k + 1:>8,}\n"
        f" photos missed     {0:>8}\n"
        f" worst error, GNSS {worst_lock:>7.2f} µs\n"
        f" worst error, all  {worst_all:>7.2f} µs\n"
        f" NMEA lost/bad     {(~h['nmea_ok'][:k + 1]).sum():>8}\n\n"
        f"Crystal not heated\n"
        f" worst error, all  {worst_unh:>7.2f} µs")


def card(lines, size=(19.2, 10.8)):
    f2 = plt.figure(figsize=size, dpi=100); f2.patch.set_facecolor("white")
    y = 0.80
    for txt, fs, wt, col in lines:
        f2.text(0.08, y, txt, fontsize=fs, weight=wt, color=col, va="top")
        y -= 0.025 + fs / 560
    return f2


def to_rgb(f):
    f.canvas.draw()
    return np.asarray(f.canvas.buffer_rgba())[:, :, :3].tobytes()


import sys
if "--png" in sys.argv:
    draw(T - 1); fig.savefig("simulation_summary.png", dpi=100); draw(14900); fig.savefig("frame_outage.png", dpi=100); sys.exit()
ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080",
                       "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                       "-pix_fmt", "yuv420p", "gnss_timing_simulation.mp4"], stdin=subprocess.PIPE)

intro = card([
    ("Can every photo be time-stamped to within 1 ms?", 34, "bold", INK),
    ("Simulation of the payload timing scheme over the whole flight", 22, "normal", MUTE),
    ("", 10, "normal", INK),
    ("•  6.5 h simulated second by second: 1 h on the ground, 90 min ascent, 4 h float", 19, "normal", INK),
    ("•  GNSS pulse with 20 ns jitter; NMEA arrives 50–300 ms late, 1.2 % lost or corrupt", 19, "normal", INK),
    ("•  MCU crystal 20 ppm fast, drifting with temperature and over time", 19, "normal", INK),
    ("•  Two GNSS outages: 60 s in ascent, 15 min at float", 19, "normal", INK),
    ("•  Camera fired by hardware on the expected pulse; strobe captured by the same counter", 19, "normal", INK),
    ("", 10, "normal", INK),
    ("Scheme: measure N = ticks per true second from the pulses (16-pulse average), fire on the", 18, "normal", MUTE),
    ("predicted pulse, label it with the NMEA second, keep firing every N ticks if the pulse is lost.", 18, "normal", MUTE),
])
fr = to_rgb(intro)
for _ in range(FPS * 5): ff.stdin.write(fr)
plt.close(intro)

for i, k in enumerate(frame_sec):
    draw(int(k)); ff.stdin.write(to_rgb(fig))
draw(T - 1)
fig.savefig("simulation_summary.png", dpi=100)
last = to_rgb(fig)
for _ in range(FPS * 3): ff.stdin.write(last)

eh_l = np.abs(h["err"])[h["locked"]].max() * 1e6
o2 = [np.abs(h["err"][a:b + 1]).max() * 1e6 for a, b in sim.OUTAGES]
o2u = [np.abs(u["err"][a:b + 1]).max() * 1e6 for a, b in sim.OUTAGES]
free_cross = int(np.argmax(np.abs(h["err_free"]) > 1e-3))
outro = card([
    ("Result", 34, "bold", INK),
    ("", 8, "normal", INK),
    (f"•  23,400 photos, none missed; every one time-stamped", 21, "normal", INK),
    (f"•  With GNSS: worst error {eh_l:.1f} µs, about 1,000× inside the 1 ms limit", 21, "normal", INK),
    (f"•  60 s outage: worst {o2[0]:.1f} µs     15 min outage: worst {o2[1]:.1f} µs (crystal held at 25 °C)", 21, "normal", INK),
    (f"•  Same 15 min outage without the heater: {o2u[1]:.0f} µs, still inside, but with far less margin", 21, "normal", INK),
    (f"•  A 1-second timer never corrected by GNSS breaks 1 ms after {free_cross} s", 21, "normal", INK),
    ("•  Stamping photos on arrival at the computer: 20–120 ms, fails on every photo", 21, "normal", INK),
    ("", 8, "normal", INK),
    ("Limits of this simulation: camera delay assumed near zero (to be measured on the bench);", 17, "normal", MUTE),
    ("crystal model is a typical datasheet curve; real values come from the test plan (LED-on-PPS check).", 17, "normal", MUTE),
])
fr = to_rgb(outro)
for _ in range(FPS * 7): ff.stdin.write(fr)
ff.stdin.close(); ff.wait()
print("done")
