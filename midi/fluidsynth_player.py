import fluidsynth
from config.constants import SOUNDFONT_PATH
import os
import time

class FluidSynthPlayer:
    """
    A class to play MIDI notes using FluidSynth.
    """
    def __init__(self, soundfont_path: str = SOUNDFONT_PATH, sample_rate: int = 44100, gain: float = 0.5):
        """
        Initializes the FluidSynth player.

        Args:
            soundfont_path (str): Path to the SoundFont file.
            sample_rate (int): Audio sample rate in Hz.
            gain (float): Master gain for FluidSynth.
        """
        self.fs = None
        self.sfid = -1
        self.soundfont_path = soundfont_path

        try:
            self.fs = fluidsynth.Synth(samplerate=sample_rate, gain=gain)
        except Exception as e:
            print(f"Error initializing FluidSynth: {e}")
            return

        if not os.path.exists(self.soundfont_path):
            print(f"Error: SoundFont file not found at {self.soundfont_path}")
            # Try a relative path assuming the script is in midi/ and soundbank is a sibling of midi/
            # This is a common structure, e.g. project_root/midi/ and project_root/soundbank/
            alt_sf_path = os.path.join(os.path.dirname(__file__), "..", "soundbank", os.path.basename(self.soundfont_path))
            if os.path.exists(alt_sf_path):
                print(f"Attempting to load SoundFont from alternative path: {alt_sf_path}")
                self.soundfont_path = alt_sf_path
            else:
                print(f"Alternative SoundFont path also not found: {alt_sf_path}")
                print("Please ensure SOUNDFONT_PATH in config.constants.py is correct or provide a valid path.")
                self.fs.delete()
                self.fs = None
                return


        self.sfid = self.fs.sfload(self.soundfont_path)
        if self.sfid == -1:
            print(f"Error: Failed to load SoundFont: {self.soundfont_path}")
            self.fs.delete()
            self.fs = None
            return

        # Initialize default program (0) for all 16 channels
        for i in range(16):
            self.fs.program_select(i, self.sfid, 0, 0)

        print(f"FluidSynth initialized with SoundFont: {self.soundfont_path}")

    def noteon(self, channel: int, key: int, velocity: int):
        """
        Plays a note on a given channel.

        Args:
            channel (int): MIDI channel (0-15).
            key (int): MIDI note number (0-127).
            velocity (int): Note velocity (0-127).
        """
        if not self.fs:
            print("Error: FluidSynth not initialized.")
            return
        try:
            self.fs.noteon(channel, key, velocity)
        except Exception as e:
            print(f"Error playing noteon: {e}")

    def noteoff(self, channel: int, key: int):
        """
        Stops a note on a given channel.

        Args:
            channel (int): MIDI channel (0-15).
            key (int): MIDI note number (0-127).
        """
        if not self.fs:
            print("Error: FluidSynth not initialized.")
            return
        try:
            self.fs.noteoff(channel, key)
        except Exception as e:
            print(f"Error playing noteoff: {e}")

    def program_change(self, channel: int, program: int):
        """
        Changes the instrument program on a given channel.

        Args:
            channel (int): MIDI channel (0-15).
            program (int): Program number (MIDI instrument).
        """
        if not self.fs or self.sfid == -1:
            print("Error: FluidSynth not initialized or SoundFont not loaded.")
            return
        try:
            self.fs.program_select(channel, self.sfid, 0, program)
        except Exception as e:
            print(f"Error changing program: {e}")

    def set_gain(self, gain: float):
        """
        Sets the master gain for FluidSynth.

        Args:
            gain (float): New gain value.
        """
        if not self.fs:
            print("Error: FluidSynth not initialized.")
            return
        try:
            self.fs.set_gain(gain)
        except Exception as e:
            print(f"Error setting gain: {e}")

    def cleanup(self):
        """
        Cleans up FluidSynth resources.
        """
        if self.fs:
            try:
                self.fs.delete()
                self.fs = None
                print("FluidSynth resources cleaned up.")
            except Exception as e:
                print(f"Error during FluidSynth cleanup: {e}")

    def __del__(self):
        """
        Destructor to ensure cleanup is called.
        """
        self.cleanup()

