bl_info = {
    "name": "Professional Audio Sync Tools",
    "author": "Your Name (Adapted from tintwotin/ChatGPT)",
    "version": (16, 1, 0), # FINAL FIX: Lowered threshold and repaired 'Sync to Active Strip'.
    "blender": (2, 93, 0),
    "location": "Sequencer > Strip > Transform",
    "description": "A suite of tools for audio synchronization. Uses a definitive competitive verification system for maximum accuracy.",
    "warning": "First run installs libraries, requires a second run to operate.",
    "doc_url": "",
    "category": "Sequencer",
}

import bpy
import sys, subprocess, site, os, tempfile, shutil, importlib

# --- Constants & Configuration ---
VIDEO_EXTENSIONS = {'.mov', '.mp4', '.mkv', '.avi', '.mts', '.m2ts'}
AUDIO_EXTENSIONS = {'.wav', '.aiff', '.aif', '.flac', '.mp3', '.ogg'}
REQUIRED_LIBS = ["numpy", "scipy", "moviepy"] 
PEAK_PROFILE_WINDOW_SEC = 1.5
DURATION_TOLERANCE_SEC = 25.0
ANALYSIS_DURATION_SEC = 90.0
CANDIDATES_TO_VERIFY = 8
# --- VERIFICATION VALUE LOWERED AS REQUESTED ---
MINIMUM_VERIFIED_CORRELATION = 0.2


# --- Library Installation and Management ---
def check_libs(): return [lib for lib in REQUIRED_LIBS if not importlib.util.find_spec(lib)]
def install_libs(missing_libs):
    py_exec = sys.executable; print(f"Missing: {', '.join(missing_libs)}. Installing...")
    try:
        subprocess.check_call([py_exec, "-m", "ensurepip"])
        for lib in missing_libs:
            print(f"Installing '{lib}'...")
            subprocess.check_call([py_exec, "-m", "pip", "install", lib, "--user", "--quiet"])
        return True
    except Exception as e: print(f"ERROR: Failed to install libraries: {e}"); return False

# --- Core Logic Functions ---
def extract_audio_to_wav(strip, temp_dir):
    from moviepy import VideoFileClip, AudioFileClip
    original_path = bpy.path.abspath(strip.sound.filepath)
    ext = os.path.splitext(original_path)[1].lower()
    safe_name = "".join(c for c in strip.name if c.isalnum() or c in ('_')).rstrip()
    wav_path = os.path.join(temp_dir, f"{safe_name}.wav")
    try:
        if ext == '.wav': shutil.copy(original_path, wav_path)
        elif ext in VIDEO_EXTENSIONS:
            with VideoFileClip(original_path) as video: video.audio.write_audiofile(wav_path, codec='pcm_s16le', logger=None)
        else:
            with AudioFileClip(original_path) as audio: audio.write_audiofile(wav_path, codec='pcm_s16le', logger=None)
        return wav_path
    except Exception as e: print(f"ERROR: MoviePy failed on {os.path.basename(original_path)}: {e}"); return None

def analyze_for_matching(wav_path):
    import numpy as np, librosa
    try:
        y, sr = librosa.load(wav_path, sr=None, mono=True, duration=ANALYSIS_DURATION_SEC)
        duration = librosa.get_duration(path=wav_path)
        peak_index = np.argmax(np.abs(y))
        window_samples = int(PEAK_PROFILE_WINDOW_SEC * sr); half_window = window_samples // 2
        start, end = peak_index - half_window, peak_index + half_window
        fingerprint = y[max(0, start):min(len(y), end)]
        return { "duration": duration, "fingerprint": fingerprint, "sr": sr }
    except Exception as e: print(f"Error analyzing for matching: {e}"); return None

def calculate_peak_similarity(target_data, candidate_data):
    import numpy as np; from scipy import signal
    try:
        t_fp, c_fp = target_data['fingerprint'], candidate_data['fingerprint']
        if len(t_fp) == 0 or len(c_fp) == 0: return 0.0
        t_norm = t_fp / (np.sqrt(np.mean(t_fp**2)) + 1e-6); c_norm = c_fp / (np.sqrt(np.mean(c_fp**2)) + 1e-6)
        corr = signal.correlate(t_norm, c_norm, 'valid') if len(t_norm)>len(c_norm) else signal.correlate(c_norm, t_norm, 'valid')
        return np.max(np.abs(corr))
    except Exception: return 0.0

def calculate_energy_correlation(audio_path, video_path, sr):
    import numpy as np, librosa
    try:
        audio_y, _ = librosa.load(audio_path, sr=sr, mono=True)
        video_y, _ = librosa.load(video_path, sr=sr, mono=True)
        ref_peak, target_peak = np.argmax(np.abs(video_y)), np.argmax(np.abs(audio_y))
        offset_samples = ref_peak - target_peak
        if offset_samples > 0: aligned_video_y = video_y[offset_samples:]
        else: aligned_video_y = np.pad(video_y, (abs(offset_samples), 0), 'constant')
        min_len = min(len(audio_y), len(aligned_video_y))
        audio_y_trimmed, video_y_trimmed = audio_y[:min_len], aligned_video_y[:min_len]
        audio_rms = librosa.feature.rms(y=audio_y_trimmed)[0]
        video_rms = librosa.feature.rms(y=video_y_trimmed)[0]
        return np.corrcoef(audio_rms, video_rms)[0, 1]
    except Exception as e: print(f"Error during verification: {e}"); return 0.0

