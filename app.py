import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon # Added for application icon
from ui.main_window import PianoRollMainWindow
import os
import pretty_midi

def main():
    app = QApplication(sys.argv)

    # Set application icon
    icon_path = "assets/icons/app_icon.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        print(f"Application icon set from {icon_path}")
    else:
        print(f"Warning: Application icon not found at {icon_path}. Using default icon.")

    # app.setStyle('Fusion') # Commented out to allow custom QSS to take full effect

    # Optional: Load initial MIDI data if a file is specified via an environment variable or argument
    # For simplicity, this example does not load initial data by default.
    # You could add logic here to load from a default file or command-line argument.
    # initial_midi_file = os.environ.get("INITIAL_MIDI_FILE") 
    # notes_to_load = []
    # if initial_midi_file and os.path.exists(initial_midi_file):
    #     try:
    #         midi_data = pretty_midi.PrettyMIDI(initial_midi_file)
    #         for instrument in midi_data.instruments:
    #             if not instrument.is_drum:
    #                 notes_to_load.extend(instrument.notes)
    #         print(f"Loaded {len(notes_to_load)} notes from {initial_midi_file}")
    #     except Exception as e:
    #         print(f"Error loading initial MIDI file {initial_midi_file}: {e}")
    # else:
    #     print("No initial MIDI file specified or found, starting empty.")
        
    # window = PianoRollMainWindow(notes_to_load)
    window = PianoRollMainWindow() # Start with an empty piano roll
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
