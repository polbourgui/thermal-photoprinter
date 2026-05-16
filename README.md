# Photobooth thermique — PROOF

Photomaton autonome : bouton physique → décompte LED → capture → impression ticket thermique.  
Aucun écran, aucun son. Administration à distance via Tailscale.

---

## Hardware requis

| Composant | Modèle testé |
|---|---|
| SBC | Intel NUC |
| Webcam | USB (V4L2) |
| Contrôleur LED + bouton | ESP8266 NodeMCU / Wemos D1 Mini |
| Bandeau LED | WS2812B 5 V — 60 LED |
| Imprimante | Epson TM-M30 (USB) |

---

## Installation (NUC)

```bash
git clone <repo> && cd thermal-photoprinter
bash setup.sh
```

Le script installe :
- Dépendances système (`v4l-utils`, `libusb`, `python3-venv`)
- Environnement Python + packages (`requirements.txt`)
- Règles udev pour l'imprimante et l'ESP8266 (accès sans `sudo`)
- Arduino CLI + core ESP8266 + bibliothèque FastLED

---

## Flash du firmware ESP8266

```bash
# Compiler
arduino-cli compile --fqbn esp8266:esp8266:nodemcu esp32/

# Flasher (adapter le port si nécessaire)
arduino-cli upload --fqbn esp8266:esp8266:nodemcu --port /dev/ttyUSB0 esp32/
```

Brochage NodeMCU :

| Broche | GPIO | Fonction |
|---|---|---|
| D2 | 4 | DATA WS2812B |
| D1 | 5 | LED bouton (PWM) |
| D5 | 14 | Bouton poussoir (INPUT\_PULLUP) |

---

## Lancement

```bash
source .venv/bin/activate

# Test sans matériel complet
python src/main.py --no-camera --no-printer --no-esp

# Test avec ESP8266 + LED, sans caméra ni imprimante
python src/main.py --no-camera --no-printer

# Production
python src/main.py
```

Interface web (réglages layout + déclencheur virtuel) : **http://localhost:8080**

---

## Test du bandeau LED seul

```bash
source .venv/bin/activate
python src/test_hardware.py --port /dev/ttyUSB0
```

Touches : `w` WAITING · `i` IDLE · `c` COUNTDOWN · `f` FLASH · `p` PRINTING · `d` DONE · `e` ERROR · `t` séquence complète

---

## Structure

```
esp32/
└── firmware.ino        # Firmware ESP8266 (FastLED, serial protocol)
src/
├── main.py             # Boucle principale (--no-camera/printer/esp)
├── trigger.py          # Événement partagé (bouton physique ou web)
├── camera.py           # Capture OpenCV/V4L2
├── esp32.py            # Communication série ESP8266
├── image_processor.py  # Pipeline : tramage, contraste, gamma…
├── layout.py           # Composition ticket Pillow (header + photo + footer)
├── printer.py          # Impression ESC/POS (Epson TM-M30)
├── storage.py          # Sauvegarde JPEG brut + PNG ticket
├── shotgun.py          # API Shotgun.live (lieu / artistes, cache 30 min)
├── config.py           # Dataclasses + persistence JSON
├── counter.py          # Numéro de preuve incrémental
├── test_hardware.py    # Test interactif LED (clavier)
└── web/
    ├── app.py          # FastAPI (réglages, mockup, /trigger)
    └── templates/
        └── index.html
config/                 # settings.json + counter.json (auto-générés)
fonts/                  # Polices TTF/OTF personnalisées (optionnel)
photos/                 # Photos brutes + tickets (YYYY-MM-DD/)
setup.sh                # Script d'installation NUC
```

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `WEB_PORT` | `8080` | Port de l'interface web |
| `CONFIG_PATH` | `config/settings.json` | Chemin du fichier de config |
| `SHOTGUN_API_TOKEN` | — | Token API Shotgun.live (optionnel) |

Créées dans `.env` par `setup.sh`.

---

## Protocole série ESP8266 ↔ NUC

| Direction | Message | Déclencheur |
|---|---|---|
| NUC → ESP | `IDLE` `COUNTDOWN` `FLASH` `PRINTING` `DONE` `ERROR` | État courant |
| ESP → NUC | `BTN_PRESS` `BTN_RELEASE` | Bouton physique |
| ESP → NUC | `READY` | Au démarrage |
