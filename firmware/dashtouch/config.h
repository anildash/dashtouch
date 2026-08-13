#pragma once
// Hardware configuration. Everything here is safe to commit.

// --- Sensor UART pins ------------------------------------------------
// Defaults follow the QT Py silkscreen: we transmit on the pad labeled
// TX (GPIO 5) and receive on the pad labeled RX (GPIO 16). Wire the
// sensor's yellow (TXD) lead to RX and brown (RXD) to TX.
//
// If fp_loopback shows your board's TX pad flooding zeros (one known
// unit does this), swap the two values below — and only then.
#define DT_FP_TX_PIN 5
#define DT_FP_RX_PIN 16

#define DT_UART_BAUD 57600

// --- Behavior --------------------------------------------------------
#define DT_POLL_MS 150          // GenImg poll cadence while idle
#define DT_RESULT_HOLD_MS 1200  // how long match/no-match colors linger
#define DT_PRESS_ENTER 1        // press Return after typing the password

// --- Finger detection ------------------------------------------------
// Default: poll the sensor itself (works on every module, no extra
// wiring assumptions). Optional: gate polling on the WAKEUP line (blue
// lead on A3) — set DT_USE_WAKEUP_PIN 1 and pick the polarity your
// module actually idles at. One known module idles at the "active"
// level, which makes the pin useless — polling is the safe default.
#define DT_USE_WAKEUP_PIN 0
#define DT_WAKEUP_PIN 8         // pad labeled A3
#define DT_WAKEUP_ACTIVE LOW    // level meaning "finger present"

#define DT_MIN_SLOT 1
#define DT_MAX_SLOT 200

#define DT_FW_VERSION "dt-0.1.0"
