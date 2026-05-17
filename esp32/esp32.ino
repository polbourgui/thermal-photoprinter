// Photobooth — firmware ESP8266 (NodeMCU / Wemos D1 Mini)
// Requires: FastLED (Arduino Library Manager)
// Board: NodeMCU 1.0 (ESP-12E) or Generic ESP8266 Module

#include <FastLED.h>

// ─── pins (NodeMCU labels) ───────────────────────────────────────────────────
//  D1 = GPIO5  → WS2812B DATA
//  D6 = GPIO12 → LED bouton (PWM)
//  D5 = GPIO14 → Bouton poussoir (INPUT_PULLUP)
#define LED_PIN      5   // D1
#define BTN_LED_PIN  12  // D6
#define BTN_PIN      14  // D5

#define NUM_LEDS     45    // array upper bound — actual count set at runtime
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

uint16_t      gNumLeds        = 15;    // updated at runtime via LEDS:n
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
  // FLASH and DONE are instantaneous — a cross-fade defeats their visual intent.
  inTransition = (newState != STATE_FLASH && newState != STATE_DONE);
  state        = newState;
  stateStart   = millis();
}

// ─── animations LED par état ─────────────────────────────────────────────────

void computeWaiting(CRGB* out) {
  unsigned long t = millis() % 2000;
  uint8_t b = (t < 1000)
    ? (uint8_t)map(t,    0, 1000, 10, 90)
    : (uint8_t)map(t, 1000, 2000, 90, 10);
  fill_solid(out, gNumLeds, CRGB(0, 0, b));
}

void computeIdle(CRGB* out) {
  // Breathe: all LEDs pulse together in warm white over a ~4-second cycle.
  uint8_t phase  = (uint8_t)(millis() / 16);       // 256 steps per 4096 ms
  uint8_t sinVal = sin8(phase);                     // 0–255 sine wave
  uint8_t b      = (uint8_t)map(sinVal, 0, 255, 18, 160);
  fill_solid(out, gNumLeds, CRGB(b, (uint8_t)(b * 200 / 255), (uint8_t)(b * 100 / 255)));
}

void computeCountdown(CRGB* out) {
  unsigned long elapsed = min((unsigned long)COUNTDOWN_MS, millis() - stateStart);
  int lit = map((long)elapsed, 0, COUNTDOWN_MS, gNumLeds, 0);
  for (int i = 0; i < gNumLeds; i++) {
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
  fill_solid(out, gNumLeds, elapsed < FLASH_MS ? FLASH_WHITE : DIM_WARM);
}

void computePrinting(CRGB* out) {
  // 250 ms per step → ~3.75 s per full rotation on a 15-LED ring.
  uint8_t pos = (millis() / 120) % gNumLeds;
  for (int i = 0; i < gNumLeds; i++) {
    int trail = (i - pos + gNumLeds) % gNumLeds; // distance derrière la tête
    int lead  = (pos - i + gNumLeds) % gNumLeds; // distance devant la tête
    uint8_t b = 0;
    // Queue — falloff exponentiel doux
    if      (trail == 0) b = 220;
    else if (trail == 1) b = 130;
    else if (trail == 2) b = 65;
    else if (trail == 3) b = 28;
    else if (trail == 4) b = 8;
    // Halo avant — anticipe la tête, casse le bord franc
    if (lead == 1) b = max(b, (uint8_t)30);
    out[i] = CRGB(0, b, 0);
  }
}

void computeDone(CRGB* out) {
  // Single flash: instant full green, linear fade to black over 700ms, then IDLE.
  unsigned long t = millis() - stateStart;
  if (t < 700) {
    uint8_t b = (uint8_t)map(t, 0, 700, 220, 0);
    fill_solid(out, gNumLeds, CRGB(0, b, 0));
  } else {
    setState(STATE_IDLE);
    computeIdle(out);
  }
}

void computeError(CRGB* out) {
  bool on = (millis() / 150) % 2;
  fill_solid(out, gNumLeds, on ? CRGB::Red : CRGB::Black);
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
      if      (buf == "IDLE")            setState(STATE_IDLE);
      else if (buf == "COUNTDOWN")       setState(STATE_COUNTDOWN);
      else if (buf == "FLASH")           setState(STATE_FLASH);
      else if (buf == "PRINTING")        setState(STATE_PRINTING);
      else if (buf == "DONE")            setState(STATE_DONE);
      else if (buf == "ERROR")           setState(STATE_ERROR);
      else if (buf.startsWith("LEDS:")) {
        int n = buf.substring(5).toInt();
        if (n >= 1 && n <= NUM_LEDS) {
          gNumLeds = (uint16_t)n;
          fill_solid(leds,       NUM_LEDS, CRGB::Black);
          fill_solid(targetLeds, NUM_LEDS, CRGB::Black);
        }
      }
      else if (buf.startsWith("BRIGHT:")) {
        int b = buf.substring(7).toInt();
        FastLED.setBrightness((uint8_t)constrain(b, 1, 255));
      }
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
  FastLED.setBrightness(255); // safe default for 15 LEDs on USB — overridden by BRIGHT:n
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

  // Clear LEDs beyond active count so reducing gNumLeds leaves no ghost pixels.
  fill_solid(targetLeds + gNumLeds, NUM_LEDS - gNumLeds, CRGB::Black);

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
