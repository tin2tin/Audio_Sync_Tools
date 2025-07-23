bl_info = {
    "name": "Sync Audio to Active Strip",
    "author": "tintwotin",
    "version": (2, 1, 0),
    "blender": (2, 83, 0),
    "location": "Sequencer > Strip > Transform > Sync Audio to Active Strip",
    "description": "Precisely syncs selected sound strips to the active sound strip using a 2-step peak detection and cross-correlation method. Ideal for syncing camera audio to external recorders using a clapperboard.",
    "warning": "Requires internet connection for first-time installation of required libraries (numpy, scipy, librosa).",
    "doc_url": "",
    "category": "Sequencer",
}

import bpy
import sys
import subprocess
import site
import os

# --- Library Installation ---

def ensure_libs():
    """
    Checks for and installs missing libraries (numpy, scipy, librosa).
    Returns True if all libraries are available, False otherwise.
    """
    py_exec = sys.executable
    required_libs = ["numpy", "scipy", "librosa"]
    missing_libs = []

    for lib_name in required_libs:
        try:
            __import__(lib_name)
        except ImportError:
            missing_libs.append(lib_name)

    if not missing_libs:
        return True

    print(f"The following required libraries are missing: {', '.join(missing_libs)}")
    print("Attempting to install...")

    try:
        subprocess.check_call([py_exec, "-m", "ensurepip"])
    except subprocess.CalledProcessError as e:
        print(f"Warning: Could not ensure pip is available: {e}")
    
    for lib_name in missing_libs:
        print(f"Installing '{lib_name}'...")
        try:
            subprocess.check_call([py_exec, "-m", "pip", "install", lib_name, "--user"])
            print(f"Successfully installed '{lib_name}'.")
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Failed to install '{lib_name}'. Please install it manually.")
            return False
            
    user_site = site.getusersitepackages()
    if user_site not in sys.path:
        sys.path.append(user_site)

    print("All required libraries are now installed and available.")
    return True

# --- Core Synchronization Logic ---

def find_offset(ref_filepath, target_filepath, context):
    """
    Calculates the precise frame offset between two audio files using a two-step process:
    1. Find Peak: Locates the loudest point (e.g., a clapperboard) in each file for a rough alignment.
    2. Correlate: Performs a cross-correlation on a small window around those peaks
       to find the exact sample-level offset for a perfect sync.
    """
    import numpy as np
    import librosa
    from scipy import signal

    try:
        # Load audio, resampling the target to match the reference's sample rate
        print(f"Loading reference: {os.path.basename(ref_filepath)}")
        ref_y, ref_sr = librosa.load(ref_filepath, sr=None, mono=True)
        print(f"Loading target: {os.path.basename(target_filepath)}")
        target_y, _ = librosa.load(target_filepath, sr=ref_sr, mono=True)

        # Step 1: Find the approximate sync point by locating the peak amplitude.
        ref_peak_index = np.argmax(np.abs(ref_y))
        target_peak_index = np.argmax(np.abs(target_y))
        print(f"Reference peak found at {ref_peak_index / ref_sr:.3f}s")
        print(f"Target peak found at {target_peak_index / ref_sr:.3f}s")
        rough_offset_samples = ref_peak_index - target_peak_index

        # Step 2: Refine the sync with a precise cross-correlation around the peak.
        # This is much faster than correlating the entire files.
        window_size_sec = 0.5  # Window of audio to analyze around the peak
        window_samples = int(window_size_sec * ref_sr)
        half_window = window_samples // 2
        
        # Extend the search window slightly to account for inaccuracies in the initial peak finding.
        search_window_extension = int(0.1 * ref_sr)

        ref_start = max(0, ref_peak_index - half_window)
        ref_end = min(len(ref_y), ref_peak_index + half_window)
        ref_chunk = ref_y[ref_start:ref_end]

        target_start = max(0, target_peak_index - half_window - search_window_extension)
        target_end = min(len(target_y), target_peak_index + half_window + search_window_extension)
        target_search_chunk = target_y[target_start:target_end]

        if len(ref_chunk) == 0 or len(target_search_chunk) < len(ref_chunk):
            print("Warning: Could not extract valid audio chunk. Using rough alignment only.")
            fine_offset_samples = 0
        else:
            correlation = signal.correlate(target_search_chunk, ref_chunk, mode='valid', method='fft')
            lag_index = np.argmax(correlation)
            
            # `lag_index` is where the ref_chunk was found within the target_search_chunk.
            # The *expected* start position was `search_window_extension`.
            # The difference is our fine-tuning adjustment, which must be subtracted from the rough offset.
            fine_offset_samples = -(lag_index - search_window_extension)
        
        print(f"Fine correlation offset found: {fine_offset_samples} samples ({fine_offset_samples/ref_sr:.4f}s)")

        # Calculate the final offset in samples and convert to frames.
        total_offset_samples = rough_offset_samples + fine_offset_samples
        
        fps = context.scene.render.fps / context.scene.render.fps_base
        offset_seconds = total_offset_samples / ref_sr
        offset_frames = int(round(offset_seconds * fps))

        return offset_frames

    except Exception as e:
        print(f"An error occurred during audio processing: {e}")
        import traceback
        traceback.print_exc()
        return None

