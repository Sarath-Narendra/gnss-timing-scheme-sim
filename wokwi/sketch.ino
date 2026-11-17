// Payload MCU - my GNSS timing scheme, kept simple.
//
// GNSS gives: a PPS pulse at the start of every UTC second, and ~0.2 s later
// an NMEA message saying which second that pulse was.
// The MCU's timer counts ticks (1 tick = 1 microsecond of its own clock).
//
// PART 1  Catch every pulse and remember its tick       (interrupt)
// PART 2  Measure N = ticks in one real second          (average of last 16 pulses)
// PART 3  Fire the camera at the predicted next pulse   (last pulse + N)
// PART 4  Check the pulse came (+-1 ms); if not, keep going on N alone
// PART 5  Label the photo with the UTC from NMEA (or last + 1 if no message)

const int PPS_PIN = 2;       // GNSS pulse in
const int CAM_PIN = 15;      // camera trigger out (red LED)
const long WINDOW = 1000;    // pulse must arrive within +-1000 ticks (+-1 ms) of my prediction

// ---------- PART 1: catch the pulse ----------
volatile unsigned long ppsTick = 0;
volatile bool ppsNew = false;
void onPulse() { ppsTick = micros(); ppsNew = true; }

// ---------- PART 2: measure N ----------
unsigned long histTick[16];  // tick of each of the last 16 good pulses
long histSec[16];            // which second each one was
int histCount = 0;
double N = 1000000;          // first guess; replaced by the measurement

void rememberPulse(unsigned long tick, long sec) {
  if (histCount == 16) {     // drop the oldest
    for (int i = 0; i < 15; i++) { histTick[i] = histTick[i + 1]; histSec[i] = histSec[i + 1]; }
    histCount = 15;
  }
  histTick[histCount] = tick; histSec[histCount] = sec; histCount++;
  if (histCount >= 2)        // ticks between oldest and newest / seconds between them
    N = (double)(histTick[histCount - 1] - histTick[0]) / (histSec[histCount - 1] - histSec[0]);
}

// ---------- NMEA: read "$GPZDA,hhmmss.00,..." -> seconds since midnight ----------
char line[80]; int len = 0;
long readTimeMessage(unsigned long waitMs) {   // returns -1 if nothing arrives in time
  unsigned long t0 = millis();
  while (millis() - t0 < waitMs) {
    if (!Serial1.available()) { delay(1); continue; }   // nothing yet: sleep 1 ms
    while (Serial1.available()) {
      char c = Serial1.read();
      if (c == '\n') {
        line[len] = 0; len = 0;
        if (strncmp(line, "$GPZDA,", 7) == 0) {
          long hh = (line[7] - '0') * 10 + (line[8] - '0');
          long mm = (line[9] - '0') * 10 + (line[10] - '0');
          long ss = (line[11] - '0') * 10 + (line[12] - '0');
          return hh * 3600 + mm * 60 + ss;
        }
      } else if (c != '\r' && len < 79) line[len++] = c;
    }
  }
  return -1;
}

void printTime(long sec, long us) {   // prints hh:mm:ss.uuuuuu
  char b[24];
  snprintf(b, sizeof b, "%02ld:%02ld:%02ld.%06ld", sec / 3600 % 24, sec / 60 % 60, sec % 60, us);
  Serial1.print(b);
}

unsigned long pulseTick;     // tick of the latest pulse (real, or predicted if it was missing)
long secNo = 0;              // seconds counted since the first pulse
long utc;                    // UTC second of the latest pulse
bool lastWasMissing = false;

void setup() {
  Serial1.begin(115200);     // TX -> serial monitor, RX <- GNSS NMEA
  pinMode(CAM_PIN, OUTPUT);
  pinMode(PPS_PIN, INPUT);
  attachInterrupt(digitalPinToInterrupt(PPS_PIN), onPulse, RISING);

  Serial1.println("Payload MCU on. Waiting for the first GNSS pulse...");
  while (!ppsNew) delay(1);                // the first pulse starts everything
  ppsNew = false;
  pulseTick = ppsTick;
  rememberPulse(pulseTick, 0);
  utc = readTimeMessage(500);
  Serial1.print("First pulse caught. It was UTC ");
  printTime(utc, 0);
  Serial1.println(". Photos start now, one per second.\n");
}

void loop() {
  // ---------- PART 3: fire the camera at the predicted next pulse ----------
  unsigned long predicted = pulseTick + (unsigned long)(N + 0.5);
  while ((long)(predicted - micros()) > 2000) delay(1);   // sleep until ~2 ms before
  while ((long)(micros() - predicted) < 0) {}              // then wait for the exact tick
  digitalWrite(CAM_PIN, HIGH);                     // camera fires
  unsigned long strobeTick = micros();             // camera's strobe, captured on the same timer
  secNo++;

  // ---------- PART 4: did the pulse come within +-1 ms? ----------
  delayMicroseconds(WINDOW + 50);
  bool pulseOK = ppsNew && labs((long)(ppsTick - predicted)) <= WINDOW;
  long diff = (long)(ppsTick - predicted);         // how far the real pulse was from my prediction
  ppsNew = false;
  if (pulseOK) { pulseTick = ppsTick; rememberPulse(pulseTick, secNo); }
  else         { pulseTick = predicted; }           // no pulse: trust N, carry on

  // ---------- PART 5: label the photo ----------
  long gnssTime = readTimeMessage(400);            // NMEA comes 50-300 ms after the pulse
  long myCount = utc + 1;
  utc = (gnssTime >= 0) ? gnssTime : myCount;
  digitalWrite(CAM_PIN, LOW);

  // time stamp = UTC second + (strobe tick - pulse tick) / N
  long offsetUs = lround((long)(strobeTick - pulseTick) * 1000000.0 / N);
  long stampSec = utc, stampUs = offsetUs;
  if (stampUs < 0) { stampSec -= 1; stampUs += 1000000; }

  Serial1.print("Photo "); Serial1.print(secNo);
  Serial1.print("  stamp UTC "); printTime(stampSec, stampUs);
  if (pulseOK) {
    Serial1.print("  | pulse OK, "); Serial1.print(diff); Serial1.print(" us from my prediction");
  } else {
    Serial1.print("  | pulse MISSING -> fired at last pulse + N");
  }
  Serial1.print(gnssTime >= 0 ? "  | time from GNSS" : "  | time = last + 1");
  Serial1.print("  | N = "); Serial1.println((long)(N + 0.5));

  if (pulseOK && lastWasMissing) {
    Serial1.print("   GNSS is back. My own count said "); printTime(myCount, 0);
    Serial1.print(", GNSS says "); printTime(gnssTime, 0);
    Serial1.println(gnssTime == myCount ? "  -> they match" : "  -> MISMATCH");
  }
  lastWasMissing = !pulseOK;
}
