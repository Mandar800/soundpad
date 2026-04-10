
import tkinter as tk
from tkinter import filedialog, messagebox
import sounddevice as sd
import numpy as np
from pydub import AudioSegment
import threading
import os
import sys
import keyboard  # For global hotkey listening
import json

SAMPLE_RATE = 44100
PROJECT_FILE = "soundpad_project.json"  # Stores sounds and hotkeys

# ===== LOGGING =====
def log(msg):
    """Log to console with timestamp - set VERBOSE=True to disable"""
    VERBOSE = True  # Set to True for debugging
    if VERBOSE:
        print(f"[LOG] {msg}", flush=True)
        sys.stdout.flush()

# ===== AUDIO ENGINE =====
play_buffer = []
play_buffer_lock = threading.Lock()

def get_audio_devices():
    """Get list of available audio output devices"""
    devices = sd.query_devices()
    output_devices = []
    for i, device in enumerate(devices):
        if device['max_output_channels'] > 0:  # Output device
            output_devices.append((i, device['name']))
    return output_devices

def normalize_hotkey(key_str):
    """Convert user input to keyboard library format"""
    key_str = key_str.lower().strip()
    
    # Map common aliases to keyboard library names
    aliases = {
        'fn1': 'f1', 'function1': 'f1', 'func1': 'f1',
        'fn2': 'f2', 'function2': 'f2', 'func2': 'f2',
        'fn3': 'f3', 'function3': 'f3', 'func3': 'f3',
        'fn4': 'f4', 'function4': 'f4', 'func4': 'f4',
        'fn5': 'f5', 'function5': 'f5', 'func5': 'f5',
        'fn6': 'f6', 'function6': 'f6', 'func6': 'f6',
        'fn7': 'f7', 'function7': 'f7', 'func7': 'f7',
        'fn8': 'f8', 'function8': 'f8', 'func8': 'f8',
        'fn9': 'f9', 'function9': 'f9', 'func9': 'f9',
        'fn10': 'f10', 'function10': 'f10', 'func10': 'f10',
        'fn11': 'f11', 'function11': 'f11', 'func11': 'f11',
        'fn12': 'f12', 'function12': 'f12', 'func12': 'f12',
        'space': 'space',
        'enter': 'enter', 'return': 'enter',
        'tab': 'tab',
        'escape': 'escape', 'esc': 'escape',
        'backspace': 'backspace', 'back': 'backspace',
        'delete': 'delete', 'del': 'delete',
        'insert': 'insert', 'ins': 'insert',
        'home': 'home',
        'end': 'end',
        'pageup': 'page up', 'pgup': 'page up',
        'pagedown': 'page down', 'pgdn': 'page down',
        'left': 'left', 'leftarrow': 'left',
        'right': 'right', 'rightarrow': 'right',
        'up': 'up', 'uparrow': 'up',
        'down': 'down', 'downarrow': 'down',
    }
    
    return aliases.get(key_str, key_str)

def play_sound(sound):
    """Queue a sound to be played and mixed with mic"""
    global play_buffer
    log(f"[PLAY] Queueing sound with shape: {sound.shape}")
    try:
        with play_buffer_lock:
            play_buffer.append(sound.copy())
            log(f"[PLAY] Sound queued, buffer length: {len(play_buffer)}")
    except Exception as e:
        log(f"[PLAY] ERROR: {e}")
        import traceback
        traceback.print_exc()

def mix_audio_callback(indata, outdata, frames, time, status):
    """Real-time audio callback: mix mic input with soundpad sounds"""
    try:
        if status:
            log(f"[AUDIO_CB] Status: {status}")
        
        # Start with microphone input
        output = indata[:, 0].copy() if indata is not None else np.zeros(frames, dtype=np.float32)
        
        # Mix in queued sounds
        with play_buffer_lock:
            new_buffer = []
            for sound in play_buffer:
                length = min(len(output), len(sound))
                output[:length] += sound[:length]
                
                if len(sound) > length:
                    new_buffer.append(sound[length:])
            play_buffer[:] = new_buffer
        
        # Clip to prevent distortion
        output = np.clip(output, -1, 1)
        outdata[:, 0] = output
    except Exception as e:
        log(f"[AUDIO_CB] ERROR: {e}")
        outdata.fill(0)

