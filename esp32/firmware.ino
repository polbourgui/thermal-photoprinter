// Photobooth ESP32-C3 firmware
// Requires: FastLED (Arduino Library Manager)
// Board: ESP32C3 Dev Module, Arduino ESP32 core >= 2.0

#include <FastLED.h>

// ─── pins ────────────────────────────────────────────────────────────────────
#define LED_PIN      4
#define NUM_LEDS     45
#define BTN_PIN      6
#define BTN_LED_PIN  5

// ─── timing ──────────────────────────────────────────────────────────────────
#define BAUD_RATE    115200
#define DEBOUNCE_MS  50
#define FLASH_MS     300
#define COUNTDOWN_MS 3000
#define FADE_MS      400
#define FRAME_MS     16    // ~60 fps

// ─── colours ─────────────────────────────────────────────────────────────────
// Warm white: slightly yellow-orange tint
static const CRGB WARM_WHITE = CRGB(255, 200, 100);
// Dim warm white: post-flash hold
static const CRGB DIM_WARM   = CRGB(40, 30, 15);
// Flash: neutral white at 75%
static const CRGB FLASH_WHITE = CRGB(191, 191, 191);

// ─── state machine ───────────────────────────────────────────────────────────
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

CRGB leds[NUM_LEDS];       // displayed each frame
CRGB fromLeds[NUM_LEDS];   // snapshot at transition start
CRGB targetLeds[NUM_LEDS]; // computed from current state animation

// ─── button LED PWM ──────────────────────────────────────────────────────────
// Uses ESP32 LEDC peripheral for smooth PWM on the button LED.
// If using Arduino ESP32 core v3+, replace ledcSetup/ledcAttachPin with:
//   ledcAttach(BTN_LED_PIN, 1000, 8)
// and replace ledcWrite(0, val) with ledcWrite(BTN_LED_PIN, val)
#define BTN_LED_CH   0
#define BTN_LED_FREQ 1000
#define BTN_LED_RES  8

void setBtnLed(uint8_t brightness) {
  ledcWrite(BTN_LED_CH, brightness);
}

// ─── state transition ────────────────────────────────────────────────────────
void setState(State newState) {
  if (newState == state) return;
  memcpy(fromLeds, leds, sizeof(leds));
  transitionStart = millis();
  inTransition    = true;
  state           = newState;
  stateStart      = millis();
}

// ─── per-state LED animations ────────────────────────────────────────────────

void computeWaiting(CRGB* out) {
  // Slow blue breathing: 2s cycle
  unsigned long t = millis() % 2000;
  uint8_t b = (t < 1000)
    ? (uint8_t)map(t,    0, 1000, 10,  90)
    : (uint8_t)map(t, 1000, 2000, 90,  10);
  fill_solid(out, NUM_LEDS, CRGB(0, 0, b));
}

void computeIdle(CRGB* out) {
  // Gentle warm white sine wave rotating around the ring
  uint8_t offset = (millis() / 60) % NUM_LEDS;
  for (int i = 0; i < NUM_LEDS; i++) {
    uint8_t angle = ((uint16_t)(i + offset) * 255) / NUM_LEDS;
    uint8_t b     = qadd8(55, sin8(angle) / 4); // 55–118 range
    out[i] = CRGB(b, (uint8_t)(b * 200 / 255), (uint8_t)(b * 100 / 255));
  }
}

void computeCountdown(CRGB* out) {
  // Warm white arc depleting clockwise over COUNTDOWN_MS
  unsigned long elapsed = min((unsigned long)COUNTDOWN_MS, millis() - stateStart);
  // lit goes from NUM_LEDS down to 0
  int lit = map((long)elapsed, 0, COUNTDOWN_MS, NUM_LEDS, 0);

  for (int i = 0; i < NUM_LEDS; i++) {
    if (i < lit - 1) {
      out[i] = WARM_WHITE;
    } else if (i == lit - 1 && lit > 0) {
      // Soft leading edge: half brightness
      out[i] = CRGB(WARM_WHITE.r / 2, WARM_WHITE.g / 2, WARM_WHITE.b / 2);
    } else {
      out[i] = CRGB::Black;
    }
  }
}

