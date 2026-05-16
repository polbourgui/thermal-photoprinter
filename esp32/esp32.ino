// Photobooth — firmware ESP8266 (NodeMCU / Wemos D1 Mini)
// Requires: FastLED (Arduino Library Manager)
// Board: NodeMCU 1.0 (ESP-12E) or Generic ESP8266 Module

#include <FastLED.h>

// ─── pins (NodeMCU labels) ───────────────────────────────────────────────────
//  D2 = GPIO4  → WS2812B DATA
//  D1 = GPIO5  → LED bouton (PWM)
//  D5 = GPIO14 → Bouton poussoir (INPUT_PULLUP)
#define LED_PIN      4   // D2
#define BTN_LED_PIN  5   // D1
#define BTN_PIN      14  // D5

#define NUM_LEDS     60
#define BAUD_RATE    115200
#define DEBOUNCE_MS  50
#define FLASH_MS     300
#define COUNTDOWN_MS 3000
#define FADE_MS      400
#define FRAME_MS     20   // 50 fps — plus sûr que 60fps sur ESP8266

// ─── couleurs ────────────────────────────────────────────────────────────────
static const CRGB WARM_WHITE  = CRGB(255, 200, 100);
static const CRGB DIM_WARM    = CRGB(40,  30,  15);
static const CRGB FLASH_WHITE = CRGB(191, 191, 191); // 75%

// ─── machine à états ─────────────────────────────────────────────────────────
enum State {
  STATE_WAITING,
  STATE_IDLE,
  STATE_COUNTDOWN,
  STATE_FLASH,
  STATE_PRINTING,
  STATE_DONE,
  STATE_ERROR
};

State         state           = STATE_WAITING;
unsigned long stateStart      = 0;
unsigned long transitionStart = 0;
bool          inTransition    = false;

CRGB leds[NUM_LEDS];
CRGB fromLeds[NUM_LEDS];
CRGB targetLeds[NUM_LEDS];

// ─── LED bouton (PWM via analogWrite ESP8266) ─────────────────────────────────
// analogWriteRange(255) en setup() pour rester en 0-255 comme l'ESP32
void setBtnLed(uint8_t brightness) {
  analogWrite(BTN_LED_PIN, brightness);
}

// ─── transitions d'état ──────────────────────────────────────────────────────
void setState(State newState) {
  if (newState == state) return;
  memcpy(fromLeds, leds, sizeof(leds));
  transitionStart = millis();
  inTransition    = true;
  state           = newState;
  stateStart      = millis();
}

// ─── animations LED par état ─────────────────────────────────────────────────

void computeWaiting(CRGB* out) {
  unsigned long t = millis() % 2000;
  uint8_t b = (t < 1000)
    ? (uint8_t)map(t,    0, 1000, 10, 90)
    : (uint8_t)map(t, 1000, 2000, 90, 10);
  fill_solid(out, NUM_LEDS, CRGB(0, 0, b));
}

void computeIdle(CRGB* out) {
  uint8_t offset = (millis() / 60) % NUM_LEDS;
  for (int i = 0; i < NUM_LEDS; i++) {
    uint8_t angle = ((uint16_t)(i + offset) * 255) / NUM_LEDS;
    uint8_t b     = qadd8(55, sin8(angle) / 4);
    out[i] = CRGB(b, (uint8_t)(b * 200 / 255), (uint8_t)(b * 100 / 255));
  }
}

void computeCountdown(CRGB* out) {
  unsigned long elapsed = min((unsigned long)COUNTDOWN_MS, millis() - stateStart);
  int lit = map((long)elapsed, 0, COUNTDOWN_MS, NUM_LEDS, 0);
  for (int i = 0; i < NUM_LEDS; i++) {
    if (i < lit - 1) {
      out[i] = WARM_WHITE;
    } else if (i == lit - 1 && lit > 0) {
      out[i] = CRGB(WARM_WHITE.r / 2, WARM_WHITE.g / 2, WARM_WHITE.b / 2);
    } else {
      out[i] = CRGB::Black;
    }
  }
}

void computeFlash(CRGB* out) {
  unsigned long elapsed = millis() - stateStart;
  fill_solid(out, NUM_LEDS, elapsed < FLASH_MS ? FLASH_WHITE : DIM_WARM);
}

void computePrinting(CRGB* out) {
  uint8_t pos = (millis() / 25) % NUM_LEDS;
  for (int i = 0; i < NUM_LEDS; i++) {
    int     dist = (i - pos + NUM_LEDS) % NUM_LEDS;
    uint8_t b    = (dist < 7) ? (uint8_t)(255 - dist * 36) : 0;
    out[i] = CRGB(0, b, 0);
  }
}

