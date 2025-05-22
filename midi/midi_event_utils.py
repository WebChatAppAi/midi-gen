import pygame.midi
import pretty_midi # For note_number_to_name in logging, if desired
import pygame # Added for pygame.midi.Output type check
from .fluidsynth_player import FluidSynthPlayer # Added for FluidSynthPlayer type check

def send_note_on(device_or_player, pitch: int, velocity: int, channel: int = 0, log: bool = False):
    """Sends a MIDI note ON message, works with Pygame MIDI output or FluidSynthPlayer."""
    if not device_or_player:
        if log: print(f"send_note_on: No device or player provided for P: {pitch}")
        return
    
    try:
        actual_velocity = int(velocity)
        actual_pitch = int(pitch)
        actual_channel = int(channel)

        if isinstance(device_or_player, FluidSynthPlayer):
            if device_or_player.fs:
                device_or_player.noteon(actual_channel, actual_pitch, actual_velocity)
                if log:
                    print(f"FS Note ON: {pretty_midi.note_number_to_name(actual_pitch)} (P: {actual_pitch}, V: {actual_velocity}, Ch: {actual_channel})")
            elif log:
                print(f"FS Note ON Skipped: FluidSynthPlayer not fully initialized (fs is None) for P: {actual_pitch}")
        
        elif isinstance(device_or_player, pygame.midi.Output):
            device_or_player.note_on(actual_pitch, actual_velocity, actual_channel)
            if log:
                print(f"Pygame Note ON: {pretty_midi.note_number_to_name(actual_pitch)} (P: {actual_pitch}, V: {actual_velocity}, Ch: {actual_channel})")
        
        else:
            if log: print(f"send_note_on: Unknown device/player type: {type(device_or_player)} for P: {actual_pitch}")

    except Exception as e:
        print(f"Error sending note on (P: {pitch}, Ch: {channel}): {e}")


def send_note_off(device_or_player, pitch: int, velocity: int = 0, channel: int = 0, log: bool = False):
    """Sends a MIDI note OFF message, works with Pygame MIDI output or FluidSynthPlayer."""
    # Velocity for note off is often 0, but some systems might use it for release velocity.
    if not device_or_player:
        if log: print(f"send_note_off: No device or player provided for P: {pitch}")
        return

    try:
        actual_pitch = int(pitch)
        actual_channel = int(channel)
        # actual_velocity = int(velocity) # Velocity for note-off is often ignored or fixed.

        if isinstance(device_or_player, FluidSynthPlayer):
            if device_or_player.fs:
                device_or_player.noteoff(actual_channel, actual_pitch) # FluidSynth noteoff doesn't take velocity
                if log:
                    print(f"FS Note OFF: {pretty_midi.note_number_to_name(actual_pitch)} (P: {actual_pitch}, Ch: {actual_channel})")
            elif log:
                print(f"FS Note OFF Skipped: FluidSynthPlayer not fully initialized (fs is None) for P: {actual_pitch}")

        elif isinstance(device_or_player, pygame.midi.Output):
            device_or_player.note_off(actual_pitch, 0, actual_channel) # Pygame note_off takes velocity, typically 0
            if log:
                print(f"Pygame Note OFF: {pretty_midi.note_number_to_name(actual_pitch)} (P: {actual_pitch}, Ch: {actual_channel})")
        
        else:
            if log: print(f"send_note_off: Unknown device/player type: {type(device_or_player)} for P: {actual_pitch}")
            
    except Exception as e:
        print(f"Error sending note off (P: {pitch}, Ch: {channel}): {e}")


def send_all_notes_off(device_or_player, log_events=False): # Renamed log to log_events for clarity
    """Sends All Notes Off messages on all channels."""
    if not device_or_player:
        if log_events: print("send_all_notes_off: No device or player provided.")
        return

    if log_events: print(f"Sending All Notes Off via {type(device_or_player)}...")
    
    try:
        if isinstance(device_or_player, FluidSynthPlayer):
            if device_or_player.fs:
                for channel in range(16):  # FluidSynth typically has 16 channels
                    # Send MIDI CC 123 (All Notes Off) to each channel
                    device_or_player.fs.cc(channel, 123, 0)
                if log_events: print("All Notes Off messages sent to FluidSynthPlayer.")
            else:
                if log_events: print("send_all_notes_off: FluidSynthPlayer not fully initialized (fs is None).")
        
        elif isinstance(device_or_player, pygame.midi.Output):
            for channel in range(16):  # Pygame MIDI typically handles 16 channels
                device_or_player.write_short(0xB0 + channel, 123, 0)  # All notes off Controller CC 123
            if log_events: print("All Notes Off messages sent to pygame.midi.Output device.")
            # Optional: The old loop for individual note_offs can be kept if CC 123 isn't sufficient for a specific device.
            # for pitch in range(128):
            #    device_or_player.note_off(pitch, 0, 0) # Usually channel 0 was assumed here.

        else:
            if log_events: print(f"send_all_notes_off: Unknown device/player type: {type(device_or_player)}")
            
    except Exception as e:
        print(f"Error sending All Notes Off messages: {e}")

def send_panic(output_device, log_events=False): # Renamed log to log_events for clarity
    """More aggressive version of all notes off, includes all sound off."""
    if not output_device: # output_device is still the param name here, consider changing if this function is also updated.
        if log_events: print("Panic: No output device.")
        return
    
    if log_events: print("Sending MIDI Panic (All Sound Off & All Notes Off)...")
    try:
        # This function would also need to be updated if it's intended to work with FluidSynthPlayer
        # For now, assuming it's still for pygame.midi.Output or needs separate handling.
        if isinstance(output_device, pygame.midi.Output):
            for channel in range(16):
                # Controller 120 (0x78) = All Sound Off
                output_device.write_short(0xB0 + channel, 120, 0) 
                # Controller 123 (0x7B) = All Notes Off
                output_device.write_short(0xB0 + channel, 123, 0)
            if log_events: print("MIDI Panic messages sent to pygame.midi.Output.")
        elif isinstance(output_device, FluidSynthPlayer):
            if output_device.fs:
                for channel in range(16):
                    output_device.fs.cc(channel, 120, 0) # All Sound Off
                    output_device.fs.cc(channel, 123, 0) # All Notes Off
                # FluidSynth also has system_reset() which might be more thorough if needed:
                # output_device.fs.system_reset() 
                if log_events: print("MIDI Panic messages sent to FluidSynthPlayer.")
            else:
                if log_events: print("send_panic: FluidSynthPlayer not fully initialized (fs is None).")

        else:
            if log_events: print(f"send_panic: Unknown device type: {type(output_device)}")
        
    except Exception as e:
        print(f"Error sending MIDI Panic messages: {e}")
