#!/usr/bin/env python3
"""
Interactive hardware test — ESP8266 + LED ring.

Usage:
    python test_hardware.py [--port /dev/ttyUSB0]

Keys:
    w  → WAITING   (blue breathing)
    i  → IDLE      (warm white rotation)
    c  → COUNTDOWN (3s arc)
    f  → FLASH     (white burst)
    p  → PRINTING  (green comet)
    d  → DONE      (green flash → IDLE)
    e  → ERROR     (red blink)
    t  → trigger full sequence (COUNTDOWN → FLASH → PRINTING → DONE → IDLE)
    q  → quit
"""
import argparse
import sys
import threading
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed — run: pip install pyserial")

STATES = {
    "w": "WAITING",
    "i": "IDLE",
    "c": "COUNTDOWN",
    "f": "FLASH",
    "p": "PRINTING",
    "d": "DONE",
    "e": "ERROR",
}

HELP = """
Keys:
  w  WAITING    i  IDLE       c  COUNTDOWN
  f  FLASH      p  PRINTING   d  DONE
  e  ERROR      t  Full test sequence
  q  Quit
"""


def _reader(ser: serial.Serial, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            raw = ser.readline()
        except serial.SerialException:
            break
        if raw:
            line = raw.decode("utf-8", errors="ignore").strip()
            if line:
                print(f"\r← ESP8266: {line}\n> ", end="", flush=True)


def _send(ser: serial.Serial, cmd: str) -> None:
    ser.write(f"{cmd}\n".encode())
    ser.flush()
    print(f"→ {cmd}")


def _full_sequence(ser: serial.Serial) -> None:
    print("--- Full test sequence ---")
    _send(ser, "COUNTDOWN")
    time.sleep(3.2)
    _send(ser, "FLASH")
    time.sleep(0.4)
    _send(ser, "PRINTING")
    time.sleep(3.0)
    _send(ser, "DONE")
    time.sleep(1.8)
    _send(ser, "IDLE")
    print("--- Done ---")


def main() -> None:
    p = argparse.ArgumentParser(description="ESP8266 LED test")
    p.add_argument("--port", default="/dev/ttyUSB0", help="Serial port (default: /dev/ttyUSB0)")
    p.add_argument("--baud", type=int, default=115200)
    args = p.parse_args()

    print(f"Opening {args.port} @ {args.baud} baud …")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as exc:
        sys.exit(f"Cannot open port: {exc}")

    print("Waiting for ESP8266 boot (2.5s) …")
    time.sleep(2.5)
    ser.reset_input_buffer()
    print("Ready." + HELP)

    stop = threading.Event()
    t = threading.Thread(target=_reader, args=(ser, stop), daemon=True)
    t.start()

    try:
        while True:
            print("> ", end="", flush=True)
            # Read one character without echo (works in normal terminal mode)
            key = sys.stdin.readline().strip().lower()
            if not key:
                continue
            key = key[0]

            if key == "q":
                break
            elif key in STATES:
                _send(ser, STATES[key])
            elif key == "t":
                _full_sequence(ser)
            else:
                print(HELP)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        ser.close()
        print("\nClosed.")


if __name__ == "__main__":
    main()
