#include "link.h"
#include "config.h"
#include "secrets.h"
#include "vectors.h"
#include "r503.h"
#include "led.h"
#include "settings.h"
#include "esp_random.h"
#include "mbedtls/md.h"
#include "mbedtls/gcm.h"

extern bool g_sensorOk;
extern uint16_t g_capacity;
extern R503 Sensor;

void (*linkOnEnroll)(uint16_t) = nullptr;
void (*linkOnDelete)(uint16_t) = nullptr;
void (*linkOnFpSwapChanged)() = nullptr;

static uint32_t s_counter = 0;
static uint8_t s_lastNonce[16];
static bool s_evPending = false;

static void hmac256(const uint8_t* key, size_t klen,
                    const uint8_t* msg, size_t mlen, uint8_t out[32]) {
  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  mbedtls_md_hmac(info, key, klen, msg, mlen, out);
}

static void toHex(const uint8_t* in, size_t n, char* out) {
  static const char* d = "0123456789abcdef";
  for (size_t i = 0; i < n; i++) {
    out[2 * i] = d[in[i] >> 4];
    out[2 * i + 1] = d[in[i] & 0xf];
  }
  out[2 * n] = 0;
}

static int fromHex(const char* in, uint8_t* out, size_t maxN) {
  size_t len = strlen(in);
  if (len % 2 || len / 2 > maxN) return -1;
  for (size_t i = 0; i < len / 2; i++) {
    char b[3] = {in[2 * i], in[2 * i + 1], 0};
    out[i] = (uint8_t)strtoul(b, nullptr, 16);
  }
  return (int)(len / 2);
}

void linkBuildEv(uint16_t slot, uint16_t score, char* out, size_t outLen) {
  esp_fill_random(s_lastNonce, sizeof(s_lastNonce));
  s_counter++;
  s_evPending = true;

  char nonceHex[33];
  toHex(s_lastNonce, 16, nonceHex);
  char canonical[96];
  snprintf(canonical, sizeof(canonical), "EV %s %lu %u %u",
           nonceHex, (unsigned long)s_counter, slot, score);
  uint8_t mac[32];
  hmac256(PAIRING_KEY, 32, (const uint8_t*)canonical, strlen(canonical), mac);
  char macHex[65];
  toHex(mac, 32, macHex);
  snprintf(out, outLen, "%s %s", canonical, macHex);
}

static void deriveResponseKey(const uint8_t nonce[16], uint8_t out[32]) {
  uint8_t msg[21];
  memcpy(msg, "DTPW1", 5);
  memcpy(msg + 5, nonce, 16);
  hmac256(PAIRING_KEY, 32, msg, sizeof(msg), out);
}

bool linkDecryptPw(const char* line, char* pwOut, size_t pwLen) {
  if (!s_evPending) return false;
  // Parse: PW <gcmnonce_hex24> <ct_hex>
  if (strncmp(line, "PW ", 3) != 0) return false;
  const char* p = line + 3;
  const char* sp = strchr(p, ' ');
  if (!sp || (size_t)(sp - p) != 24) return false;

  char gcmHex[25];
  memcpy(gcmHex, p, 24);
  gcmHex[24] = 0;
  uint8_t gcmNonce[12];
  if (fromHex(gcmHex, gcmNonce, sizeof(gcmNonce)) != 12) return false;

  uint8_t ctbuf[192];
  int ctLen = fromHex(sp + 1, ctbuf, sizeof(ctbuf));
  if (ctLen < 17) return false;  // at least 1 byte + 16-byte tag
  size_t ptLen = ctLen - 16;
  if (ptLen >= pwLen) return false;

  uint8_t key[32];
  deriveResponseKey(s_lastNonce, key);

  mbedtls_gcm_context g;
  mbedtls_gcm_init(&g);
  mbedtls_gcm_setkey(&g, MBEDTLS_CIPHER_ID_AES, key, 256);
  int rc = mbedtls_gcm_auth_decrypt(&g, ptLen, gcmNonce, sizeof(gcmNonce),
                                    nullptr, 0, ctbuf + ptLen, 16,
                                    ctbuf, (uint8_t*)pwOut);
  mbedtls_gcm_free(&g);

  memset(key, 0, sizeof(key));
  s_evPending = false;  // one shot, success or fail
  if (rc != 0) {
    memset(pwOut, 0, pwLen);  // Unauthenticated plaintext must never survive
    return false;
  }
  pwOut[ptLen] = 0;
  return true;
}

