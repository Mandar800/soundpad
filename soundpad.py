
import tkinter as tk
from tkinter import filedialog, messagebox
import sounddevice as sd
import numpy as np
from pydub import AudioSegment
import threading
import os
import sys
import keyboard  # For global hotkey listening

SAMPLE_RATE = 44100

# ===== LOGGING =====
def log(msg):
    """Log to console with timestamp - set VERBOSE=True to disable"""
    VERBOSE = True  # Set to True for debugging
    if VERBOSE:
        print(f"[LOG] {msg}", flush=True)
        sys.stdout.flush()

# ===== AUDIO ENGINE =====
def play_sound(sound):
    log(f"[PLAY] Playing sound with shape: {sound.shape}")
    try:
        # Use sounddevice's simple play function instead of callbacks
        sd.play(sound, samplerate=SAMPLE_RATE)
        log(f"[PLAY] Sound queued successfully")
    except Exception as e:
        log(f"[PLAY] ERROR: {e}")
        messagebox.showerror("Error", f"Failed to play sound:\n{e}")
        import traceback
        traceback.print_exc()

def start_audio():
    log("[AUDIO] Audio system initialized (using sd.play)")
    # No persistent stream needed - sd.play() handles it automatically

def load_sound(file):
    log(f"[LOAD] Loading sound: {file}")
    try:
        log(f"[LOAD] Attempting AudioSegment.from_file()...")
        audio = AudioSegment.from_file(file)
        log(f"[LOAD] Loaded - channels: {audio.channels}, frame_rate: {audio.frame_rate}, sample_width: {audio.sample_width}")
        
        # Convert stereo to mono if needed
        if audio.channels > 1:
            log(f"[LOAD] Converting {audio.channels} channels to mono")
            audio = audio.set_channels(1)
        
        # Resample to match our SAMPLE_RATE if needed
        if audio.frame_rate != SAMPLE_RATE:
            log(f"[LOAD] Resampling from {audio.frame_rate} to {SAMPLE_RATE}")
            audio = audio.set_frame_rate(SAMPLE_RATE)
        
        # Convert to numpy array
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
        log(f"[LOAD] Samples array shape: {samples.shape}")
        
        # Normalize based on bit depth
        # AudioSegment uses 16-bit by default (range: -32768 to 32767)
        max_val = 32768.0 if audio.sample_width == 2 else (2 ** (audio.sample_width * 8 - 1))
        samples /= max_val
        log(f"[LOAD] Normalized with max_val: {max_val}")
        
        return samples
    except FileNotFoundError as fe:
        log(f"[LOAD] ERROR - File not found: {file}")
        messagebox.showerror("Error", f"Audio file not found:\n{file}")
        raise
    except Exception as e:
        log(f"[LOAD] ERROR: {type(e).__name__}: {e}")
        log(f"[LOAD] Make sure FFmpeg is installed!")
        messagebox.showerror("Error", f"Failed to load audio file:\n{e}\n\nMake sure FFmpeg is installed on your system.")
        import traceback
        traceback.print_exc()
        raise