def find_offset_samples(ref_path, target_path, sr):
    import numpy as np, librosa; from scipy import signal
    try:
        ref_y, _ = librosa.load(ref_path, sr=sr, mono=True); target_y, _ = librosa.load(target_path, sr=sr, mono=True)
        ref_peak, target_peak = np.argmax(np.abs(ref_y)), np.argmax(np.abs(target_y))
        rough_offset = ref_peak - target_peak
        win_s=int(0.5*sr); half_win=win_s//2; search_ext=int(0.1*sr)
        ref_chunk=ref_y[max(0,ref_peak-half_win):min(len(ref_y),ref_peak+half_win)]
        target_chunk=target_y[max(0,target_peak-half_win-search_ext):min(len(target_y),target_peak+half_win+search_ext)]
        if len(ref_chunk)==0 or len(target_chunk)<len(ref_chunk): fine_offset=0
        else: lag=np.argmax(signal.correlate(target_chunk,ref_chunk,'valid')); fine_offset=-(lag-search_ext)
        return rough_offset + fine_offset
    except Exception: return None

# --- Asynchronous Operator ---
class SEQUENCER_OT_MatchAndSyncAudio(bpy.types.Operator):
    bl_idname = "sequencer.match_and_sync_audio"; bl_label = "Match and Sync Audio"; bl_options = {'REGISTER', 'UNDO'}
    _timer = None; state = 'INITIALIZING'
    
    def modal(self, context, event):
        if event.type in {'RIGHTMOUSE', 'ESC'}: self.cancel(context); return {'CANCELLED'}
        if event.type == 'TIMER':
            if self.state == 'ANALYZING_FILES':
                try:
                    strip = next(self.process_iter)
                    path = extract_audio_to_wav(strip, self.temp_dir)
                    if path: self.extracted_paths[strip] = path; self.analysis_cache[strip] = analyze_for_matching(path)
                except StopIteration:
                    self.report({'INFO'}, "Verifying top candidates...")
                    self.state = 'VERIFYING_CANDIDATES'
                    self.build_candidate_lists(); self.process_iter = iter(self.verification_queue)
            elif self.state == 'VERIFYING_CANDIDATES':
                try:
                    pair = next(self.process_iter)
                    audio, video = pair['audio'], pair['video']
                    score = calculate_energy_correlation(self.extracted_paths[audio], self.extracted_paths[video], self.analysis_cache[audio]['sr'])
                    self.verification_matrix.append({'score': score, 'audio': audio, 'video': video})
                    self.report({'INFO'}, f"  Verified '{audio.name}' + '{video.name}' -> Score: {score:.4f}")
                    print(f"  Verified '{audio.name}' + '{video.name}' -> Score: {score:.4f}")
                except StopIteration:
                    self.report({'INFO'}, "Assigning best pairs...")
                    self.state = 'ASSIGNING_PAIRS'
                    self.assign_final_pairs(context)
                    self.state = 'FINISHED'
            elif self.state == 'FINISHED':
                self.report({'INFO'}, f"Sync complete. {self.synced_count} pairs assigned.")
                self.cancel(context); return {'FINISHED'}
        return {'PASS_THROUGH'}

    def assign_final_pairs(self, context):
        self.verification_matrix.sort(key=lambda x: x['score'], reverse=True)
        synced_audio, synced_video = set(), set()
        for pair in self.verification_matrix:
            audio, video, score = pair['audio'], pair['video'], pair['score']
            if audio in synced_audio or video in synced_video: continue
            if score < MINIMUM_VERIFIED_CORRELATION: break
            print(f"Confirmed Match: '{audio.name}' + '{video.name}' (Verified Score: {score:.4f})")
            self.report({'INFO'}, f"Confirmed Match: '{audio.name}' + '{video.name}' (Verified Score: {score:.4f})")
            offset_samples = find_offset_samples(self.extracted_paths[video], self.extracted_paths[audio], self.analysis_cache[audio]['sr'])
            if offset_samples is not None:
                fps = context.scene.render.fps / context.scene.render.fps_base
                offset_frames = int(round((offset_samples / self.analysis_cache[audio]['sr']) * fps))
                audio.frame_start = video.frame_start + offset_frames - audio.frame_offset_start
                synced_audio.add(audio); synced_video.add(video); self.synced_count += 1
                
    def build_candidate_lists(self):
        self.verification_queue = []
        vid_strips = {s: d for s, d in self.analysis_cache.items() if s in self.video_audio_strips and d}
        aud_strips = {s: d for s, d in self.analysis_cache.items() if s in self.dedicated_audio_strips and d}
        for audio_strip, adata in aud_strips.items():
            scores = []
            for video_strip, vdata in vid_strips.items():
                if abs(adata['duration'] - vdata['duration']) <= DURATION_TOLERANCE_SEC:
                    score = calculate_peak_similarity(adata, vdata)
                    scores.append({'score': score, 'video': video_strip})
            scores.sort(key=lambda x: x['score'], reverse=True)
            for item in scores[:CANDIDATES_TO_VERIFY]:
                self.verification_queue.append({'audio': audio_strip, 'video': item['video']})
            
    def execute(self, context):
        missing = check_libs()
        if missing:
            self.report({'INFO'}, "Installing required libraries...");
            if install_libs(missing): self.report({'WARNING'}, "Libraries installed. Please run again.")
            else: self.report({'ERROR'}, "Failed to install libraries.")
            return {'CANCELLED'}
        self.context = context; self.temp_dir = tempfile.mkdtemp()
        self.video_audio_strips, self.dedicated_audio_strips = [], []
        for s in context.selected_sequences:
            if s.type == 'SOUND' and s.sound:
                ext = os.path.splitext(s.sound.filepath)[1].lower()
                if ext in VIDEO_EXTENSIONS: self.video_audio_strips.append(s)
                elif ext in AUDIO_EXTENSIONS or ext == '.wav': self.dedicated_audio_strips.append(s)
        if not self.video_audio_strips or not self.dedicated_audio_strips:
            self.report({'ERROR'}, "Selection needs video-audio and audio-only strips."); shutil.rmtree(self.temp_dir); return {'CANCELLED'}
        self.process_iter = iter(self.video_audio_strips + self.dedicated_audio_strips)
        self.extracted_paths, self.analysis_cache, self.verification_matrix = {}, {}, []
        self.synced_count = 0
        context.window_manager.modal_handler_add(self)
        self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
        self.state = 'ANALYZING_FILES'; self.report({'INFO'}, "Starting sync process... Analyzing files...")
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if self._timer: context.window_manager.event_timer_remove(self._timer); self._timer = None
        if hasattr(self, 'temp_dir') and os.path.exists(self.temp_dir): shutil.rmtree(self.temp_dir)