stream = None

def start_audio(output_device_id=None):
    """Start audio stream that captures mic input and mixes with soundpad sounds"""
    global stream
    log(f"[AUDIO] Starting audio stream (device: {output_device_id})...")
    try:
        if stream:
            stream.stop()
            stream.close()
        
        # If no device specified, use default
        if output_device_id is None:
            output_device_id = sd.default.device[1]  # Get default output
        
        # Check what input device we're using
        default_input = sd.default.device[0]
        log(f"[AUDIO] Using output device ID: {output_device_id}")
        log(f"[AUDIO] Using input device ID: {default_input} (default)")
        
        # Create duplex stream: captures mic input, outputs mixed audio
        stream = sd.Stream(
            samplerate=SAMPLE_RATE,
            channels=1,
            callback=mix_audio_callback,
            dtype='float32',
            device=(None, output_device_id)  # Default input, selected output
        )
        stream.start()
        log(f"[AUDIO] Duplex stream started successfully (mic + sounds)")
    except Exception as e:
        log(f"[AUDIO] ERROR: {e}")
        import traceback
        traceback.print_exc()

# ===== PERSISTENCE =====
def save_project(sounds):
    """Save sounds and hotkeys to JSON file"""
    try:
        project_data = []
        for sound in sounds:
            project_data.append({
                "name": sound["name"],
                "file_path": sound.get("file_path", ""),
                "hotkey": sound.get("hotkey", None)
            })
        
        with open(PROJECT_FILE, "w") as f:
            json.dump(project_data, f, indent=2)
        log(f"[SAVE] Project saved to {PROJECT_FILE} with {len(project_data)} sounds")
    except Exception as e:
        log(f"[SAVE] ERROR: {e}")

