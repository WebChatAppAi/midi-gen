import time
import threading
import pygame.midi # For init/quit if other pygame.midi parts are used
import pretty_midi # For Note object type hint
# from .device_manager import DeviceManager # Removed
from .note_scheduler import NoteScheduler
from .midi_event_utils import send_all_notes_off
from .fluidsynth_player import FluidSynthPlayer
from config.constants import SOUNDFONT_PATH, INSTRUMENT_MAPPINGS

class PlaybackController:
    """Controls MIDI playback, managing state, FluidSynthPlayer, and note scheduling."""

    def __init__(self):
        # pygame.midi.init() # Ensure this is called once if other pygame.midi (e.g. input) is used.
        # For now, playback is via FluidSynthPlayer.

        self.fluidsynth_player = None
        self.log_events = True # For debugging - moved up for use in init

        try:
            self.fluidsynth_player = FluidSynthPlayer(SOUNDFONT_PATH)
            if not self.fluidsynth_player.fs: # Check if FluidSynth was initialized properly
                if self.log_events: print("PlaybackController: FluidSynthPlayer failed to initialize (fs is None). Playback disabled.")
                self.fluidsynth_player = None # Ensure it's None if failed
            else:
                if self.log_events: print("PlaybackController: FluidSynthPlayer initialized successfully.")
                # Set default instrument
                self.set_instrument(INSTRUMENT_MAPPINGS.get("EZ Pluck", 0)) # Default to program 0 if "EZ Pluck" is missing
        except Exception as e:
            if self.log_events: print(f"PlaybackController: Exception during FluidSynthPlayer initialization: {e}. Playback disabled.")
            self.fluidsynth_player = None

        self.notes = []
        self._is_playing_internal = False # Actual state of playback for scheduler
        self.paused = False
        self.current_playback_time_sec = 0.0 # Time from start of current playback segment
        self.playback_start_real_time = 0.0  # time.time() when playback (re)started
        self.pause_start_time_sec = 0.0 # Stores current_playback_time_sec when paused

        self.tempo_bpm = 120.0
        self.tempo_scale_factor = 1.0 # (current_bpm / 120.0)

        self.stop_flag = threading.Event()
        
        # The NoteScheduler needs a way to know if it should be actively processing.
        # We pass a list containing our internal playing state.
        self._is_playing_for_scheduler = [self._is_playing_internal] 
        
        # Scheduler is created when notes are set, or on first play
        self.note_scheduler = None
        # self.log_events = True # Moved up

    def _ensure_scheduler(self):
        """Creates a NoteScheduler instance if one doesn't exist or if midi_output_target changed."""
        if not self.fluidsynth_player:
            if self.log_events: print("PlaybackController: Cannot ensure scheduler, FluidSynthPlayer not available.")
            self.note_scheduler = None # Ensure no old scheduler is used
            return

        # Condition for recreating scheduler:
        # 1. No scheduler exists.
        # 2. Scheduler exists but its target is not the current fluidsynth_player.
        if not self.note_scheduler or self.note_scheduler.midi_output_target != self.fluidsynth_player:
            if self.note_scheduler: # If exists, stop its thread before replacing
                self.note_scheduler.stop_playback_thread()
            
            self.note_scheduler = NoteScheduler(
                notes=self.notes,
                midi_output_target=self.fluidsynth_player, # Pass the FluidSynthPlayer instance
                get_current_time_func=self.get_current_position,
                tempo_scale_func=lambda: self.tempo_scale_factor,
                stop_flag=self.stop_flag,
                is_playing_flag=self._is_playing_for_scheduler, # Pass the mutable list
                log_events=self.log_events
            )
            if self.log_events: print("PlaybackController: NoteScheduler created/recreated for FluidSynthPlayer.")
        elif self.note_scheduler:
            # If scheduler exists and target is current, ensure its notes are current
            self.note_scheduler.update_notes(self.notes)


    def set_notes(self, notes: list[pretty_midi.Note]):
        # if self.log_events: print(f"PlaybackController: Setting {len(notes)} notes.") # Original line
        # Stop current playback before changing notes
        # Check if fluidsynth_player is available before calling stop, as stop might try to use it.
        if self.fluidsynth_player:
            if self.log_events: print(f"PlaybackController: Setting {len(notes)} notes. Stopping current playback.")
            self.stop() 
        else:
            # If no player, still log and prepare notes, but playback won't happen.
            if self.log_events: print(f"PlaybackController: Setting {len(notes)} notes. FluidSynthPlayer not available.")
            # Manually ensure flags are reset as stop() would do.
            self._is_playing_internal = False
            self._is_playing_for_scheduler[0] = False
            self.paused = False


        self.notes = notes if notes else []
        self.current_playback_time_sec = 0.0
        self.pause_start_time_sec = 0.0
        
        if self.fluidsynth_player: # Only update/ensure scheduler if player is available
            if self.note_scheduler:
                self.note_scheduler.update_notes(self.notes)
                self.note_scheduler.reset_playback_position(0.0)
            else:
                self._ensure_scheduler() # Create scheduler if it wasn't there
        else:
            if self.log_events: print("PlaybackController: FluidSynthPlayer not available, cannot ensure scheduler for new notes.")


    def play(self):
        if self.log_events: print(f"PlaybackController: Play called. Currently playing: {self._is_playing_internal}, Paused: {self.paused}")
        
        if not self.fluidsynth_player:
            if self.log_events: print("PlaybackController: Cannot play, FluidSynthPlayer not available.")
            return
            
        if not self.notes:
            if self.log_events: print("PlaybackController: No notes to play.")
            return

        self._ensure_scheduler() # This will now use self.fluidsynth_player
        if not self.note_scheduler or not self.note_scheduler.midi_output_target: # Changed from output_device
            if self.log_events: print("PlaybackController: Cannot play, scheduler or FluidSynthPlayer not available for scheduler.")
            return

        if self._is_playing_internal and not self.paused: # Already playing
            return

        self.stop_flag.clear()
        self._is_playing_internal = True
        self._is_playing_for_scheduler[0] = True # Update shared flag for scheduler

        if self.paused: # Resuming
            # Adjust start time to account for pause duration
            self.playback_start_real_time = time.time() - self.pause_start_time_sec / self.tempo_scale_factor
            self.paused = False
            if self.log_events: print(f"PlaybackController: Resuming from {self.pause_start_time_sec:.2f}s.")
        else: # Starting new or from a seek
            self.playback_start_real_time = time.time() - self.current_playback_time_sec / self.tempo_scale_factor
            self.note_scheduler.reset_playback_position(self.current_playback_time_sec)
            if self.log_events: print(f"PlaybackController: Starting playback from {self.current_playback_time_sec:.2f}s.")
        
        self.note_scheduler.start_playback_thread()


    def pause(self):
        if self.log_events: print("PlaybackController: Pause called.")
        if self._is_playing_internal and not self.paused:
            self.paused = True
            self._is_playing_internal = False # Stop the scheduler's active loop
            self._is_playing_for_scheduler[0] = False
            # self.note_scheduler.stop_playback_thread() # Not stopping thread, just pausing its activity
            
            self.pause_start_time_sec = self.get_current_position() # Store accurate pause time
            if self.log_events: print(f"PlaybackController: Paused at {self.pause_start_time_sec:.2f}s.")
            
            # Send all notes off when pausing
            if self.fluidsynth_player: # Use fluidsynth_player directly
                send_all_notes_off(self.fluidsynth_player, self.log_events)
        

    def stop(self):
        if self.log_events: print("PlaybackController: Stop called.")
        self._is_playing_internal = False
        self._is_playing_for_scheduler[0] = False # Update shared flag
        self.paused = False
        
        # NoteScheduler's stop_playback_thread will call send_all_notes_off with its midi_output_target
        if self.note_scheduler:
            self.note_scheduler.stop_playback_thread() 
        elif self.fluidsynth_player: 
            # If scheduler wasn't active/created, but player exists, ensure notes are off
            send_all_notes_off(self.fluidsynth_player, self.log_events)
        
        self.current_playback_time_sec = 0.0
        self.pause_start_time_sec = 0.0
        if self.note_scheduler: # Reset scheduler's internal state too
            self.note_scheduler.reset_playback_position(0.0)


    def seek(self, position_sec: float):
        if self.log_events: print(f"PlaybackController: Seek to {position_sec:.2f}s.")
        
        if not self.fluidsynth_player:
            if self.log_events: print("PlaybackController: Cannot seek, FluidSynthPlayer not available.")
            # Set time but don't attempt MIDI operations or scheduler interaction
            self.current_playback_time_sec = max(0.0, position_sec)
            self.pause_start_time_sec = self.current_playback_time_sec
            return

        # Stop notes before seek, regardless of playing state
        send_all_notes_off(self.fluidsynth_player, self.log_events)

        self.current_playback_time_sec = max(0.0, position_sec)
        self.pause_start_time_sec = self.current_playback_time_sec # If paused, resume from here

        if self.note_scheduler: # Should exist if fluidsynth_player is available and play/set_notes was called
            self.note_scheduler.reset_playback_position(self.current_playback_time_sec)

        # Adjust playback_start_real_time for accurate get_current_position calculation
        # This needs to happen whether playing, paused, or stopped, so get_current_position is correct if play() is called next.
        self.playback_start_real_time = time.time() - self.current_playback_time_sec / self.tempo_scale_factor

        if self._is_playing_internal and not self.paused: # Was playing, restart scheduler thread
            if self.note_scheduler:
                 # Stop existing thread and clear its events first.
                self.note_scheduler.stop_playback_thread(join=False) # Don't join here, start_playback_thread will handle it or create new.
                # Ensure stop_flag is clear before restarting, as stop_playback_thread sets it.
                self.stop_flag.clear() 
                # Ensure _is_playing_for_scheduler is true so the new thread runs.
                self._is_playing_for_scheduler[0] = True 
                self.note_scheduler.start_playback_thread()
        elif self.paused:
            # If paused, the current_playback_time_sec is already set.
            # self.pause_start_time_sec is also self.current_playback_time_sec
            # When play() is called, it will resume from this new self.pause_start_time_sec.
            pass

        if self.log_events: print(f"PlaybackController: Seek complete. Current time: {self.current_playback_time_sec:.2f}s")


    def get_current_position(self) -> float:
        if self._is_playing_internal and not self.paused:
            elapsed_real_time = time.time() - self.playback_start_real_time
            self.current_playback_time_sec = elapsed_real_time * self.tempo_scale_factor
            return self.current_playback_time_sec
        elif self.paused:
            return self.pause_start_time_sec 
        return self.current_playback_time_sec # Stopped or not yet played

    @property
    def is_playing(self) -> bool:
        # This property reflects if the controller *thinks* it should be playing,
        # which might differ slightly from the scheduler thread's instantaneous state.
        return self._is_playing_internal and not self.paused

    def toggle_playback(self):
        """Toggles playback between play and pause."""
        if self.is_playing:
            if self.log_events: print("PlaybackController: Toggling playback (was playing, now pausing).")
            self.pause()
        else:
            # If it was paused, play will resume. If stopped, play will start from current_playback_time_sec (usually 0).
            if self.log_events: print("PlaybackController: Toggling playback (was not playing, now playing).")
            self.play()

    def set_tempo(self, bpm: float):
        if bpm <= 0:
            if self.log_events: print("PlaybackController: BPM must be positive.")
            return
        
        if self.log_events: print(f"PlaybackController: Setting tempo to {bpm} BPM.")
        
        current_pos_before_tempo_change = self.get_current_position()
        
        self.tempo_bpm = float(bpm)
        self.tempo_scale_factor = self.tempo_bpm / 120.0
        
        # Adjust start time to maintain current logical position with new tempo
        if self._is_playing_internal or self.paused:
             self.playback_start_real_time = time.time() - (current_pos_before_tempo_change / self.tempo_scale_factor)
        
        if self.log_events: print(f"PlaybackController: Tempo scale factor: {self.tempo_scale_factor}")

    def cleanup(self):
        """Clean up resources, especially the MIDI device."""
        if self.log_events: print("PlaybackController: Cleanup called.")
        self.stop() # Ensure playback is stopped and thread joined
        self.device_manager.close_device()
        # pygame.midi.quit() # Main application should call this at the very end.

    def __del__(self):
        self.cleanup()

    def set_instrument(self, program_number: int, channel: int = 0):
        """Sets the instrument for a given channel on the FluidSynthPlayer."""
        if self.fluidsynth_player and self.fluidsynth_player.fs:
            try:
                self.fluidsynth_player.program_change(channel, program_number)
                if self.log_events:
                    # Try to find instrument name from mapping for logging
                    instrument_name = "Unknown"
                    for name, prog_num in INSTRUMENT_MAPPINGS.items():
                        if prog_num == program_number:
                            instrument_name = name
                            break
                    print(f"PlaybackController: Set instrument on channel {channel} to program {program_number} ({instrument_name}).")
            except Exception as e:
                if self.log_events:
                    print(f"PlaybackController: Error setting instrument (Ch: {channel}, Pgm: {program_number}): {e}")
        elif self.log_events:
            print(f"PlaybackController: Cannot set instrument, FluidSynthPlayer not available or not initialized.")
