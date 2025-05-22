import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QSizePolicy, QSlider, QStyle, QToolButton,
    QFrame, QSpacerItem, QDockWidget, QListWidget, QListWidgetItem,
    QFormLayout, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QDialog, QDialogButtonBox, QFileDialog, QApplication, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot, QSize, QEvent
from PySide6.QtGui import QKeyEvent, QColor, QPalette, QFont, QLinearGradient, QBrush
import pretty_midi
import time
import os

from note_display import PianoRollDisplay
from midi_player import MidiPlayer
# Assuming plugin_manager, export_utils are in the root or accessible via PYTHONPATH
from plugin_manager import PluginManager
from export_utils import export_to_midi
# UI components are now relative to the 'ui' package or root
from .custom_widgets import ModernSlider, ModernButton
from .plugin_dialogs import PluginParameterDialog
from .plugin_panel import PluginManagerPanel
from .transport_controls import TransportControls
from .event_handlers import MainWindowEventHandlersMixin, GlobalPlaybackHotkeyFilter # Added GlobalPlaybackHotkeyFilter
from config import theme # Import the theme configuration
from config.constants import INSTRUMENT_MAPPINGS # Added for instrument selection


class PianoRollMainWindow(QMainWindow, MainWindowEventHandlersMixin):
    """Piano roll window that displays MIDI notes graphically"""
    
    def __init__(self, midi_notes=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Piano Roll with Plugin Manager")
        self.setMinimumSize(1000, 600)
        
        self.midi_notes = midi_notes or []
        self.midi_player = MidiPlayer()
        self.bpm = 120
        self.total_duration = 10.0
        
        self._apply_stylesheet()
        
        if self.midi_notes:
            print(f"Setting initial {len(self.midi_notes)} notes in MIDI player")
            self.midi_player.set_notes(self.midi_notes)
            
        self._setup_central_widget()
        self._setup_main_layout()
        
        self.create_piano_roll_display()
        
        self.transport_controls = TransportControls()
        self.main_layout.addWidget(self.transport_controls)
        self._connect_transport_signals() # Existing connections

        # Connect new instrument changed signal
        self.transport_controls.instrumentChangedSignal.connect(self.instrument_changed_slot)
        
        # Initialize default instrument
        # This needs to be after midi_player is initialized and transport_controls are available
        default_instrument_name = "EZ Pluck" 
        # A more robust way to get the first key, if order matters and dict is not guaranteed
        # default_instrument_name = next(iter(INSTRUMENT_MAPPINGS)) if INSTRUMENT_MAPPINGS else None
        if default_instrument_name and default_instrument_name in INSTRUMENT_MAPPINGS:
            default_program_number = INSTRUMENT_MAPPINGS[default_instrument_name]
            # Ensure midi_player.set_instrument exists and is called.
            # This relies on midi_player.py being updated as per step 4 of the task.
            if hasattr(self.midi_player, 'set_instrument'):
                self.midi_player.set_instrument(default_program_number) 
                print(f"MainWindow: Default instrument '{default_instrument_name}' (Program: {default_program_number}) set on MidiPlayer.")
            else:
                print(f"MainWindow: MidiPlayer does not have set_instrument method. Cannot set default instrument.")
            
            # Update the transport controls UI to reflect this default
            self.transport_controls.set_selected_instrument(default_instrument_name)
            print(f"MainWindow: TransportControls UI set to default instrument '{default_instrument_name}'.")
        elif self.midi_notes: # If notes are loaded but default instrument isn't found, it's an issue.
             print(f"MainWindow: Default instrument '{default_instrument_name}' not found in INSTRUMENT_MAPPINGS.")
        
        self.create_plugin_manager()
        
        # self.installEventFilter(self) # MainWindow's own event filter is now secondary
        
        # Install the global event filter
        # Pass the main window's toggle_playback method directly
        app_instance = QApplication.instance()
        if app_instance:
            # Pass self.toggle_playback which handles UI updates (timer)
            self.global_hotkey_filter = GlobalPlaybackHotkeyFilter(self.toggle_playback, self) 
            app_instance.installEventFilter(self.global_hotkey_filter)
            print("Global playback hotkey filter installed with MainWindow.toggle_playback.")
        else:
            print("Error: QApplication.instance() is None. Global hotkey filter not installed.")
            self.global_hotkey_filter = None
            
        self.playback_timer = QTimer(self)
        self.update_timer_interval()
        self.playback_timer.timeout.connect(self.update_playback_position)

        # Initialize transport controls after all components are ready
        self.transport_controls.set_bpm_value(self.bpm)
        self.update_slider_range()


    def _apply_stylesheet(self):
        # Global stylesheet using constants from theme.py
        qss = f"""
            QMainWindow, QWidget {{
                background-color: {theme.APP_BG_COLOR.name()};
                color: {theme.PRIMARY_TEXT_COLOR.name()};
                font-family: "{theme.FONT_FAMILY_PRIMARY}";
                font-size: {theme.FONT_SIZE_M}pt;
            }}

            QLabel {{
                color: {theme.PRIMARY_TEXT_COLOR.name()};
                font-family: "{theme.FONT_FAMILY_PRIMARY}";
                font-size: {theme.FONT_SIZE_M}pt;
            }}

            QDockWidget::title {{
                background-color: {theme.PANEL_BG_COLOR.darker(110).name()};
                color: {theme.PRIMARY_TEXT_COLOR.name()};
                font-family: "{theme.FONT_FAMILY_PRIMARY}";
                font-size: {theme.FONT_SIZE_L}pt; /* Slightly larger for titles */
                font-weight: {theme.FONT_WEIGHT_BOLD};
                padding: {theme.PADDING_S}px {theme.PADDING_M}px;
                border-bottom: 1px solid {theme.BORDER_COLOR_NORMAL.name()};
            }}

            QDockWidget {{
                border: 1px solid {theme.BORDER_COLOR_NORMAL.name()};
                /* titlebar-close-icon and titlebar-normal-icon properties can be used
                   if custom icons are desired for dock widget float/close buttons */
            }}
            
            QScrollBar:horizontal {{
                background-color: {theme.PANEL_BG_COLOR.lighter(110).name()};
                height: 10px;
                margin: 0px 0px 0px 0px;
                border-radius: {theme.BORDER_RADIUS_S}px;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {theme.BORDER_COLOR_NORMAL.name()};
                min-width: 20px;
                border-radius: {theme.BORDER_RADIUS_S}px;
                margin: 2px 0px 2px 0px; /* Vertical margin */
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {theme.BORDER_COLOR_HOVER.name()};
            }}
            QScrollBar::handle:horizontal:pressed {{
                background-color: {theme.ACCENT_PRIMARY_COLOR.name()};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                border: none;
                background: none;
                width: 0px; /* Hide arrows */
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}

            QScrollBar:vertical {{
                background-color: {theme.PANEL_BG_COLOR.lighter(110).name()};
                width: 10px;
                margin: 0px 0px 0px 0px;
                border-radius: {theme.BORDER_RADIUS_S}px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {theme.BORDER_COLOR_NORMAL.name()};
                min-height: 20px;
                border-radius: {theme.BORDER_RADIUS_S}px;
                margin: 0px 2px 0px 2px; /* Horizontal margin */
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {theme.BORDER_COLOR_HOVER.name()};
            }}
            QScrollBar::handle:vertical:pressed {{
                background-color: {theme.ACCENT_PRIMARY_COLOR.name()};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
                height: 0px; /* Hide arrows */
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}

            /* Style for QScrollArea containing PianoRollDisplay - already partially styled inline */
            /* This global style can act as a fallback or default */
            QScrollArea {{
                background-color: {theme.PIANO_ROLL_BG_COLOR.name()}; 
                border: 1px solid {theme.BORDER_COLOR_NORMAL.name()}; /* Or none if preferred */
            }}
            
            /* Fallback QPushButton styling */
            QPushButton {{
                background-color: {theme.STANDARD_BUTTON_BG_COLOR.name()};
                color: {theme.STANDARD_BUTTON_TEXT_COLOR.name()};
                border: 1px solid {theme.BORDER_COLOR_NORMAL.name()}; /* Adding a subtle border */
                padding: {theme.PADDING_S}px {theme.PADDING_M}px;
                border-radius: {theme.BORDER_RADIUS_M}px;
                font-family: "{theme.FONT_FAMILY_PRIMARY}";
                font-size: {theme.FONT_SIZE_M}pt;
            }}
            QPushButton:hover {{
                background-color: {theme.STANDARD_BUTTON_HOVER_BG_COLOR.name()};
                border: 1px solid {theme.BORDER_COLOR_HOVER.name()};
            }}
            QPushButton:pressed {{
                background-color: {theme.STANDARD_BUTTON_PRESSED_BG_COLOR.name()};
            }}
            QPushButton:disabled {{
                background-color: {theme.DISABLED_BG_COLOR.name()};
                color: {theme.DISABLED_TEXT_COLOR.name()};
                border-color: {theme.DISABLED_BG_COLOR.darker(110).name()};
            }}
        """
        self.setStyleSheet(qss)

    def _setup_central_widget(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

    def _setup_main_layout(self):
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
    
    def create_plugin_manager(self):
        self.plugin_manager_panel = PluginManagerPanel(self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.plugin_manager_panel)
        self.plugin_manager_panel.notesGenerated.connect(self.set_midi_notes)
        self.plugin_manager_panel.set_current_notes(self.midi_notes)

    def _connect_transport_signals(self):
        self.transport_controls.playClicked.connect(self.start_playback)
        self.transport_controls.pauseClicked.connect(self.pause_playback)
        self.transport_controls.stopClicked.connect(self.stop_playback)
        self.transport_controls.seekPositionChanged.connect(self.slider_position_changed_slot)
        self.transport_controls.bpmChangedSignal.connect(self.bpm_changed_slot)

    def create_piano_roll_display(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1c1c20;
            }
        """)
        self.piano_roll = PianoRollDisplay(self.midi_notes)
        self.piano_roll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll_area.setWidget(self.piano_roll)
        self.main_layout.addWidget(scroll_area, 1)
        
        # Connect signals from PianoRollDisplay
        self.piano_roll.midiFileProcessed.connect(self.handle_midi_file_processed)
        self.piano_roll.notesChanged.connect(self.handle_notes_changed_from_display)

    @Slot(list)
    def handle_midi_file_processed(self, loaded_notes: list):
        """Handles notes loaded from a dropped MIDI file."""
        print(f"MainWindow: MIDI file processed, {len(loaded_notes)} notes received.")
        # set_midi_notes will update all components
        self.set_midi_notes(loaded_notes)
        # Optionally, reset playhead to start after loading a new file
        self.stop_playback() # Stop and reset playhead

    @Slot(list)
    def handle_notes_changed_from_display(self, current_notes_in_display: list):
        """Handles notes changed by direct interaction in PianoRollDisplay (paint, delete)."""
        print(f"MainWindow: Notes changed in display, {len(current_notes_in_display)} notes.")
        # Update the main list and propagate to other components
        # Avoid direct call to set_midi_notes if it causes redundant updates or signal loops
        # For now, assuming set_midi_notes is robust enough.
        # If PianoRollDisplay.notes IS the master list, then only need to update other components.
        # Let's assume MainWindow.midi_notes is the master.
        
        self.midi_notes = current_notes_in_display # Update master list
        
        # Propagate to MidiPlayer and PluginManagerPanel directly if piano_roll.set_notes was already called
        # by PianoRollDisplay itself before emitting notesChanged.
        # The PianoRollDisplay.set_notes calls notesChanged.emit(self.notes)
        # PianoRollDisplay.add_note calls notesChanged.emit(self.notes)
        # PianoRollDisplay.delete_note_at calls notesChanged.emit(self.notes)
        # So, current_notes_in_display is already the new state of piano_roll.notes.
        
        self.midi_player.set_notes(self.midi_notes)
        if hasattr(self, 'plugin_manager_panel'):
            self.plugin_manager_panel.set_current_notes(self.midi_notes)
        
        # Recalculate duration and update UI elements that depend on it
        max_end_time = 0
        if self.midi_notes:
            for note in self.midi_notes:
                if hasattr(note, 'end') and note.end > max_end_time:
                    max_end_time = note.end
        self.total_duration = max_end_time + 1.0 # Add padding
        self.update_slider_range()
        # self.piano_roll.update() # PianoRollDisplay should update itself after modification

    def set_midi_notes(self, notes: list): # Added type hint
        # This method is called by PluginManagerPanel.notesGenerated and handle_midi_file_processed
        # It should be the primary way to update notes across the application.
        print(f"PianoRollMainWindow: Setting {len(notes)} notes globally.")
        self.midi_notes = notes if notes is not None else []
        
        # Update PianoRollDisplay (if notes didn't originate from it)
        # To avoid signal loops, check source or block signals if necessary.
        # For now, assume direct call is okay.
        if hasattr(self, 'piano_roll'):
             self.piano_roll.set_notes(self.midi_notes) # This will emit piano_roll.notesChanged again.
                                                        # This could be problematic.
                                                        # Let's refine: set_notes in PianoRollDisplay should not emit if called from here.
                                                        # Or, handle_notes_changed_from_display should be the sole updater from PianoRoll.

        # The set_notes in PianoRollDisplay already emits notesChanged.
        # If this set_midi_notes is the main handler, then PianoRollDisplay.notesChanged should
        # primarily update MainWindow.midi_notes and then MainWindow updates others.

        # Let's simplify: MainWindow.set_midi_notes is the authority.
        # PianoRollDisplay.notesChanged will call a simpler handler in MainWindow
        # that just updates MainWindow.midi_notes, then calls this authoritative set_midi_notes.
        # This is getting circular.

        # Revised flow:
        # 1. User action in PianoRollDisplay (paint, delete) -> PianoRollDisplay updates its internal self.notes
        #    -> PianoRollDisplay emits notesChanged(self.notes)
        # 2. MIDI Drop in PianoRollDisplay -> PianoRollDisplay emits midiFileProcessed(loaded_notes)
        # 3. Plugin generates notes -> PluginManagerPanel emits notesGenerated(generated_notes)

        # MainWindow slots:
        # - handle_midi_file_processed(loaded_notes) -> calls self.set_midi_notes(loaded_notes)
        # - handle_notes_changed_from_display(new_notes_list) -> calls self.set_midi_notes(new_notes_list)
        # - set_midi_notes (called by plugin) -> this is the current method.

        # The current set_midi_notes method:
        # self.midi_notes = notes # Master list updated
        # self.piano_roll.set_notes(notes) # Updates display, emits notesChanged -> handle_notes_changed_from_display -> calls set_midi_notes again! (LOOP)

        # To break loop:
        # Option A: PianoRollDisplay.set_notes has an emit_signal=False flag.
        # Option B: MainWindow.set_midi_notes blocks signals from piano_roll temporarily.
        # Option C: Refactor signal connections.

        # Let's go with a flag in PianoRollDisplay.set_notes and add_note/delete_note_at
        # For now, I'll assume the current structure and proceed, then refine if loops occur.
        # The current PianoRollDisplay.set_notes *does* emit notesChanged.

        if hasattr(self, 'piano_roll') and self.piano_roll.notes != self.midi_notes: # Avoid redundant update if already set
            self.piano_roll.set_notes(self.midi_notes) 
        
        if notes:
            sample = notes[0]
            # print(f"Sample note: pitch={getattr(sample, 'pitch', 'N/A')}, " +
            #       f"start={getattr(sample, 'start', 'N/A')}, " +
            #       f"end={getattr(sample, 'end', 'N/A')}, " +
            #       f"velocity={getattr(sample, 'velocity', 'N/A')}")
        
        self.midi_player.set_notes(notes)
        
        max_end_time = 0
        for note in notes:
            if hasattr(note, 'end') and note.end > max_end_time:
                max_end_time = note.end
        
        self.total_duration = max_end_time + 1.0
        self.update_slider_range()
        
        if hasattr(self, 'plugin_manager_panel'):
            self.plugin_manager_panel.set_current_notes(notes)
        
        self.transport_controls.set_bpm_value(self.bpm) # Ensure BPM display is correct
        # self.update_slider_range() # Called above

    def clear_notes(self):
        print("PianoRollMainWindow: Clearing all notes.")
        self.midi_notes = []
        if hasattr(self, 'piano_roll'):
            self.piano_roll.set_notes([])
        if hasattr(self, 'midi_player'):
            self.midi_player.set_notes([])
        
        self.total_duration = 10.0
        self.update_slider_range()
        if hasattr(self, 'piano_roll'):
            self.piano_roll.set_playhead_position(0)
        
        if hasattr(self, 'transport_controls'):
            self.transport_controls.update_position_label(0)
            self.transport_controls.update_time_slider_value(0)

        if hasattr(self, 'plugin_manager_panel'):
            self.plugin_manager_panel.set_current_notes([])

    def receive_generated_note(self, note: pretty_midi.Note):
        if not hasattr(note, 'start') or not hasattr(note, 'end') or not hasattr(note, 'pitch'):
            print(f"PianoRollMainWindow: Received invalid note object: {note}")
            return

        self.midi_notes.append(note)
        if hasattr(self, 'piano_roll'):
            self.piano_roll.add_note(note)

        if note.end > self.total_duration:
            self.total_duration = note.end + 1.0
            self.update_slider_range()
        
        if hasattr(self, 'plugin_manager_panel'):
            self.plugin_manager_panel.set_current_notes(self.midi_notes)
    
    def toggle_playback(self):
        if self.midi_player.is_playing:
            # User wants pause to behave like stop: reset playhead to 0
            print("MainWindow: Toggle playback - was playing, now stopping and resetting.")
            self.stop_playback() 
        else:
            # If stopped or "paused" (which is now stop), start from beginning
            print("MainWindow: Toggle playback - was stopped/paused, now starting from beginning.")
            # Ensure playback position is at 0 before starting
            if self.midi_player.get_current_position() != 0.0:
                 self.midi_player.seek(0.0) # Ensure player is at start
                 self.piano_roll.set_playhead_position(0.0) # Ensure UI is at start
                 self.transport_controls.update_time_slider_value(0)
                 self.transport_controls.update_position_label(0)
            self.start_playback()
    
    def start_playback(self):
        if not self.midi_player.notes and self.midi_notes:
            print("FIXING: Re-setting notes before playback")
            self.midi_player.set_notes(self.midi_notes)
        time.sleep(0.1)
        self.midi_player.play()
        self.transport_controls.set_playing_state(True)
        self.update_timer_interval()
        self.playback_timer.start()
    
    def pause_playback(self):
        self.midi_player.pause()
        self.transport_controls.set_playing_state(False)
        self.playback_timer.stop()
    
    def stop_playback(self):
        self.midi_player.stop()
        self.transport_controls.set_playing_state(False)
        self.playback_timer.stop()
        self.transport_controls.update_time_slider_value(0)
        self.transport_controls.update_position_label(0)
        self.piano_roll.set_playhead_position(0)
    
    def update_playback_position(self):
        position = self.midi_player.get_current_position()
        slider_value_ms = int(position * 1000)
        self.transport_controls.update_time_slider_value(slider_value_ms)
        self.transport_controls.update_position_label(position)
        self.piano_roll.set_playhead_position(position)
        if hasattr(self, 'total_duration') and position >= self.total_duration and self.midi_player.is_playing:
            self.stop_playback()

    @Slot(float)
    def slider_position_changed_slot(self, position_seconds):
        self.midi_player.seek(position_seconds)
        self.transport_controls.update_position_label(position_seconds)
        self.piano_roll.set_playhead_position(position_seconds)

    @Slot(int)
    def bpm_changed_slot(self, new_bpm):
        self.bpm = new_bpm
        self.piano_roll.set_bpm(new_bpm)
        self.update_slider_range()
        self.update_timer_interval()
        if hasattr(self.midi_player, 'set_tempo'):
            self.midi_player.set_tempo(new_bpm)
    
    def update_timer_interval(self):
        base_interval = 16
        scaled_interval = min(30, max(5, int(base_interval * (120 / max(1, self.bpm)))))
        was_active = self.playback_timer.isActive()
        if was_active:
            self.playback_timer.stop()
        self.playback_timer.setInterval(scaled_interval)
        if was_active:
            self.playback_timer.start()
    
    def update_slider_range(self):
        if hasattr(self, 'total_duration'):
            scaled_duration_ms = int(self.total_duration * 1000)
            if hasattr(self, 'transport_controls'):
                self.transport_controls.update_time_slider_maximum(scaled_duration_ms)
        else:
            pass

    @Slot(str)
    def instrument_changed_slot(self, instrument_name: str):
        """Handles instrument changes from the TransportControls."""
        if instrument_name in INSTRUMENT_MAPPINGS:
            program_number = INSTRUMENT_MAPPINGS[instrument_name]
            if hasattr(self.midi_player, 'set_instrument'):
                self.midi_player.set_instrument(program_number)
                print(f"MainWindow: Instrument changed to '{instrument_name}' (Program: {program_number}).")
            else:
                print(f"MainWindow: MidiPlayer does not have set_instrument. Cannot change instrument to '{instrument_name}'.")
        else:
            print(f"MainWindow: Instrument '{instrument_name}' not found in INSTRUMENT_MAPPINGS.")
    
    # eventFilter and closeEvent are now inherited from MainWindowEventHandlersMixin

# Example usage (for testing, would be in main.py)
if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Load some initial MIDI data for testing if desired
    # initial_midi_file = "path_to_your_midi.mid" 
    # if os.path.exists(initial_midi_file):
    #     midi_data = pretty_midi.PrettyMIDI(initial_midi_file)
    #     notes_to_load = []
    #     for instrument in midi_data.instruments:
    #         if not instrument.is_drum:
    #             notes_to_load.extend(instrument.notes)
    # else:
    #     notes_to_load = []

    # window = PianoRollMainWindow(notes_to_load)
    window = PianoRollMainWindow() # Start with empty
    window.show()
    sys.exit(app.exec())