def load_project():
    """Load saved sounds and hotkeys from JSON file"""
    try:
        if not os.path.exists(PROJECT_FILE):
            log(f"[LOAD_PROJECT] No saved project found ({PROJECT_FILE})")
            return []
        
        with open(PROJECT_FILE, "r") as f:
            project_data = json.load(f)
        
        log(f"[LOAD_PROJECT] Loaded {len(project_data)} sounds from {PROJECT_FILE}")
        
        # Reload sound data from file paths
        sounds = []
        for item in project_data:
            file_path = item.get("file_path", "")
            if file_path and os.path.exists(file_path):
                try:
                    sound_data = load_sound(file_path)
                    sounds.append({
                        "name": item["name"],
                        "data": sound_data,
                        "hotkey": item.get("hotkey", None),
                        "file_path": file_path
                    })
                    log(f"[LOAD_PROJECT] Loaded sound: {item['name']}")
                except Exception as e:
                    log(f"[LOAD_PROJECT] ERROR loading {file_path}: {e}")
            else:
                log(f"[LOAD_PROJECT] File not found: {file_path}")
        
        return sounds
    except Exception as e:
        log(f"[LOAD_PROJECT] ERROR: {e}")
        return []

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
        self.selected_device_id = None
        
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

        tk.Label(control_frame, text="Name:").pack(side="left")
        self.name_entry = tk.Entry(control_frame, width=15)
        self.name_entry.pack(side="left", padx=5)

        self.rename_btn = tk.Button(control_frame, text="Rename", command=self.rename_sound)
        self.rename_btn.pack(side="left", padx=2)

        tk.Label(control_frame, text="Hotkey:").pack(side="left", padx=(10, 0))
        self.hotkey_entry = tk.Entry(control_frame, width=10)
        self.hotkey_entry.pack(side="left", padx=5)

        self.record_hotkey_btn = tk.Button(control_frame, text="Record", command=self.record_hotkey)
        self.record_hotkey_btn.pack(side="left", padx=2)

        self.set_hotkey_btn = tk.Button(control_frame, text="Set", command=self.set_selected_hotkey)
        self.set_hotkey_btn.pack(side="left", padx=2)

        self.play_selected_btn = tk.Button(control_frame, text="Play Selected", command=self.play_selected)
        self.play_selected_btn.pack(side="left", padx=5)

        self.remove_btn = tk.Button(control_frame, text="Remove", command=self.remove_selected)
        self.remove_btn.pack(side="left", padx=5)
        
        # Device selector frame
        device_frame = tk.Frame(root)
        device_frame.pack(padx=10, pady=5, fill="x")
        
        tk.Label(device_frame, text="Output Device:").pack(side="left")
        self.device_var = tk.StringVar(value="Loading...")
        
        # Add trace to detect device changes
        self.device_var.trace('w', lambda name, index, mode: self._on_device_var_changed())
        
        self.device_combo = tk.OptionMenu(device_frame, self.device_var, "Loading...")
        self.device_combo.pack(side="left", padx=5, fill="x", expand=True)
        
        # Populate device list
        self.update_device_list()
        
        # Now load saved project and populate UI
        self.sounds = load_project()
        log(f"[UI_INIT] Loaded {len(self.sounds)} sounds from project")
        
        # Register hotkeys from loaded sounds
        for sound in self.sounds:
            if sound.get("hotkey"):
                self.hotkey_listeners[sound["hotkey"]] = sound["data"]
                log(f"[UI_INIT] Registered hotkey: {sound['hotkey']}")
        
        self.update_list()
        log("[UI_INIT] SoundpadApp initialized successfully")

    def update_list(self):
        """Refresh the listbox to show all sounds with their hotkeys"""
        self.list_box.delete(0, tk.END)
        for sound in self.sounds:
            hotkey_text = f" [{sound['hotkey']}]" if sound["hotkey"] else " [No hotkey]"
            self.list_box.insert(tk.END, sound["name"] + hotkey_text)
        
        # Bind selection event to populate name field
        self.list_box.bind('<<ListboxSelect>>', self.on_sound_selected)

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
                "hotkey": None,
                "file_path": file  # Store the file path for persistence
            }

            self.sounds.append(sound)
            log(f"[ADD_SOUND] Sound added: {sound['name']}")
            
            self.update_list()
            save_project(self.sounds)  # Save after adding
            log("[ADD_SOUND] List updated and project saved")
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

    def on_sound_selected(self, event):
        """When user clicks a sound in the list, populate the name field"""
        sound = self.get_selected_sound()
        if sound:
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, sound["name"])
            log(f"[UI] Sound selected: {sound['name']}")

    def rename_sound(self):
        """Rename the selected sound"""
        sound = self.get_selected_sound()
        if not sound:
            messagebox.showwarning("Warning", "Please select a sound first")
            return

        new_name = self.name_entry.get().strip()
        if not new_name:
            messagebox.showwarning("Warning", "Name cannot be empty")
            return

        old_name = sound["name"]
        sound["name"] = new_name
        log(f"[RENAME] Changed '{old_name}' to '{new_name}'")
        
        self.update_list()
        save_project(self.sounds)
        messagebox.showinfo("Success", f"Sound renamed to: {new_name}")

    def update_device_list(self):
        """Populate dropdown with available audio output devices"""
        try:
            devices = get_audio_devices()
            log(f"[DEVICE] Found {len(devices)} output devices")
            
            # Clear existing menu
            menu = self.device_combo["menu"]
            menu.delete(0, "end")
            
            # Add devices
            self.device_map = {}  # Map display name to device ID
            for device_id, device_name in devices:
                self.device_map[device_name] = device_id
                menu.add_command(label=device_name, command=lambda d=device_name: self.device_var.set(d))
                log(f"[DEVICE] Added: {device_name} (ID: {device_id})")
            
            # Set default to first device
            if devices:
                default_device_name = devices[0][1]
                self.device_var.set(default_device_name)
                self.selected_device_id = devices[0][0]
                log(f"[DEVICE] Default device set to: {default_device_name}")
        except Exception as e:
            log(f"[DEVICE] ERROR: {e}")

    def on_device_changed(self, device_name):
        """Called when user selects a different device"""
        self.selected_device_id = self.device_map.get(device_name)
        log(f"[DEVICE] Changed to: {device_name} (ID: {self.selected_device_id})")
        # Restart audio stream with new device
        start_audio(self.selected_device_id)
    
    def _on_device_var_changed(self):
        """Internal handler for StringVar trace - runs whenever device_var changes"""
        device_name = self.device_var.get()
        if device_name and device_name != "Loading...":
            self.on_device_changed(device_name)

    def record_hotkey(self):
        """Record a hotkey by listening for the next key press"""
        self.hotkey_entry.delete(0, tk.END)
        self.hotkey_entry.insert(0, "Press any key...")
        self.hotkey_entry.config(state='disabled', fg='gray')
        self.record_hotkey_btn.config(state='disabled')
        
        log("[RECORD] Waiting for key press...")
        
        def on_key_press(event):
            """Capture the key that was pressed"""
            key_name = None
            
            # Map Tkinter key names to keyboard library names
            key_map = {
                'F1': 'f1', 'F2': 'f2', 'F3': 'f3', 'F4': 'f4', 'F5': 'f5', 'F6': 'f6',
                'F7': 'f7', 'F8': 'f8', 'F9': 'f9', 'F10': 'f10', 'F11': 'f11', 'F12': 'f12',
                'space': 'space', 'Return': 'enter', 'Tab': 'tab', 'Escape': 'escape',
                'BackSpace': 'backspace', 'Delete': 'delete', 'Insert': 'insert',
                'Home': 'home', 'End': 'end', 'Page_Up': 'page up', 'Page_Down': 'page down',
                'Left': 'left', 'Right': 'right', 'Up': 'up', 'Down': 'down',
            }
            
            # Get the key name
            if event.keysym in key_map:
                key_name = key_map[event.keysym]
            elif len(event.char) == 1 and event.char.isprintable():
                key_name = event.char.lower()
            else:
                key_name = event.keysym.lower()
            
            log(f"[RECORD] Key captured: {key_name}")
            self.hotkey_entry.config(state='normal', fg='black')
            self.hotkey_entry.delete(0, tk.END)
            self.hotkey_entry.insert(0, key_name)
            self.record_hotkey_btn.config(state='normal')
            
            # Unbind after capturing
            self.root.unbind('<Key>')
            messagebox.showinfo("Success", f"Hotkey recorded: {key_name}\n\nClick 'Set Hotkey' to confirm.")
        
        self.root.bind('<Key>', on_key_press)

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
        
        # Normalize the key name
        normalized_key = normalize_hotkey(key_str)
        log(f"[HOTKEY] Input: '{key_str}' -> Normalized: '{normalized_key}'")
        
        # Try to verify the key is valid by testing it
        try:
            result = keyboard.is_pressed(normalized_key)
            log(f"[HOTKEY] Key validation successful: '{normalized_key}'")
        except Exception as e:
            log(f"[HOTKEY] ERROR - Invalid key: '{normalized_key}': {e}")
            messagebox.showerror("Error", f"Invalid hotkey: '{key_str}'\n\nUse: f1-f12, space, enter, letters, numbers, etc.")
            return
        
        sound["hotkey"] = normalized_key
        
        # Register this hotkey for listening
        self.hotkey_listeners[normalized_key] = sound["data"]
        log(f"[HOTKEY] Registered listener for key: '{normalized_key}'")
        
        self.hotkey_entry.delete(0, tk.END)
        self.update_list()
        save_project(self.sounds)  # Save after setting hotkey
        messagebox.showinfo("Success", f"Hotkey '{key_str}' (as '{normalized_key}') set for {sound['name']}")

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
            removed_sound = self.sounds[selection[0]]
            del self.sounds[selection[0]]
            
            # Remove from hotkey listeners if it has a hotkey
            if removed_sound.get("hotkey"):
                self.hotkey_listeners.pop(removed_sound["hotkey"], None)
                log(f"[REMOVE] Removed hotkey: {removed_sound['hotkey']}")
            
            self.update_list()
            save_project(self.sounds)  # Save after removing
            log(f"[REMOVE] Removed sound: {removed_sound['name']}")

# ===== MAIN =====
log("=" * 50)
log("SOUNDPAD APPLICATION STARTING")
log("=" * 50)

root = tk.Tk()
app = SoundpadApp(root)

log("[MAIN] Starting audio system...")
start_audio(app.selected_device_id)

log("[MAIN] Entering main loop...")
root.mainloop()
log("[MAIN] Application closed")