void linkHandleCommand(const String& line) {
  if (line == "PING") {
    Serial.println("PONG");
  } else if (line == "STATUS") {
    Serial.printf("STATUS_OK proto=1 fw=%s sensor=%s cap=%u\n",
                  DT_FW_VERSION, g_sensorOk ? "ok" : "fail", g_capacity);
  } else if (line == "SELFTEST") {
    Serial.println(linkSelfTest() ? "SELFTEST_OK" : "SELFTEST_FAIL");
  } else if (line == "INDEX") {
    uint8_t bitmap[32];
    int c = Sensor.readIndexTable(0, bitmap);
    if (c == 0) {
      char hex[65];
      toHex(bitmap, 32, hex);
      Serial.printf("INDEX_OK %s\n", hex);
    } else {
      Serial.printf("INDEX_FAIL %d\n", c);
    }
  } else if (line.startsWith("ENROLL ")) {
    uint16_t slot = line.substring(7).toInt();
    if (slot >= DT_MIN_SLOT && slot <= DT_MAX_SLOT && linkOnEnroll)
      linkOnEnroll(slot);
    else
      Serial.println("ENROLL_FAIL badslot");
  } else if (line.startsWith("DELETE ")) {
    uint16_t slot = line.substring(7).toInt();
    if (slot >= DT_MIN_SLOT && slot <= DT_MAX_SLOT && linkOnDelete)
      linkOnDelete(slot);
    else
      Serial.println("DELETE_FAIL badslot");
  } else if (line == "SETTINGS") {
    Serial.printf("SETTINGS_OK idle_color=%u idle_style=%u press_enter=%u fp_swap=%u\n",
                  settingsIdleColor(), settingsIdleStyle(),
                  settingsPressEnter() ? 1 : 0, settingsFpSwap() ? 1 : 0);
  } else if (line.startsWith("SET ")) {
    // "SET <key> <value>"
    String rest = line.substring(4);
    int sp = rest.indexOf(' ');
    String key = sp >= 0 ? rest.substring(0, sp) : rest;
    String valStr = sp >= 0 ? rest.substring(sp + 1) : "";
    long val = valStr.toInt();
    if (key == "idle_color") {
      if (val >= 0 && val <= 7 && settingsSetIdleColor((uint8_t)val)) {
        Serial.printf("SET_OK idle_color %u\n", (unsigned)val);
        ledApplyIdleNow();
      } else {
        Serial.println("SET_FAIL idle_color");
      }
    } else if (key == "idle_style") {
      if (val >= 1 && val <= 2 && settingsSetIdleStyle((uint8_t)val)) {
        Serial.printf("SET_OK idle_style %u\n", (unsigned)val);
        ledApplyIdleNow();
      } else {
        Serial.println("SET_FAIL idle_style");
      }
    } else if (key == "press_enter") {
      bool v = (val != 0);
      settingsSetPressEnter(v);
      Serial.printf("SET_OK press_enter %u\n", v ? 1 : 0);
    } else if (key == "fp_swap") {
      bool v = (val != 0);
      settingsSetFpSwap(v);
      // Re-init the sensor UART with the new orientation and re-run the
      // handshake right now — no reboot required to find out if it works.
      if (linkOnFpSwapChanged) linkOnFpSwapChanged();
      Serial.printf("SET_OK fp_swap %u\n", v ? 1 : 0);
    } else {
      Serial.printf("SET_FAIL %s\n", key.c_str());
    }
  } else if (line.length()) {
    Serial.printf("UNKNOWN_CMD %s\n", line.c_str());
  }
  Serial.flush();
}

bool linkSelfTest() {
  // 1) HMAC over the vector canonical string must match TV_HMAC.
  char nonceHex[33];
  toHex(TV_NONCE, 16, nonceHex);
  char canonical[96];
  snprintf(canonical, sizeof(canonical), "EV %s %lu %u %u",
           nonceHex, (unsigned long)TV_COUNTER, TV_SLOT, TV_SCORE);
  uint8_t mac[32];
  hmac256(TV_KEY, 32, (const uint8_t*)canonical, strlen(canonical), mac);
  if (memcmp(mac, TV_HMAC, 32) != 0) return false;

  // 2) Decrypting TV_PW_LINE with the vector key/nonce must yield
  //    TV_PASSWORD. Temporarily wire the static state to vector values.
  uint8_t savedNonce[16];
  memcpy(savedNonce, s_lastNonce, 16);
  bool savedPending = s_evPending;

  memcpy(s_lastNonce, TV_NONCE, 16);
  s_evPending = true;
  // deriveResponseKey uses PAIRING_KEY, but vectors use TV_KEY — check
  // the derived key directly instead of going through linkDecryptPw:
  uint8_t msg[21];
  memcpy(msg, "DTPW1", 5);
  memcpy(msg + 5, TV_NONCE, 16);
  uint8_t rkey[32];
  hmac256(TV_KEY, 32, msg, sizeof(msg), rkey);
  bool keyOk = (memcmp(rkey, TV_RESPONSE_KEY, 32) == 0);

  // 3) GCM-decrypt the vector PW line with the vector response key.
  const char* sp1 = TV_PW_LINE + 3;
  const char* sp2 = strchr(sp1, ' ');
  char gcmHex[25];
  memcpy(gcmHex, sp1, 24);
  gcmHex[24] = 0;
  uint8_t gcmNonce[12];
  fromHex(gcmHex, gcmNonce, sizeof(gcmNonce));
  uint8_t ctbuf[64];
  int ctLen = fromHex(sp2 + 1, ctbuf, sizeof(ctbuf));
  uint8_t pt[48] = {0};
  mbedtls_gcm_context g;
  mbedtls_gcm_init(&g);
  mbedtls_gcm_setkey(&g, MBEDTLS_CIPHER_ID_AES, TV_RESPONSE_KEY, 256);
  int rc = mbedtls_gcm_auth_decrypt(&g, ctLen - 16, gcmNonce, 12, nullptr, 0,
                                    ctbuf + ctLen - 16, 16, ctbuf, pt);
  mbedtls_gcm_free(&g);
  bool ptOk = (rc == 0 && strcmp((char*)pt, TV_PASSWORD) == 0);

  memcpy(s_lastNonce, savedNonce, 16);
  s_evPending = savedPending;
  return keyOk && ptOk;
}
