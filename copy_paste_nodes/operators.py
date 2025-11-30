import bpy
from bpy.types import Operator

import json

from . import json_nodes

_message = "Copy/Paste Nodes JSON export (https://extensions.blender.org/add-ons/copy-paste-nodes/)"


class NODE_OT_clipboard_copy_json(Operator):
    """Copy the selected nodes to the system clipboard as JSON"""

    bl_idname = "node.clipboard_copy_json"
    bl_label = "Copy as JSON"
    bl_options = {'REGISTER', 'UNDO'}

    include_groups: bpy.props.BoolProperty(name="Include Groups", default=True)

    @classmethod
    def poll(cls, context):
        return (
            context.space_data
            and context.space_data.type == 'NODE_EDITOR'
            and context.space_data.edit_tree is not None
        )

    def execute(self, context):
        context.window_manager.clipboard = (
            "# " + _message + "\n" + json_nodes.dumps_compact(
            json_nodes.nodes_to_dict(
                [n for n in context.space_data.edit_tree.nodes if n.select],
                include_groups=self.include_groups
            )
        ))
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "include_groups")

class NODE_OT_clipboard_paste_json(Operator):
    """Paste nodes from JSON in the system clipboard to the active node tree"""

    bl_idname = "node.clipboard_paste_json"
    bl_label = "Paste from JSON"
    bl_options = {'REGISTER', 'UNDO'}

    reuse_existing: bpy.props.BoolProperty(name="Reuse Existing Groups", default=True)

    @classmethod
    def poll(cls, context):
        return (
            context.space_data
            and context.space_data.type == 'NODE_EDITOR'
            and context.space_data.edit_tree is not None
        )

    def execute(self, context):
        lines = context.window_manager.clipboard.splitlines()
        if not lines:
            self.report({'ERROR'}, "The clipboard is empty")
            return {'CANCELLED'}
        if lines[0].startswith('#'):
            lines = lines[1:]
        try:
            nodes_dict = json.loads('\n'.join(lines))
        except json.JSONDecodeError as e:
            self.report({'ERROR'}, f"The clipboard could not be decoded as JSON: {e}")
            return {'CANCELLED'}
        try:
            json_nodes.validate_schema(nodes_dict, json_nodes.SCHEMA)
        except TypeError as e:
            self.report({'ERROR'}, f"Schema error in JSON: {e}")
            return {'CANCELLED'}
        for n in context.space_data.edit_tree.nodes:
            n.select = False
        json_nodes.dict_to_nodes(
            context.space_data.edit_tree,
            context.space_data.cursor_location,
            nodes_dict,
            reuse_existing=self.reuse_existing
        )
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "reuse_existing")


register, unregister = bpy.utils.register_classes_factory((
    NODE_OT_clipboard_copy_json,
    NODE_OT_clipboard_paste_json,
))

