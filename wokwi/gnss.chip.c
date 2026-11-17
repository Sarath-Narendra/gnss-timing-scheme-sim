// Simulated GNSS receiver.
// Every second it sends:
//   1) a PPS pulse  -> the exact start of a UTC second
//   2) ~0.2 s later, an NMEA message saying WHICH second that pulse was
// If the EN switch is off (no satellite fix), it sends nothing at all.

#include "wokwi-api.h"
#include <stdio.h>
#include <stdlib.h>

// One real second, measured in the payload MCU's clock ticks (1 tick = 1 us).
// Real crystals are never perfect: here the MCU's crystal runs 50 ppm fast,
// so it counts 1,000,050 ticks in one real second. The MCU does not know this
// number - it has to measure it (that is "N" in my scheme).
#define ONE_SECOND_US 1000050

typedef struct {
  pin_t pps, en;
  uart_dev_t uart;
  timer_t second_timer, pps_off_timer, nmea_timer;
  uint32_t utc;      // UTC of the latest pulse, in seconds since midnight
  char msg[64];
} gnss_t;

static void on_second(void *user_data) {
  gnss_t *g = user_data;
  g->utc++;                                   // real time keeps going, fix or no fix
  if (pin_read(g->en) == LOW) return;         // switch off = no fix = no pulse, no message
  pin_write(g->pps, HIGH);                    // rising edge = start of this UTC second
  timer_start(g->pps_off_timer, 100000, false);   // pulse is 100 ms wide
  timer_start(g->nmea_timer, 200000, false);      // time message 200 ms later
}

static void on_pps_off(void *user_data) {
  gnss_t *g = user_data;
  pin_write(g->pps, LOW);
}

static void on_nmea(void *user_data) {
  gnss_t *g = user_data;
  uint32_t t = g->utc;
  char body[48];
  snprintf(body, sizeof body, "GPZDA,%02u%02u%02u.00,16,11,2026,00,00",
           (unsigned)(t / 3600 % 24), (unsigned)(t / 60 % 60), (unsigned)(t % 60));
  uint8_t cs = 0;                             // NMEA checksum = XOR of the characters
  for (char *p = body; *p; p++) cs ^= (uint8_t)*p;
  int n = snprintf(g->msg, sizeof g->msg, "$%s*%02X\r\n", body, cs);
  uart_write(g->uart, (uint8_t *)g->msg, n);
}

void chip_init(void) {
  gnss_t *g = calloc(1, sizeof(gnss_t));
  g->utc = 8 * 3600 + 36 * 60;                // clock starts at 08:36:00 UTC
  g->pps = pin_init("PPS", OUTPUT_LOW);
  g->en  = pin_init("EN", INPUT_PULLUP);

  const uart_config_t uart_cfg = {
    .tx = pin_init("TX", INPUT_PULLUP),
    .rx = pin_init("RX", INPUT),     // not used (GNSS only talks)
    .baud_rate = 115200,
    .user_data = g,
  };
  g->uart = uart_init(&uart_cfg);

  const timer_config_t t1 = { .callback = on_second,  .user_data = g };
  const timer_config_t t2 = { .callback = on_pps_off, .user_data = g };
  const timer_config_t t3 = { .callback = on_nmea,    .user_data = g };
  g->second_timer  = timer_init(&t1);
  g->pps_off_timer = timer_init(&t2);
  g->nmea_timer    = timer_init(&t3);
  timer_start(g->second_timer, ONE_SECOND_US, true);
  printf("GNSS ready\n");
}