if __name__ == '__main__':
    # This test block assumes it can find the soundfont.
    # SOUNDFONT_PATH from config.constants is 'soundbank/soundfont.sf2'
    # If running this script directly from the 'midi' directory, the path needs adjustment.

    # Determine the base directory of the project (assuming 'midi' is a subdirectory)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
    # Construct the path to the soundfont file from the project root
    # The constant SOUNDFONT_PATH = "soundbank/soundfont.sf2" implies it's relative to project root
    sf_path_from_constants = os.path.join(project_root, SOUNDFONT_PATH)

    print(f"Attempting to load soundfont from: {sf_path_from_constants}")

    if not os.path.exists(sf_path_from_constants):
        print(f"Warning: Soundfont file not found at determined path: {sf_path_from_constants}")
        print(f"SOUNDFONT_PATH in constants is: {SOUNDFONT_PATH}")
        print("Please ensure you have a soundfont file at 'project_root/soundbank/soundfont.sf2'")
        print("Alternatively, place 'soundfont.sf2' in the 'soundbank' directory relative to the project root.")
        # Fallback for testing: check if a soundfont is in the current script's directory or a 'soundbank' subdir relative to current script
        # This is less robust.
        test_sf_paths = [
            "soundfont.sf2", 
            os.path.join("..", "soundbank", "soundfont.sf2"), # if run from midi/
            SOUNDFONT_PATH # if run from project root
        ]
        found_test_sf = None
        for p in test_sf_paths:
            abs_p = os.path.abspath(p)
            print(f"Checking alternative: {abs_p}")
            if os.path.exists(abs_p):
                sf_path_from_constants = abs_p
                print(f"Found soundfont at alternative path: {sf_path_from_constants}")
                break
        if not os.path.exists(sf_path_from_constants):
             print(f"FluidSynthPlayer test skipped: Soundfont not found at any tested path.")
             sf_path_from_constants = None # Ensure it's None if not found
    
    if sf_path_from_constants and os.path.exists(sf_path_from_constants):
        player = FluidSynthPlayer(sf_path_from_constants)
        
        if player.fs: # Check if FluidSynth was successfully initialized
            print(f"FluidSynthPlayer initialized with {sf_path_from_constants}.")

            # Test program change (e.g., to Warm Pad on channel 0)
            # Instrument numbers from General MIDI standard. 89 is Pad 2 (warm)
            player.program_change(0, 89) 
            print("Changed to Warm Pad (89) on channel 0.")

            # Test note on/off
            print("Playing C4 (MIDI note 60) on channel 0...")
            player.noteon(0, 60, 100) # Channel 0, Middle C, Velocity 100
            time.sleep(1)
            player.noteoff(0, 60)
            print("Stopped C4.")

            # Test another instrument (e.g., Synth Lead on channel 1)
            # 80 is Lead 1 (square)
            player.program_change(1, 80)
            print("Changed to Synth Lead (80) on channel 1.")
            print("Playing E4 (MIDI note 64) on channel 1...")
            player.noteon(1, 64, 100)
            time.sleep(1)
            player.noteoff(1, 64)
            print("Stopped E4.")
            
            # player.cleanup() # __del__ will call this, but explicit call is fine
            print("FluidSynthPlayer test complete.")
        else:
            print(f"FluidSynthPlayer test skipped: FluidSynth could not be initialized even if soundfont path was provided.")
    else:
        print(f"FluidSynthPlayer test skipped: Soundfont not found.")

print("If tests ran, ensure you heard sound or check FluidSynth/system audio configuration if not.")
print("System dependencies for pyfluidsynth: `fluidsynth` library (e.g., `sudo apt-get install fluidsynth`).")
print("A SoundFont file (e.g., .sf2) is also required.")

# Make sure there is a soundbank folder in the root of the project 
# and a soundfont.sf2 file in it for the test to run correctly.
# For example: project_root/soundbank/soundfont.sf2
# The script will try to find it.
# If you don't have a soundfont, you can find many free ones online.
# A common one is "FluidR3_GM.sf2". Place it as soundbank/soundfont.sf2.

# To run this test directly:
# 1. Ensure you are in the project root directory.
# 2. Run `python midi/fluidsynth_player.py`
# 3. Make sure you have a soundfont at `soundbank/soundfont.sf2`
# If you have issues, check the paths printed by the script.
# You might need to install `libportaudio2` for audio output: `sudo apt-get install libportaudio2`
# (This was done in the previous step's bash command)

# The SOUNDFONT_PATH in config.constants is "soundbank/soundfont.sf2"
# The class's __init__ will try to use this.
# The __main__ block tries to be a bit more robust in finding it for direct script execution.
# It also tries an alternative path: ../soundbank/soundfont.sf2 (relative to this file)
# which is effectively project_root/soundbank/soundfont.sf2
# This should work if the script is run from the 'midi' directory or the project root.
# However, the most reliable way is to ensure SOUNDFONT_PATH in constants.py points to the correct location
# relative to the project root, and run scripts from the project root.

# The __init__ method has been updated to try a path relative to the script file
# if the direct SOUNDFONT_PATH doesn't exist. This helps if the script is not run
# from the project root but SOUNDFONT_PATH is relative to the project root.
# For example, if CWD is /app/midi and SOUNDFONT_PATH is "soundbank/soundfont.sf2",
# it won't be found. The alternative path calculation `os.path.join(os.path.dirname(__file__), "..", "soundbank", os.path.basename(self.soundfont_path))`
# would construct `/app/midi/../soundbank/soundfont.sf2` which resolves to `/app/soundbank/soundfont.sf2`.
# This is generally what's needed.
