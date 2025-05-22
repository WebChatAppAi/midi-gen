# Constants for piano roll display
MIN_PITCH = 21  # A0
MAX_PITCH = 108  # C8
WHITE_KEY_WIDTH = 60
BLACK_KEY_WIDTH = 40
WHITE_KEY_HEIGHT = 24
BLACK_KEY_HEIGHT = 16
BASE_TIME_SCALE = 100  # Base pixels per second (at 120 BPM)
DEFAULT_BPM = 120

# Constants for note labels
MIN_LABEL_PITCH = 36  # C2 MIDI note number (will be displayed as C3)
MAX_LABEL_PITCH = 96  # C7 MIDI note number (will be displayed as C8)

# SoundFont path
SOUNDFONT_PATH = "soundbank/soundfont.sf2"

# Instrument mappings
INSTRUMENT_MAPPINGS = {
    "EZ Pluck": 0,      # Acoustic Grand Piano
    "Synth Lead": 80,   # Lead 1 (square)
    "Warm Pad": 89,     # Pad 2 (warm)
    "Classic Piano": 1  # Bright Acoustic Piano
}