# --- CORRECTED 'Sync to Active' OPERATOR ---
class SEQUENCER_OT_SyncAudioToActive(bpy.types.Operator):
    bl_idname = "sequencer.sync_audio_to_active"; bl_label = "Sync Audio to Active Strip"; bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        if not (context.scene and context.scene.sequence_editor): return False
        active_strip = context.scene.sequence_editor.active_strip
        if not active_strip or active_strip.type != 'SOUND': return False
        return len([s for s in context.selected_sequences if s.type == 'SOUND' and s != active_strip]) > 0
    def execute(self, context):
        missing = check_libs();
        if missing:
            self.report({'INFO'}, "Installing libraries...");
            if install_libs(missing): self.report({'WARNING'}, "Libraries installed. Please run again.")
            else: self.report({'ERROR'}, "Failed to install libraries.")
            return {'CANCELLED'}
        temp_dir = tempfile.mkdtemp()
        try:
            active_strip = context.scene.sequence_editor.active_strip
            strips_to_sync = [s for s in context.selected_sequences if s.type == 'SOUND' and s != active_strip]
            ref_path = extract_audio_to_wav(active_strip, temp_dir)
            if not ref_path: self.report({'ERROR'}, f"Failed to prepare audio for {active_strip.name}"); return {'CANCELLED'}
            try: import librosa; sr = librosa.get_samplerate(ref_path)
            except Exception as e: print(f"Could not get sample rate: {e}"); shutil.rmtree(temp_dir); return {'CANCELLED'}
            for strip in strips_to_sync:
                target_path = extract_audio_to_wav(strip, temp_dir)
                if not target_path: continue
                # This operator now correctly calls the simple offset function.
                offset_samples = find_offset_samples(ref_path, target_path, sr)
                if offset_samples is not None:
                    # And applies it with the correct math.
                    fps = context.scene.render.fps / context.scene.render.fps_base
                    offset_frames = int(round((offset_samples / sr) * fps))
                    strip.frame_start = active_strip.frame_start + offset_frames - strip.frame_offset_start
                else:
                    self.report({'WARNING'}, f"Could not determine offset for '{strip.name}'.")
        finally: shutil.rmtree(temp_dir)
        return {'FINISHED'}

# --- Registration ---
def draw_menu(self, context):
    layout = self.layout; layout.separator()
    layout.operator(SEQUENCER_OT_MatchAndSyncAudio.bl_idname, icon='AUTOMERGE_ON')
    layout.operator(SEQUENCER_OT_SyncAudioToActive.bl_idname, icon='LINKED')
def register():
    bpy.utils.register_class(SEQUENCER_OT_MatchAndSyncAudio); bpy.utils.register_class(SEQUENCER_OT_SyncAudioToActive)
    bpy.types.SEQUENCER_MT_strip_transform.append(draw_menu)
def unregister():
    bpy.utils.unregister_class(SEQUENCER_OT_MatchAndSyncAudio); bpy.utils.unregister_class(SEQUENCER_OT_SyncAudioToActive)
    bpy.types.SEQUENCER_MT_strip_transform.remove(draw_menu)
if __name__ == "__main__": register()
