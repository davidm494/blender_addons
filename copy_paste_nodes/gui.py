import bpy

import sys

def draw_clipboard_copypaste(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("node.clipboard_copy_json", icon='COPYDOWN')
    layout.operator("node.clipboard_paste_json", icon='PASTEDOWN')

_addon_keymaps = []

def register():
    bpy.types.NODE_MT_node.append(draw_clipboard_copypaste)
    if sys.platform == "darwin":
        ctrl_cmd = {"oskey": True}
    else:
        ctrl_cmd = {"ctrl": True}

    kc = bpy.context.window_manager.keyconfigs.addon
    if kc is not None:
        km = kc.keymaps.new(name='Node Editor', space_type='NODE_EDITOR')
        _addon_keymaps.append((km,
            km.keymap_items.new("node.clipboard_copy_json", 'C', 'PRESS', alt=True, **ctrl_cmd)))
        _addon_keymaps.append((km,
            km.keymap_items.new("node.clipboard_paste_json", 'V', 'PRESS', alt=True, **ctrl_cmd)))

def unregister():
    for km, kmi in _addon_keymaps:
        km.keymap_items.remove(kmi)
    _addon_keymaps.clear()

    bpy.types.NODE_MT_node.remove(draw_clipboard_copypaste)
