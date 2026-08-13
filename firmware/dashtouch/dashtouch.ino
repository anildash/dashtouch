// Dashboard Touch firmware — see docs/protocol.md for every line this
// prints or accepts. This file is the state machine; the protocol lives
// in link.cpp (Task 4) and the sensor driver in r503.cpp.
#include <Arduino.h>
#include "config.h"
#include "r503.h"
#include "led.h"

HardwareSerial FingerSerial(1);
R503 Sensor;
bool g_sensorOk = false;
uint16_t g_capacity = 0;

void setup() {
  Serial.begin(115200);
  delay(1500);

  Sensor.begin(FingerSerial, DT_FP_RX_PIN, DT_FP_TX_PIN, DT_UART_BAUD);
  ledInit(&Sensor);

  Serial.printf("BOOT dashtouch %s proto=1\n", DT_FW_VERSION);

  g_sensorOk = (Sensor.verifyPassword() == 0);
  if (g_sensorOk) {
    Sensor.readSysPara(&g_capacity, nullptr);
    Serial.println("READY");
    ledSet(DT_LED_IDLE);
    boardLedRed(false);
  } else {
    Serial.println("ERR sensor_unreachable");
    ledSet(DT_LED_BOOT_FAIL);  // best effort; ring may be unreachable
    boardLedRed(true);         // this one the sensor can't take down
  }
  Serial.flush();
}

void loop() {
  delay(50);  // state machine lands in Task 5
}
