import time
import threading
import pretty_midi # For logging note names
from .midi_event_utils import send_note_on, send_note_off, send_all_notes_off

class NoteScheduler:
    """Handles the timing and scheduling of MIDI note events for playback."""

    def __init__(self, notes, output_device, get_current_time_func, tempo_scale_func, stop_flag, is_playing_flag):
        self.notes = sorted(notes, key=lambda note: note.start) if notes else []
        self.output_device = output_device # This should be an opened pygame.midi.Output object
        self.get_current_time = get_current_time_func # Function to get current playback time in seconds
        self.get_tempo_scale = tempo_scale_func # Function to get current tempo_scale
        self.stop_flag = stop_flag # threading.Event()
        self.is_playing_flag = is_playing_flag # A mutable flag or a function returning bool

        self.playback_thread = None
        self.notes_on = {}  # Tracks currently playing notes {note_index_in_sorted_list: start_playback_time}
        self.next_note_idx = 0
        self.log_events = True # Enable/disable MIDI event logging

    def start_playback_thread(self):
        if not self.notes:
            print("NoteScheduler: No notes to play.")
            if callable(self.is_playing_flag): # if it's a setter function
                self.is_playing_flag(False)
            else: # assume it's a mutable list/object [value]
                self.is_playing_flag[0] = False
            return

        if self.playback_thread is None or not self.playback_thread.is_alive():
            self.stop_flag.clear()
            # Reset playback state for the thread
            self.notes_on = {}
            self.next_note_idx = 0
            # Find the first note to play based on current time (e.g., if resuming or seeking)
            initial_current_time = self.get_current_time()
            while self.next_note_idx < len(self.notes) and \
                  self.notes[self.next_note_idx].start < initial_current_time:
                # If a note should have started but also ended before current time, skip it.
                # Otherwise, if it should have started and is still ongoing, it should be turned on.
                # This logic can be complex for robust resume/seek. For now, simple advance.
                self.next_note_idx += 1
            
            self.playback_thread = threading.Thread(target=self._run_schedule)
            self.playback_thread.daemon = True
            self.playback_thread.start()
            if self.log_events:
                print(f"NoteScheduler: Playback thread started. First note index: {self.next_note_idx}")
        else:
            if self.log_events: print("NoteScheduler: Playback thread already running.")


    def _run_schedule(self):
        if self.log_events:
            print(f"NoteScheduler: _run_schedule entered. Notes: {len(self.notes)}")
            if self.notes:
                print(f"NoteScheduler: First note: P{self.notes[0].pitch} S{self.notes[0].start} E{self.notes[0].end}")

        if not self.output_device:
            print("NoteScheduler: No output device available for playback.")
            if callable(self.is_playing_flag): self.is_playing_flag(False)
            else: self.is_playing_flag[0] = False
            return

        try:
            while not self.stop_flag.is_set():
                # Check if is_playing_flag (which might be a function call or list access) is false
                is_playing_check = self.is_playing_flag() if callable(self.is_playing_flag) else self.is_playing_flag[0]
                if not is_playing_check: # If playback was paused/stopped externally
                    time.sleep(0.01) # Sleep briefly and re-check
                    continue

                current_time = self.get_current_time()

                # Process note-offs
                notes_to_remove_from_on = []
                for note_idx, _ in self.notes_on.items():
                    note = self.notes[note_idx]
                    if current_time >= note.end:
                        send_note_off(self.output_device, note.pitch, 0, 0, self.log_events)
                        notes_to_remove_from_on.append(note_idx)
                
                for note_idx in notes_to_remove_from_on:
                    del self.notes_on[note_idx]

                # Process note-ons
                while (self.next_note_idx < len(self.notes) and
                       current_time >= self.notes[self.next_note_idx].start):
                    note = self.notes[self.next_note_idx]
                    if current_time < note.end: # Only play if not already ended
                        send_note_on(self.output_device, note.pitch, note.velocity, 0, self.log_events)
                        self.notes_on[self.next_note_idx] = current_time 
                    self.next_note_idx += 1
                
                # If all notes have been scheduled and all playing notes have ended
                if self.next_note_idx >= len(self.notes) and not self.notes_on:
                    if self.log_events: print("NoteScheduler: All notes played.")
                    if callable(self.is_playing_flag): self.is_playing_flag(False) # Signal end of playback
                    else: self.is_playing_flag[0] = False
                    break 

                tempo_scale = self.get_tempo_scale()
                sleep_duration = min(0.01, 0.005 / max(0.1, tempo_scale)) # Ensure tempo_scale isn't too small
                time.sleep(sleep_duration)

        except Exception as e:
            print(f"NoteScheduler: Error in playback loop: {e}")
        finally:
            # Ensure all notes are turned off when the thread exits or is stopped
            send_all_notes_off(self.output_device, self.log_events)
            if self.log_events: print("NoteScheduler: Playback thread finished.")
            # Do not set is_playing_flag to False here if stop_flag was the cause,
            # as the main controller should handle that. Only if playback naturally ends.


    def stop_playback_thread(self):
        self.stop_flag.set()
        if self.playback_thread and self.playback_thread.is_alive():
            self.playback_thread.join(timeout=0.5) # Wait briefly for thread to exit
        self.playback_thread = None
        # Crucially, turn off any lingering notes if the device is still valid
        if self.output_device:
            send_all_notes_off(self.output_device, self.log_events)
        if self.log_events: print("NoteScheduler: Playback thread explicitly stopped.")

    def update_notes(self, notes):
        """Updates the notes for the scheduler. Playback should be stopped before calling this."""
        if self.playback_thread and self.playback_thread.is_alive():
            print("NoteScheduler: Warning - updating notes while playback thread is active. Stop playback first.")
            self.stop_playback_thread() # Ensure it's stopped
            
        self.notes = sorted(notes, key=lambda note: note.start) if notes else []
        self.next_note_idx = 0
        self.notes_on = {}
        if self.log_events: print(f"NoteScheduler: Notes updated. Count: {len(self.notes)}")

    def reset_playback_position(self, position_seconds=0.0):
        """Resets the scheduler's internal pointers to a given time, typically 0."""
        self.next_note_idx = 0
        while self.next_note_idx < len(self.notes) and \
              self.notes[self.next_note_idx].start < position_seconds:
            self.next_note_idx += 1
        self.notes_on = {} # Clear any tracked 'on' notes
        if self.log_events: print(f"NoteScheduler: Playback position reset to {position_seconds}s. Next note index: {self.next_note_idx}")
