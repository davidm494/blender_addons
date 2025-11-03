bl_info = {
    "name": "Auto Track Weights",
    "author": "David Murmann",
    "version": (0, 2),
    "blender": (4, 2, 0),
    "location": "Clip Editor",
    "description": "Automatically adjust the weights of tracking markers",
    "warning": "",
    "doc_url": "",
    "tracker_url": "https://github.com/davidm494/blender_addons",
    "category": "Tracking",
}

import bpy
from bpy.types import Operator, Panel

def clear_animation_data_property(obj, prop):
    animation_data = obj.id_data.animation_data
    action = animation_data and animation_data.action
    if not action:
        return
    data_path = obj.path_from_id(prop)
    if bpy.app.version < (5, 0, 0):
        to_remove = [fc for fc in action.fcurves if fc.data_path == data_path]
        for fc in to_remove:
            action.fcurves.remove(fc)
    else:
        from bpy_extras import anim_utils
        action_slot = animation_data.action_slot
        channelbag = anim_utils.action_get_channelbag_for_slot(action, action_slot)
        to_remove = [fc for fc in channelbag.fcurves if fc.data_path == data_path]
        for fc in to_remove:
            channelbag.fcurves.remove(fc)

def process_markers_in_track(track, falloff_frames):
    t = track
    # nothing to do if all markers are disabled
    if not len([m for m in t.markers if not m.mute]):
        return
    if falloff_frames < 1:
        return

    # clear any previous animation curve on track.weight
    clear_animation_data_property(t, 'weight')

    min_frame = -(2**30)
    max_frame = 2**30

    # clips implicitly start at 1 for marker frame numbers
    clip_sfra = 1
    clip_efra = t.id_data.frame_duration

    markers = list(enumerate(t.markers))

    # backwards pass to identify the next disabled frame for each marker
    next_disabled = max_frame
    next_frame = clip_efra + 1
    next_disabled_frame = [max_frame] * len(markers)
    for i, m in reversed(markers):
        if m.mute and (m.frame < clip_sfra or m.frame > clip_efra):
            # ignore out of bounds
            continue
        if m.mute:
            next_disabled = m.frame
        elif next_frame - m.frame > 1:
            next_disabled = m.frame + 1
        next_disabled_frame[i] = next_disabled
        next_frame = m.frame

    last_disabled = min_frame
    last_frame = clip_sfra - 1
    for i, m in markers:
        if m.mute and (m.frame < clip_sfra or m.frame > clip_efra):
            # ignore out of bounds
            continue
        if m.mute:
            last_disabled = m.frame
        elif m.frame - last_frame > 1:
            last_disabled = m.frame - 1
        last_frame = m.frame

        if last_disabled == min_frame:
            dist_left = max_frame
        else:
            dist_left = m.frame - last_disabled
        if next_disabled_frame[i] == max_frame:
            dist_right = max_frame
        else:
            dist_right = next_disabled_frame[i] - m.frame
        boundary_dist = min(dist_left, dist_right)

        if boundary_dist <= falloff_frames:
            t.weight = boundary_dist / falloff_frames
            t.keyframe_insert(data_path='weight', frame=m.frame + t.id_data.frame_start - 1)


def process_tracks_in_clip(clip, falloff_frames):
    # only process the active tracking object
    for track in clip.tracking.objects.active.tracks:
        # only change selected and visible tracks
        if not track.select or track.hide:
            continue
        process_markers_in_track(track, falloff_frames)


class CLIP_OT_AutoTrackWeight(Operator):
    """Reduce weight of selected tracks near track boundaries over time"""

    bl_idname = "clip.auto_track_weight"
    bl_label = "Set Track Weights"
    bl_options = {'REGISTER', 'UNDO'}

    falloff_frames: bpy.props.IntProperty(name="Falloff Frames", default=12, min=0, max=1000)

    @classmethod
    def poll(cls, context):
        return (context.space_data.type == 'CLIP_EDITOR')

    def execute(self, context):
        process_tracks_in_clip(context.space_data.clip, self.falloff_frames)
        return {'FINISHED'}


class CLIP_PT_AutoTrackWeightPanel(Panel):
    bl_idname = "CLIP_PT_AutoTrackWeightPanel"
    bl_label = "Auto Track Weights"
    bl_space_type = "CLIP_EDITOR"
    bl_region_type = "TOOLS"
    bl_category = "Track"

    def draw(self, context):
        col = self.layout.column()
        col.operator(CLIP_OT_AutoTrackWeight.bl_idname)


_classes = (CLIP_OT_AutoTrackWeight, CLIP_PT_AutoTrackWeightPanel)
_addon_keymaps = []

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is not None:
        km = kc.keymaps.new(name='Clip Editor', space_type='CLIP_EDITOR')
        kmi = km.keymap_items.new(CLIP_OT_AutoTrackWeight.bl_idname, 'W', 'PRESS', alt=True)
        _addon_keymaps.append((km, kmi))

def unregister():
    for km, kmi in _addon_keymaps:
        km.keymap_items.remove(kmi)
    _addon_keymaps.clear()

    for cls in _classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
