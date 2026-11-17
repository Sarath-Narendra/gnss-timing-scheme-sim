# GNSS timing scheme: microcontroller simulation (Wokwi)

A Raspberry Pi Pico runs my timing scheme. A simulated GNSS receiver feeds it:
- **PPS** on GP2: a pulse at the start of every UTC second (the green LED blinks with it)
- **NMEA** on GP1: about 0.2 s after each pulse, a `$GPZDA` message saying which second that pulse was
- **Switch**: turns the GNSS fix off and on

The red **CAMERA** LED is the camera trigger. The serial monitor prints one line per photo.

## What the run shows
```
Photo 1   stamp UTC 08:36:01.999950 | pulse OK, 50 us from my prediction | time from GNSS | N = 1000050
Photo 2   stamp UTC 08:36:03.000002 | pulse OK, 0 us from my prediction  | time from GNSS | N = 1000050
...
Photo 20  stamp UTC 08:36:21.000000 | pulse MISSING -> fired at last pulse + N | time = last + 1
...
Photo 30  stamp UTC 08:36:31.000002 | pulse OK, 0 us from my prediction  | time from GNSS
   GNSS is back. My own count said 08:36:31, GNSS says 08:36:31 -> they match
```
- **Photo 1** fires on the first guess (N = 1,000,000). The MCU's clock actually counts 1,000,050 ticks per real second, so the photo is taken 50 µs early. The stamp still records the correct time: 08:36:01.999950.
- **From photo 2 on**, N is measured (1,000,050). The camera fires within a couple of microseconds of the real pulse.
- **GNSS switched off** (photos 20–29): no pulses and no messages arrive. Photos still come every second, timed from the last pulse + N and labelled last + 1.
- **GNSS back** (photo 30): the real pulse lands 0 µs from where the MCU fired the camera, and the MCU's own count of the second matches GNSS. The holdover held.

Every stamp is well inside the 1 ms requirement.

## The code in 5 parts (sketch.ino)
1. **Catch the pulse.** The PPS interrupt saves the timer tick when the pulse arrives.
2. **Measure N.** N is the ticks between the oldest and newest of the last 16 pulses, divided by the seconds between them. This is the number of ticks in one real second for this crystal.
3. **Fire the camera** at the predicted next pulse: last pulse tick + N. The strobe tick is saved on the same timer.
4. **Check the pulse.** If a pulse came within ±1 ms of the prediction, lock to it and update N. If not, the photo is already taken: keep going on N.
5. **Label the photo.** Use the UTC second from NMEA, or last + 1 if there is no message. Stamp = UTC second + (strobe tick − pulse tick) / N.

The GNSS chip (`gnss.chip.c`) does one job: every second it raises PPS and sends the NMEA line 0.2 s later, unless the switch is off.

## Kept out on purpose
This is a logic demo. Heating, crystal temperature drift, the IMU and SSD storage are not modelled. The Python simulation covers the long-mission drift.

## Run it yourself
1. Open wokwi.com and start a new Raspberry Pi Pico project.
2. Use "Upload file(s)" to add these 4 files: `sketch.ino`, `diagram.json`, `gnss.chip.c`, `gnss.chip.json`.
3. Press play. Flip the switch to cut GNSS, then flip it back.