# ===== UI =====
class SoundpadApp:
    def __init__(self, root):
        log("[UI_INIT] Initializing SoundpadApp...")
        self.root = root
        self.root.title("Python Soundpad")
        self.root.geometry("600x400")

        self.sounds = []
        self.hotkey_listeners = {}  # Map: hotkey_name -> sound_data
        self.listening = True  # Flag to control listener thread
        
        # Start hotkey listener thread
        self.listener_thread = threading.Thread(target=self._listen_for_hotkeys, daemon=True)
        self.listener_thread.start()
        log("[UI_INIT] Hotkey listener thread started")

        # Top frame for buttons
        top_frame = tk.Frame(root)
        top_frame.pack(padx=10, pady=10, fill="x")

        self.add_btn = tk.Button(top_frame, text="Add Sound", command=self.add_sound)
        self.add_btn.pack(side="left", padx=5)

        # List frame with scrollbar
        list_frame = tk.Frame(root)
        list_frame.pack(padx=10, pady=5, fill="both", expand=True)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.list_box = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=10)
        self.list_box.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.list_box.yview)

        # Control frame for adding hotkeys
        control_frame = tk.Frame(root)
        control_frame.pack(padx=10, pady=5, fill="x")

        tk.Label(control_frame, text="Hotkey:").pack(side="left")
        self.hotkey_entry = tk.Entry(control_frame, width=15)
        self.hotkey_entry.pack(side="left", padx=5)

        self.set_hotkey_btn = tk.Button(control_frame, text="Set Hotkey", command=self.set_selected_hotkey)
        self.set_hotkey_btn.pack(side="left", padx=5)

        self.play_selected_btn = tk.Button(control_frame, text="Play Selected", command=self.play_selected)
        self.play_selected_btn.pack(side="left", padx=5)

        self.remove_btn = tk.Button(control_frame, text="Remove", command=self.remove_selected)
        self.remove_btn.pack(side="left", padx=5)
        
        log("[UI_INIT] SoundpadApp initialized successfully")

    def update_list(self):
        """Refresh the listbox to show all sounds with their hotkeys"""
        self.list_box.delete(0, tk.END)
        for sound in self.sounds:
            hotkey_text = f" [{sound['hotkey']}]" if sound["hotkey"] else " [No hotkey]"
            self.list_box.insert(tk.END, sound["name"] + hotkey_text)

    def add_sound(self):
        log("[ADD_SOUND] Opening file dialog...")
        file = filedialog.askopenfilename()
        if not file:
            log("[ADD_SOUND] File dialog cancelled")
            return

        try:
            log(f"[ADD_SOUND] Loading file: {file}")
            sound_data = load_sound(file)
            log(f"[ADD_SOUND] Sound loaded successfully, size: {sound_data.nbytes} bytes")

            sound = {
                "name": os.path.basename(file),
                "data": sound_data,
                "hotkey": None
            }

            self.sounds.append(sound)
            log(f"[ADD_SOUND] Sound added: {sound['name']}")
            
            self.update_list()
            log("[ADD_SOUND] List updated successfully")
        except Exception as e:
            log(f"[ADD_SOUND] ERROR after loading: {type(e).__name__}: {e}")
            messagebox.showerror("Error", f"Failed to add sound:\n{e}")
            import traceback
            traceback.print_exc()

    def get_selected_sound(self):
        """Get the currently selected sound from the listbox"""
        selection = self.list_box.curselection()
        if selection:
            return self.sounds[selection[0]]
        return None

    def set_selected_hotkey(self):
        """Set hotkey name for the selected sound"""
        sound = self.get_selected_sound()
        if not sound:
            messagebox.showwarning("Warning", "Please select a sound first")
            return

        key_str = self.hotkey_entry.get().strip()
        if not key_str:
            messagebox.showwarning("Warning", "Please enter a hotkey")
            return
        
        log(f"[HOTKEY] Setting hotkey name: '{key_str}'")
        sound["hotkey"] = key_str
        
        # Register this hotkey for listening
        self.hotkey_listeners[key_str] = sound["data"]
        log(f"[HOTKEY] Registered listener for key: '{key_str}'")
        
        self.hotkey_entry.delete(0, tk.END)
        self.update_list()
        messagebox.showinfo("Success", f"Hotkey '{key_str}' set for {sound['name']}")

    def _listen_for_hotkeys(self):
        """Background thread that listens for registered hotkeys"""
        log("[HOTKEY_LISTENER] Started listening for hotkeys...")
        while self.listening:
            try:
                for hotkey_name, sound_data in self.hotkey_listeners.items():
                    if keyboard.is_pressed(hotkey_name):
                        log(f"[HOTKEY_LISTENER] Hotkey pressed: {hotkey_name}")
                        play_sound(sound_data)
                        # Wait a bit to avoid rapid re-triggering
                        threading.Event().wait(0.2)
            except Exception as e:
                log(f"[HOTKEY_LISTENER] ERROR: {e}")
            
            threading.Event().wait(0.05)  # Small sleep to prevent high CPU usage

    def play_selected(self):
        """Play the selected sound"""
        sound = self.get_selected_sound()
        if sound:
            play_sound(sound["data"])

    def remove_selected(self):
        """Remove the selected sound"""
        selection = self.list_box.curselection()
        if selection:
            del self.sounds[selection[0]]
            self.update_list()

# ===== MAIN =====
log("=" * 50)
log("SOUNDPAD APPLICATION STARTING")
log("=" * 50)

root = tk.Tk()
app = SoundpadApp(root)

log("[MAIN] Starting audio system...")
start_audio()

log("[MAIN] Entering main loop...")
root.mainloop()
log("[MAIN] Application closed")