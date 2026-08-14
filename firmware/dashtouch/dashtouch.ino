// Dashboard Touch firmware — see docs/protocol.md for every line this
// prints or accepts.
#include <Arduino.h>
#include <USB.h>
#include <USBHIDKeyboard.h>
#include "driver/gpio.h"
#include "config.h"
#include "r503.h"
#include "led.h"
#include "link.h"
#include "settings.h"

HardwareSerial FingerSerial(1);
R503 Sensor;
USBHIDKeyboard Keyboard;

bool g_sensorOk = false;
uint16_t g_capacity = 0;

static String s_cmdBuf;
static uint32_t s_lastPoll = 0;

// ---------------------------------------------------------------- enroll
static void doEnroll(uint16_t slot) {
  ledSet(DT_LED_ENROLL_PLACE);
  Serial.println("ENROLL_WAIT_FINGER_1");
  Serial.flush();

  uint32_t deadline = millis() + 15000;
  while (millis() < deadline && Sensor.genImg() != 0) delay(50);
  if (Sensor.img2Tz(1) != 0) {
    Serial.println("ENROLL_FAIL capture1");
    ledSet(DT_LED_ENROLL_FAIL);
    delay(DT_RESULT_HOLD_MS);
    ledSet(DT_LED_IDLE);
    return;
  }

  ledSet(DT_LED_ENROLL_LIFT);
  Serial.println("ENROLL_REMOVE_FINGER");
  Serial.flush();
  deadline = millis() + 8000;
  while (millis() < deadline && Sensor.genImg() == 0) delay(100);
  delay(300);

  ledSet(DT_LED_ENROLL_PLACE);
  Serial.println("ENROLL_WAIT_FINGER_2");
  Serial.flush();
  deadline = millis() + 15000;
  while (millis() < deadline && Sensor.genImg() != 0) delay(50);
  if (Sensor.img2Tz(2) != 0) {
    Serial.println("ENROLL_FAIL capture2");
    ledSet(DT_LED_ENROLL_FAIL);
    delay(DT_RESULT_HOLD_MS);
    ledSet(DT_LED_IDLE);
    return;
  }

  if (Sensor.regModel() != 0) {
    Serial.println("ENROLL_FAIL regmodel");
    ledSet(DT_LED_ENROLL_FAIL);
    delay(DT_RESULT_HOLD_MS);
    ledSet(DT_LED_IDLE);
    return;
  }
  if (Sensor.storeTemplate(slot) != 0) {
    Serial.println("ENROLL_FAIL store");
    ledSet(DT_LED_ENROLL_FAIL);
    delay(DT_RESULT_HOLD_MS);
    ledSet(DT_LED_IDLE);
    return;
  }

  Serial.printf("ENROLL_OK %u\n", slot);
  Serial.flush();
  ledSet(DT_LED_ENROLL_OK);
  delay(DT_RESULT_HOLD_MS);
  ledSet(DT_LED_IDLE);
}

// Selects the sensor UART pins per the stored fp_swap setting and
// (re)starts FingerSerial on them. Shared by setup() and the fp_swap
// SET handler so there's exactly one place pin orientation is decided.
static void initSensorUart() {
  bool fpSwap = settingsFpSwap();
  int rxPin = fpSwap ? DT_FP_TX_PIN : DT_FP_RX_PIN;
  int txPin = fpSwap ? DT_FP_RX_PIN : DT_FP_TX_PIN;
  FingerSerial.end();
  // HardwareSerial::end() frees the UART driver but does not release the
  // ESP32 GPIO matrix routing on the pins it was using. On a live re-init
  // triggered by SET fp_swap, the two physical pins are the same ones as
  // before — only their TX/RX roles flip — so the pin that was just
  // driving as TX output can stay latched to the old peripheral signal
  // instead of going tri-state for its new RX role. The new UART then
  // reads a dead line and every command times out, even though the wiring
  // and the sensor are both fine. gpio_reset_pin() fully detaches a pin
  // from any peripheral (input and output matrix) before we hand the pair
  // to Sensor.begin() in the new orientation.
  gpio_reset_pin((gpio_num_t)DT_FP_TX_PIN);
  gpio_reset_pin((gpio_num_t)DT_FP_RX_PIN);
  delay(20);  // let the reset settle before the handshake races it
  Sensor.begin(FingerSerial, rxPin, txPin, DT_UART_BAUD);
}

// Called after `SET fp_swap <n>` persists the new value. Re-initializes
// the sensor UART with the new orientation and re-runs the handshake
// immediately, so the person setting it learns right away whether that
// orientation works — no reboot needed. Only the sensor UART is
// affected; the USB CDC link to the Mac (and this printf) are untouched.
static void doFpSwapChanged() {
  initSensorUart();
  g_sensorOk = (Sensor.verifyPassword() == 0);
  if (g_sensorOk) {
    Sensor.readSysPara(&g_capacity, nullptr);
    ledSet(DT_LED_IDLE);
    boardLedRed(false);
  } else {
    ledSet(DT_LED_BOOT_FAIL);
    boardLedRed(true);
  }
}