# --- Blender Operator ---

class SEQUENCER_OT_SyncAudioToActive(bpy.types.Operator):
    bl_idname = "sequencer.sync_audio_to_active"
    bl_label = "Sync Audio to Active Strip"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not (context.scene and context.scene.sequence_editor):
            return False
        active_strip = context.scene.sequence_editor.active_strip
        if not active_strip or active_strip.type != 'SOUND':
            return False
        
        # Ensure there's at least one other selected sound strip to sync
        other_sound_strips = [s for s in context.selected_sequences if s.type == 'SOUND' and s != active_strip]
        return len(other_sound_strips) > 0

    def execute(self, context):
        if not ensure_libs():
            self.report({'ERROR'}, "Could not install required Python libraries. See console for details.")
            return {'CANCELLED'}
            
        sequencer = context.scene.sequence_editor
        active_strip = sequencer.active_strip
        strips_to_sync = [s for s in context.selected_sequences if s.type == 'SOUND' and s != active_strip]

        ref_filepath = bpy.path.abspath(active_strip.sound.filepath)
        if not os.path.exists(ref_filepath):
            self.report({'ERROR'}, f"Reference audio file not found: {ref_filepath}")
            return {'CANCELLED'}

        strips_synced_count = 0
        for strip in strips_to_sync:
            self.report({'INFO'}, f"Processing '{strip.name}'...")
            
            target_filepath = bpy.path.abspath(strip.sound.filepath)
            if not os.path.exists(target_filepath):
                self.report({'WARNING'}, f"Target audio file not found for strip '{strip.name}'. Skipping.")
                continue

            offset_frames = find_offset(ref_filepath, target_filepath, context)

            if offset_frames is not None:
                # The reference strip's start frame is the anchor. The `offset_frames` is the
                # calculated shift for the target's audio content. We must also subtract the
                # target strip's own `frame_offset_start` (its "trim in" point) to align the
                # start of the audio data correctly.
                strip.frame_start = active_strip.frame_start + offset_frames - strip.frame_offset_start
                strips_synced_count += 1
                self.report({'INFO'}, f"Synced '{strip.name}' to '{active_strip.name}'. Offset: {offset_frames} frames.")
            else:
                self.report({'ERROR'}, f"Failed to calculate offset for '{strip.name}'. See system console for details.")

        self.report({'INFO'}, f"Sync operation complete. {strips_synced_count} strip(s) moved.")
        return {'FINISHED'}

# --- Registration ---

def draw_menu(self, context):
    layout = self.layout
    layout.separator()
    layout.operator(SEQUENCER_OT_SyncAudioToActive.bl_idname)

def register():
    bpy.utils.register_class(SEQUENCER_OT_SyncAudioToActive)
    bpy.types.SEQUENCER_MT_strip_transform.append(draw_menu)

def unregister():
    bpy.utils.unregister_class(SEQUENCER_OT_SyncAudioToActive)
    bpy.types.SEQUENCER_MT_strip_transform.remove(draw_menu)

if __name__ == "__main__":
    register()