void computeDone(CRGB* out) {
  unsigned long t = millis() - stateStart;
  if (t < 300) {
    fill_solid(out, NUM_LEDS, CRGB::Green);
  } else if (t < 700) {
    uint8_t b = (uint8_t)map(t, 300, 700, 255, 0);
    fill_solid(out, NUM_LEDS, CRGB(0, b, 0));
  } else {
    setState(STATE_IDLE);
    computeIdle(out);
  }
}

void computeError(CRGB* out) {
  bool on = (millis() / 150) % 2;
  fill_solid(out, NUM_LEDS, on ? CRGB::Red : CRGB::Black);
}

// ─── luminosité LED bouton par état ──────────────────────────────────────────
uint8_t btnLedTarget() {
  unsigned long t = millis();
  switch (state) {
    case STATE_WAITING:   return (t / 800) % 2 ? 160 : 0;
    case STATE_IDLE:      return 255;
    case STATE_COUNTDOWN: return (t / 150) % 2 ? 255 : 0;
    case STATE_FLASH:     return 255;
    case STATE_PRINTING:  return 0;
    case STATE_DONE:      return 255;
    case STATE_ERROR:     return (t / 150) % 2 ? 255 : 0;
    default:              return 0;
  }
}

// ─── lecture série ───────────────────────────────────────────────────────────
void handleSerial() {
  static String buf = "";
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      buf.trim();
      if      (buf == "IDLE")      setState(STATE_IDLE);
      else if (buf == "COUNTDOWN") setState(STATE_COUNTDOWN);
      else if (buf == "FLASH")     setState(STATE_FLASH);
      else if (buf == "PRINTING")  setState(STATE_PRINTING);
      else if (buf == "DONE")      setState(STATE_DONE);
      else if (buf == "ERROR")     setState(STATE_ERROR);
      buf = "";
    } else {
      buf += c;
    }
  }
}

// ─── bouton avec debounce ─────────────────────────────────────────────────────
void handleButton() {
  static bool          lastRaw       = HIGH;
  static bool          lastDebounced = HIGH;
  static unsigned long lastChange    = 0;

  bool raw = (bool)digitalRead(BTN_PIN);
  if (raw != lastRaw) {
    lastChange = millis();
    lastRaw    = raw;
  }
  if ((millis() - lastChange > DEBOUNCE_MS) && (raw != lastDebounced)) {
    lastDebounced = raw;
    Serial.println(raw == LOW ? "BTN_PRESS" : "BTN_RELEASE");
  }
}

// ─── setup ───────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(BAUD_RATE);

  // WS2812B — ordre de couleur GRB (standard WS2812)
  FastLED.addLeds<WS2812B, LED_PIN, GRB>(leds, NUM_LEDS);
  FastLED.setBrightness(255);
  fill_solid(leds, NUM_LEDS, CRGB::Black);
  FastLED.show();

  pinMode(BTN_PIN, INPUT_PULLUP);
  pinMode(BTN_LED_PIN, OUTPUT);
  analogWriteRange(255); // 8-bit PWM comme l'ESP32 (0-255)
  setBtnLed(0);

  Serial.println("READY");
}

// ─── boucle principale ────────────────────────────────────────────────────────
void loop() {
  handleSerial();
  handleButton();

  switch (state) {
    case STATE_WAITING:   computeWaiting(targetLeds);   break;
    case STATE_IDLE:      computeIdle(targetLeds);      break;
    case STATE_COUNTDOWN: computeCountdown(targetLeds); break;
    case STATE_FLASH:     computeFlash(targetLeds);     break;
    case STATE_PRINTING:  computePrinting(targetLeds);  break;
    case STATE_DONE:      computeDone(targetLeds);      break;
    case STATE_ERROR:     computeError(targetLeds);     break;
  }

  if (inTransition) {
    unsigned long elapsed = millis() - transitionStart;
    if (elapsed >= FADE_MS) {
      inTransition = false;
      memcpy(leds, targetLeds, sizeof(leds));
    } else {
      fract8 progress = (fract8)((elapsed * 255) / FADE_MS);
      for (int i = 0; i < NUM_LEDS; i++) {
        leds[i] = blend(fromLeds[i], targetLeds[i], progress);
      }
    }
  } else {
    memcpy(leds, targetLeds, sizeof(leds));
  }

  setBtnLed(btnLedTarget());
  FastLED.show();
  delay(FRAME_MS);
}