static void doDelete(uint16_t slot) {
  if (Sensor.deleteTemplate(slot) == 0)
    Serial.printf("DELETE_OK %u\n", slot);
  else
    Serial.printf("DELETE_FAIL %u\n", slot);
  Serial.flush();
}

// ----------------------------------------------------------------- match
// After a match: emit EV, wait up to 3000 ms for a valid PW line, type it.
static void handleMatch(uint16_t slot, uint16_t score) {
  char ev[192];
  linkBuildEv(slot, score, ev, sizeof(ev));
  Serial.println("TOUCH");
  Serial.println(ev);
  Serial.flush();

  char pw[128];
  bool typed = false;
  bool answered = false;
  uint32_t deadline = millis() + 3000;
  String buf;
  while (millis() < deadline && !answered) {
    while (Serial.available()) {
      char c = (char)Serial.read();
      if (c == '\n') {
        buf.trim();
        if (buf.startsWith("PW ")) {
          answered = true;
          if (linkDecryptPw(buf.c_str(), pw, sizeof(pw))) {
            Keyboard.print(pw);
            if (settingsPressEnter()) Keyboard.write('\n');
            memset(pw, 0, sizeof(pw));  // wipe
            typed = true;
          }
        }
        buf = "";
      } else if (c != '\r') {
        buf += c;
      }
    }
    delay(5);
  }

  if (typed) {
    Serial.println("TYPED");
    ledSet(DT_LED_MATCH);
    delay(DT_RESULT_HOLD_MS);
    ledSet(DT_LED_IDLE);
  } else if (answered) {
    Serial.println("ERR bad_response");
    ledSet(DT_LED_HELPER_WAIT);  // yellow: the Mac side is the problem
  } else {
    Serial.println("ERR helper_timeout");
    ledSet(DT_LED_HELPER_WAIT);
  }
  Serial.flush();
}

// ---------------------------------------------------------------- serial
void pollSerialCommands() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      String line = s_cmdBuf;
      s_cmdBuf = "";
      line.trim();
      // Any successful host exchange clears a stale yellow.
      if (line.length()) ledSet(DT_LED_IDLE);
      linkHandleCommand(line);
    } else if (c != '\r') {
      s_cmdBuf += c;
    }
  }
}

// ------------------------------------------------------------ setup/loop
void setup() {
  Serial.begin(115200);
  Keyboard.begin();
  USB.begin();
  delay(1500);

#if DT_USE_WAKEUP_PIN
  pinMode(DT_WAKEUP_PIN, INPUT);
#endif

  settingsInit();  // load idle_color/idle_style/press_enter/fp_swap before the first ledSet

  initSensorUart();  // honors the stored fp_swap orientation
  ledInit(&Sensor);
  linkOnEnroll = doEnroll;
  linkOnDelete = doDelete;
  linkOnFpSwapChanged = doFpSwapChanged;

  Serial.printf("BOOT dashtouch %s proto=1\n", DT_FW_VERSION);

  g_sensorOk = (Sensor.verifyPassword() == 0);
  if (g_sensorOk) {
    Sensor.readSysPara(&g_capacity, nullptr);
    Serial.println("READY");
    ledSet(DT_LED_IDLE);
    boardLedRed(false);
  } else {
    Serial.println("ERR sensor_unreachable");
    ledSet(DT_LED_BOOT_FAIL);
    boardLedRed(true);
  }
  Serial.flush();
}

void loop() {
  pollSerialCommands();

  if (!g_sensorOk || millis() - s_lastPoll < DT_POLL_MS) {
    delay(5);
    return;
  }
  s_lastPoll = millis();

#if DT_USE_WAKEUP_PIN
  // Optional: skip the UART round-trip entirely until WAKEUP asserts.
  if (digitalRead(DT_WAKEUP_PIN) != DT_WAKEUP_ACTIVE) return;
#endif

  // Silent poll: no LED change unless a finger is actually present.
  if (Sensor.genImg() != 0) return;

  ledSet(DT_LED_READING);
  if (Sensor.img2Tz(1) != 0) {
    ledSet(DT_LED_IDLE);
    return;
  }

  uint16_t slot = 0, score = 0;
  if (Sensor.search(&slot, &score) == 0 && score > 0) {
    handleMatch(slot, score);
  } else {
    Serial.println("NO_MATCH");
    Serial.flush();
    ledSet(DT_LED_NOMATCH);
    delay(DT_RESULT_HOLD_MS);
    ledSet(DT_LED_IDLE);
  }

  // Don't re-fire while the finger is still down.
  uint32_t lifted = millis() + 5000;
  while (millis() < lifted && Sensor.genImg() == 0) delay(100);
}
