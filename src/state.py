# Shared hardware references — set by main.py, read by web/app.py.
# Mirrors the pattern used in trigger.py for cross-module state.
_esp = None  # ESP32 instance, or None when --no-esp