void computeFlash(CRGB* out) {
  // Full flash for FLASH_MS then hold dim warm white until PRINTING arrives
  unsigned long elapsed = millis() - stateStart;
  fill_solid(out, NUM_LEDS, elapsed < FLASH_MS ? FLASH_WHITE : DIM_WARM);
}

void computePrinting(CRGB* out) {
  // Green comet chasing around the ring
  uint8_t pos = (millis() / 25) % NUM_LEDS;
  for (int i = 0; i < NUM_LEDS; i++) {
    int     dist = (i - pos + NUM_LEDS) % NUM_LEDS;
    uint8_t b    = (dist < 7) ? (uint8_t)(255 - dist * 36) : 0;
    out[i] = CRGB(0, b, 0);
  }
}

void computeDone(CRGB* out) {
  // One green flash (300ms on, 400ms fade out) then auto-return to IDLE
  unsigned long t = millis() - stateStart;
  if (t < 300) {
    fill_solid(out, NUM_LEDS, CRGB::Green);
  } else if (t < 700) {
    // Fade out the green
    uint8_t b = (uint8_t)map(t, 300, 700, 255, 0);
    fill_solid(out, NUM_LEDS, CRGB(0, b, 0));
  } else {
    setState(STATE_IDLE);
    computeIdle(out);
  }
}

void computeError(CRGB* out) {
  // Fast red blink
  bool on = (millis() / 150) % 2;
  fill_solid(out, NUM_LEDS, on ? CRGB::Red : CRGB::Black);
}

// ─── button LED brightness target per state ───────────────────────────────────
uint8_t btnLedTarget() {
  unsigned long t = millis();
  switch (state) {
    case STATE_WAITING:   return (t / 800) % 2 ? 160 : 0;    // slow blink
    case STATE_IDLE:      return 255;                          // solid
    case STATE_COUNTDOWN: return (t / 150) % 2 ? 255 : 0;    // fast blink
    case STATE_FLASH:     return 255;
    case STATE_PRINTING:  return 0;
    case STATE_DONE:      return 255;
    case STATE_ERROR:     return (t / 150) % 2 ? 255 : 0;
    default:              return 0;
  }
}

// ─── serial command parser ────────────────────────────────────────────────────
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

// ─── button with debounce ────────────────────────────────────────────────────
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
    // INPUT_PULLUP: LOW = pressed
    Serial.println(raw == LOW ? "BTN_PRESS" : "BTN_RELEASE");
  }
}

// ─── setup ───────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(BAUD_RATE);

  FastLED.addLeds<WS2815, LED_PIN>(leds, NUM_LEDS);
  FastLED.setBrightness(255);
  fill_solid(leds, NUM_LEDS, CRGB::Black);
  FastLED.show();

  pinMode(BTN_PIN, INPUT_PULLUP);

  ledcSetup(BTN_LED_CH, BTN_LED_FREQ, BTN_LED_RES);
  ledcAttachPin(BTN_LED_PIN, BTN_LED_CH);
  setBtnLed(0);

  Serial.println("READY");
}

// ─── main loop ───────────────────────────────────────────────────────────────
void loop() {
  handleSerial();
  handleButton();

  // 1. Compute target frame for current state
  switch (state) {
    case STATE_WAITING:   computeWaiting(targetLeds);   break;
    case STATE_IDLE:      computeIdle(targetLeds);      break;
    case STATE_COUNTDOWN: computeCountdown(targetLeds); break;
    case STATE_FLASH:     computeFlash(targetLeds);     break;
    case STATE_PRINTING:  computePrinting(targetLeds);  break;
    case STATE_DONE:      computeDone(targetLeds);      break;
    case STATE_ERROR:     computeError(targetLeds);     break;
  }

  // 2. Blend from previous state if transition in progress
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

  // 3. Output
  setBtnLed(btnLedTarget());
  FastLED.show();
  delay(FRAME_MS);
}
