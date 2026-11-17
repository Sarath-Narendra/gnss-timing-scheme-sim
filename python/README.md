# GNSS/PPS photo time-stamping: flight simulation

Simulates the payload timing scheme from my Digantara payload design assessment
over a full 6.5 h flight (1 h on the ground, 90 min ascent, 4 h float), one second at a time.

Run:
    pip install numpy matplotlib
    python3 sim.py          # prints the results
    python3 make_video.py   # renders gnss_timing_simulation.mp4 (needs ffmpeg)

## Modelled
- GNSS pulse (PPS): 20 ns jitter. NMEA arrives 50-300 ms after its pulse; 1.2 % lost or corrupt.
- MCU counter: 1 MHz nominal, crystal +20 ppm, temperature curve, short-term noise, slow random-walk drift.
- Crystal temperature: heater-held near 25 C (design) vs. following the unheated box (comparison).
- GNSS outages: 60 s (ascent) and 15 min (float).
- Camera: hardware-triggered, near-zero delay (0-1 us), 0.3 ms exposure, stamped at mid-exposure.

## Scheme
1. Capture the counter at every pulse; N = ticks per true second, averaged over the last 16 pulses.
2. Fire the camera at the tick where the next pulse is expected.
3. Pulse within +/-1 ms of prediction: lock to it. Pulse missing: photo already taken, mark "no pulse".
4. Stamp = UTC second (from the NMEA that follows the pulse) + (strobe tick - pulse tick) / N + exposure/2.

## Results (seed 7)
| Case | Worst stamp error |
|---|---|
| GNSS present | 1.0 us |
| 60 s outage, heated crystal | 0.7 us |
| 15 min outage, heated crystal | 10.8 us |
| 15 min outage, crystal not heated | 323 us |
| 1-second timer never corrected by GNSS | > 1 ms after 51 s, 0.47 s by the end |
| Stamping on arrival at the computer | 20-120 ms on every photo |

Requirement IR-2: 1 ms.

## Limits
Camera trigger-to-exposure delay is assumed near zero; the real value must be measured on the bench
(LED-on-PPS test in the trial plan). The crystal model is a typical datasheet-style curve, not a measured part.
One design detail the simulation surfaced: using a single-second N (integer ticks) limits holdover accuracy to
about 1 ppm, so N is averaged over 16 pulses.
