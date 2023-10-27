bl_info = {
    "name": "Sync Sound to Sound",
    "author": "tintwotin",
    "version": (1, 0),
    "blender": (2, 80, 0),
    "location": "Sequencer > Strip > Transform > Sync Sound to Sound",
    "description": "Sync Sound to Sound",
    "warning": "",
    "doc_url": "",
    "category": "Seqeuncer",
}

import bpy, sys
import numpy as np
from scipy import signal

try:
    import librosa
except ImportError:
    app_path = site.USER_SITE
    if app_path not in sys.path:
        sys.path.append(app_path)
    pybin = sys.executable
    subprocess.check_call([pybin, "-m", "pip", "install", "librosa"])
    import librosa

    print("librosa package installed.")


def calculate_offset(within_file, find_file, window):
    # Normalize both input audio in memory
    y_within, sr_within = librosa.load(within_file, sr=None)
    y_find, _ = librosa.load(find_file, sr=sr_within)

    # Normalize the audio
    peak_amplitude_within = max(abs(y_within))
    peak_amplitude_find = max(abs(y_find))

    scaling_factor_within = 1.0 / peak_amplitude_within
    scaling_factor_find = 1.0 / peak_amplitude_find

    y_within = y_within * scaling_factor_within
    y_find = y_find * scaling_factor_find

    # Calculate the offset
    c = signal.correlate(
        y_within, y_find[: sr_within * window], mode="valid", method="fft"
    )
    peak = np.argmax(c)
    offset = round(peak / sr_within, 2)

    return offset


class SEQUENCER_OT_AudioOffsetOperator(bpy.types.Operator):
    bl_idname = "sequencer.audio_offset"
    bl_label = "Sync Sound to Sound"

    @classmethod
    def poll(cls, context):
        if (
            context.scene
            and context.scene.sequence_editor
            and context.scene.sequence_editor.active_strip
        ):
            return context.scene.sequence_editor.active_strip.type == "SOUND"
        else:
            return False

    def execute(self, context):
        active_strip = context.scene.sequence_editor.active_strip

        if active_strip and active_strip.type == "SOUND":
            find_file = bpy.path.abspath(active_strip.sound.filepath)

            for strip in context.selected_sequences:
                if strip.type == "SOUND" and strip != active_strip:
                    within_file = bpy.path.abspath(strip.sound.filepath)
                    offset = calculate_offset(within_file, find_file, 5)
                    # self.report({'INFO'}, f"Offset between {active_strip.name} and {strip.name}: {offset} seconds")

                    # Calculate the frame offset based on the offset in seconds
                    frame_offset = round(
                        offset
                        * (context.scene.render.fps / context.scene.render.fps_base)
                    )
                    strip.frame_start = active_strip.frame_start + frame_offset
        return {"FINISHED"}


def draw_func(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("sequencer.audio_offset")


def register():
    bpy.utils.register_class(SEQUENCER_OT_AudioOffsetOperator)
    bpy.types.SEQUENCER_MT_strip_transform.append(draw_func)


def unregister():
    bpy.utils.unregister_class(SEQUENCER_OT_AudioOffsetOperator)
    bpy.types.SEQUENCER_MT_strip_transform.remove(draw_func)


if __name__ == "__main__":
    register()
