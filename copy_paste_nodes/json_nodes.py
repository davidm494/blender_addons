import bpy
from mathutils import Vector, Color, Euler, Quaternion

import collections
import json
import numpy

JSON_SCHEMA_VERSION = 2

# Simple declarative schema that serves as documentation and basic checking of valid JSON.
# This will not check everything, as we want to be compatible with future blender additions
# of new properties, but should catch most things that would stop us from producing any
# useful output when loading from JSON.

class Optional:
    def __init__(self, key):
        self.key = key
    def __repr__(self):
        return f'Optional("{self.key}")'

class MapOf:
    def __init__(self, value_schema):
        self.value_schema = value_schema
    def __repr__(self):
        return f'MapOf({self.value_schema!r})'

_NODES_SCHEMA = [
    {
        "bl_idname": str,
        "props": {"name": str},
        Optional("node_tree"): str,
        Optional("parent"): str,
        Optional("paired_output"): str,
        Optional("inputs"): MapOf({Optional("hide"): bool, Optional("links"): [(str, int)]}),
        Optional("outputs"): MapOf({Optional("hide"): bool}),
    },
]

SCHEMA = {
    "version": int,
    "type": str,
    "app_version": (int, int, int),
    "nodes": _NODES_SCHEMA,

    Optional("node_trees"): MapOf({
        "nodes": _NODES_SCHEMA,
        "interface": {
            Optional("items_tree"): [{Optional("in_out"): str}],
        },
        Optional("props"): {},
    }),
}

def validate_schema(obj, schema, path="root"):
    """
    Recursively validate obj against the schema. Only fields listed in the
    schema are checked, any other fields are ignored.
    Raises TypeError if a type mismatch or missing required key is found.
    """
    if isinstance(schema, type):
        if not isinstance(obj, schema):
            raise TypeError(f"{path} expected {schema.__name__}, got {type(obj).__name__}")
        return

    if isinstance(schema, list):
        if not isinstance(obj, list):
            raise TypeError(f"{path} expected list, got {type(obj).__name__}")
        if not schema:
            return
        for i, item in enumerate(obj):
            validate_schema(item, schema[0], path=f"{path}[{i}]")
        return

    if isinstance(schema, dict):
        if not isinstance(obj, dict):
            raise TypeError(f"{path} expected dict, got {type(obj).__name__}")

        for key, subschema in schema.items():
            if isinstance(key, Optional):
                key_name = key.key
                if key_name in obj:
                    validate_schema(obj[key_name], subschema, path=f"{path}.{key_name}")
            else:
                if key not in obj:
                    raise TypeError(f"{path} missing required key '{key}'")
                validate_schema(obj[key], subschema, path=f"{path}.{key}")
        return

    if isinstance(schema, tuple):
        if not isinstance(obj, (tuple, list)):
            raise TypeError(f"{path} expected tuple/list of length {len(schema)}, got {type(obj).__name__}")
        if len(obj) != len(schema):
            raise TypeError(f"{path} expected tuple/list of length {len(schema)}, got length {len(obj)}")
        for i, (item, subschema) in enumerate(zip(obj, schema)):
            validate_schema(item, subschema, path=f"{path}[{i}]")
        return

    if isinstance(schema, MapOf):
        if not isinstance(obj, dict):
            raise TypeError(f"{path} expected dict, got {type(obj).__name__}")
        for k, v in obj.items():
            validate_schema(v, schema.value_schema, path=f"{path}.{k}")
        return

    raise TypeError(f"{path} invalid schema type {type(schema)}")

_bpy_type_to_data_collection = {}
def _get_data_collection(id_type):
    """Check if data of type `id_type` are stored in a bpy.data collection. If so, return that collection."""
    # Fill lookup dict on first run, assuming bpy.data is static
    if not _bpy_type_to_data_collection:
        for prop in bpy.data.bl_rna.properties:
            if prop.type == 'COLLECTION':
                _bpy_type_to_data_collection[prop.fixed_type] = prop.identifier

    result = None
    while result is None:
        result = _bpy_type_to_data_collection.get(id_type)
        id_type = id_type.base
        if id_type is None:
            return None
    return getattr(bpy.data, result)

def _to_serializable(val):
    if isinstance(val, (list, tuple, Vector, Color, Euler, Quaternion, bpy.types.bpy_prop_array)):
        return [_to_serializable(v) for v in val]
    if isinstance(val, float):
        # Blender float properties are single precision, so round to the nearest float32
        return float(repr(numpy.float32(val)))
    if isinstance(val, (int, bool, str)) or val is None:
        return val
    # Fallback: stringify
    return str(val)

def _is_nonzero(val):
    if isinstance(val, (list, tuple, Vector, Color, Euler, Quaternion, bpy.types.bpy_prop_array)):
        return any([v for v in val])
    return bool(val)

# These are repeated a lot, abbreviating them makes the output much more readable
# (new names start with an underscore, so we hopefully don't collide with any actual props)
_long_to_short_prop_name = {
    'location_absolute': '_loc',
    'default_value': '_val',
}
_short_to_long_prop_name = {}
for _k, _v in _long_to_short_prop_name.items():
    _short_to_long_prop_name[_v] = _k
def _short_prop_name(name):
    return _long_to_short_prop_name.get(name, name)
def _long_prop_name(name):
    return _short_to_long_prop_name.get(name, name)

def _serialize_prop(properties, idblock, prop, defaults):
    v = getattr(idblock, prop.identifier, None)
    if v is None:
        return
    default = getattr(defaults, prop.identifier, None)
    if isinstance(v, bpy.types.bpy_prop_array):
        v = list(v)
    if isinstance(default, bpy.types.bpy_prop_array):
        default = list(default)
    if v == default:
         # v is default value, no need to store
        return

    key = _short_prop_name(prop.identifier)
    if prop.type == "POINTER":
        # Store name if id block can be accessed via bpy.data
        data_collection = _get_data_collection(v.bl_rna)
        if data_collection:
            properties[key] = v.name
        # Store parent index for interface.items_tree
        elif prop.identifier == "parent" and getattr(v, "index", -1) >= 0:
            properties[key] = v.index
    else:
        properties[key] = _to_serializable(v)

def _iter_properties(idblock, defaults=None, skip_props=(), always_include=()):
    properties = {}
    for prop in sorted(idblock.bl_rna.properties, key=lambda x: x.identifier):
        if prop.identifier in skip_props:
            continue
        if prop.is_hidden:
            continue

        if prop.type == 'COLLECTION':
            properties[_short_prop_name(prop.identifier)] = [_iter_properties(
                p,
                defaults,
                skip_props=skip_props,
                always_include=always_include,
            ) for p in getattr(idblock, prop.identifier)]
            continue

        force_include = prop.identifier in always_include
        if not force_include and prop.is_readonly:
            continue

        if prop.type in {'BOOLEAN', 'INT', 'FLOAT', 'ENUM', 'STRING', 'POINTER'}:
            _serialize_prop(properties, idblock, prop, None if force_include else defaults)
    return properties

def _socket_index(sockets, s):
    for i, x in enumerate(sockets):
        if x == s:
            return i
    raise ValueError("%r not found in sockets" % s)

def _serialize_nodes(nodes, default_nodes):
    nodes_payload = []
    node_names = set(n.name for n in nodes)

    for node in nodes:
        default_node = default_nodes[(node.bl_idname, getattr(node, "node_tree", None))]
        node_dict = {
            "bl_idname": node.bl_idname,
        }

        group_tree = getattr(getattr(node, "node_tree", None), "name", None)
        if group_tree is not None:
            node_dict["node_tree"] = group_tree

        paired_output = getattr(node, "paired_output", None)
        if paired_output is not None:
            node_dict["paired_output"] = node.paired_output.name

        is_reroute = (node.bl_idname == "NodeReroute")
        node_dict["props"] = _iter_properties(node, default_node, skip_props={
            # Don't include these, because they are stored differently
            "inputs",
            "outputs",
            "internal_links",
            "parent",

            # Ignoring these is cosmetic, as they don't change behavior
            "select",
            "location", # Keep location_absolute instead
            "socket_idname",
            "active_index",
            "active_generation_index",
            "active_input_index",
            "active_main_index",
        } | ({"width"} if is_reroute else set()), always_include={"name"})

        for socket_dir in ("inputs", "outputs"):
            sockets = {}
            for i, socket in enumerate(getattr(node, socket_dir)):
                default_sockets = getattr(default_node, socket_dir)
                if len(default_sockets):
                    default_socket = default_sockets[min(i, len(default_sockets)-1)]
                else:
                    default_socket = None
                props = {}
                # Only store value and hidden state. All other properties should be updated at runtime
                for k in ("default_value", "hide", "pin_gizmo") if not is_reroute else ():
                    prop = socket.bl_rna.properties.get(k)
                    if prop and (socket_dir == "inputs" or _is_nonzero(getattr(socket, prop.identifier))):
                        _serialize_prop(props, socket, prop, default_socket)
                # Store links in input sockets
                if socket_dir == "inputs" and socket.links:
                    props["links"] = [(
                        link.from_node.name,
                        _socket_index(link.from_node.outputs, link.from_socket)
                    ) for link in socket.links if link.from_node.name in node_names]
                if props:
                    # Name is not necessary, but nice for readability
                    if socket_dir == "inputs":
                        d = {"name": socket.name}
                        d.update(props)
                        sockets[str(i)] = d
                    else:
                        sockets[str(i)] = props
            if sockets:
                node_dict[socket_dir] = sockets

        if node.parent is not None:
            node_dict["parent"] = node.parent.name

        nodes_payload.append(node_dict)
    return nodes_payload

def _topological_sort(graph):
    seen = set()
    stack = []
    order = []
    q = list(graph)
    while q:
        v = q.pop()
        if v not in seen:
            seen.add(v)
            q.extend(graph[v])
            while stack and v not in graph[stack[-1]]:
                order.append(stack.pop())
            stack.append(v)
    return order + stack

def _collect_trees(nodes):
    stack = collections.deque((None, n) for n in nodes)
    trees = {}
    all_nodes = []

    while stack:
        parent, node = stack.popleft()
        all_nodes.append(node)
        nt = getattr(node, 'node_tree', None)
        if nt is not None:
            if node not in trees:
                stack.extend((nt, n) for n in nt.nodes)
                trees[nt] = set()
            if parent is not None:
                trees[parent].add(nt)
    return _topological_sort(trees), all_nodes

def nodes_to_dict(nodes, include_groups=True):
    if iter(nodes) is nodes:
        nodes = list(nodes)
    if not len(nodes):
        return {}
    if include_groups:
        trees, all_nodes = _collect_trees(nodes)
    else:
        trees, all_nodes = [], nodes
    tree_type = nodes[0].id_data.type

    node_types = set()
    for node in all_nodes:
        group_tree = getattr(node, "node_tree", None)
        node_types.add((node.bl_idname, group_tree))

    # To only store properties that are not at their default value, we create a
    # default version of every occuring node type in a new, hidden node group.
    # These will be compared against when serializing the actual nodes. The
    # defaults group will be deleted afterwards.
    default_nodes = {}
    node_group = bpy.data.node_groups.new('.defaults', nodes[0].id_data.bl_idname)
    for idname, group_tree in node_types:
        # Render layer nodes can only exist in the scene composite tree in
        # versions before 5.0. Just use a RGB constant node, this will only
        # result in some additional properties being stored.
        if bpy.app.version < (5, 0, 0) and idname == "CompositorNodeRLayers":
            default_node = node_group.nodes.new("CompositorNodeRGB")
        else:
            default_node = node_group.nodes.new(idname)
        if group_tree is not None:
            default_node.node_tree = group_tree
        default_nodes[(idname, group_tree)] = default_node
    default_socket = node_group.interface.new_socket("default")
    for (idname, _), node in default_nodes.items():
        if hasattr(node, "paired_output"):
            out_node = default_nodes.get((idname.replace("Input", "Output"), None))
            if out_node:
                node.pair_with_output(out_node)

    result = {"version": JSON_SCHEMA_VERSION, "type": tree_type, "app_version": bpy.app.version}
    try:
        result["nodes"] = _serialize_nodes(nodes, default_nodes)
        trees_dict = {}
        for tree in trees:
            trees_dict[tree.name] = {
                "nodes": _serialize_nodes(tree.nodes, default_nodes),
                "interface": _iter_properties(
                    tree.interface,
                    default_socket,
                    skip_props={"interface_items", "bl_socket_idname", "active_index"},
                    always_include={"in_out", "parent"},
                ),
                "props": _iter_properties(tree, node_group, skip_props={
                    "name",
                    "nodes",
                    "links",
                    "use_extra_user",
                }),
            }
        if trees_dict:
            result["node_trees"] = trees_dict
    finally:
        for node in default_nodes.values():
            node_group.nodes.remove(node)
        bpy.data.node_groups.remove(node_group)

    return result


def _map_attribute_to_socket_type(attr):
    return {
        "FLOAT": "FLOAT",
        "INT": "INT",
        "FLOAT_VECTOR": "VECTOR",
        "FLOAT_COLOR": "RGBA",
        "BOOLEAN": "BOOLEAN",
        "QUATERNION": "ROTATION",
        "FLOAT4X4": "MATRIX",
        # These are not selectable currently, give them some value anyways:
        "BYTE_COLOR": "RGBA",
        "STRING": "STRING",
        "FLOAT2": "VECTOR",
        "INT8": "INT",
        "INT16_2D": "VECTOR",
        "INT32_2D": "VECTOR",
    }[attr]

def _set_prop_on_idblock(idblock, identifier, value):
    prop = idblock.bl_rna.properties.get(identifier)
    if prop is None:
        # Silently ignore properties that don't exist for now (TODO: warning?)
        return
    if prop.type == 'POINTER':
        if value and type(value) == str:
            collection = _get_data_collection(prop.fixed_type)
            if not collection:
                return
            ptr_value = collection.get(value)
            if not ptr_value:
                return
            setattr(idblock, identifier, ptr_value)
    else:
        setattr(idblock, identifier, value)

def _create_nodes(target_tree, location_offset, nodes, trees, raw_trees):
    created = {}
    for nd in nodes:
        node = target_tree.nodes.new(nd["bl_idname"])
        group_tree_name = nd.get("node_tree")
        if group_tree_name is not None:
            group_tree = trees.get(group_tree_name)
            if not group_tree:
                if group_tree_name in raw_trees:
                    raise ValueError(f"node group used before definition: {group_tree_name}")
                group_tree = bpy.data.node_groups.get(group_tree_name)
            if group_tree:
                node.node_tree = group_tree
        node.name = nd["props"]["name"]

        created[nd["props"]["name"]] = (nd, node)

    # Process "Output" nodes first, so that zone item types get set before
    # corresponding "Input" nodes get processed. (input nodes depend on their
    # paired output for socket definitions)
    for nd, node in sorted(created.values(), key=lambda x: "Output" not in x[0]["bl_idname"]):
        if "parent" in nd:
            node.parent = created.get(nd["parent"], (None, None))[1]
        if "paired_output" in nd:
            out_node = created.get(nd["paired_output"], (None, None))[1]
            if out_node:
                node.pair_with_output(out_node)

        for k, v in nd.get("props", {}).items():
            k = _long_prop_name(k)
            prop = node.bl_rna.properties.get(k)
            if not prop.is_readonly:
                if k == "location_absolute":
                    v = [v[0] + location_offset[0], v[1] + location_offset[1]]
                _set_prop_on_idblock(node, k, v)
            elif prop.type == 'COLLECTION':
                collection = getattr(node, k)
                new_params = collection.bl_rna.functions['new'].parameters
                collection.clear()
                for item in v:
                    params = []
                    used_keys = set()
                    # Match properties to constructor parameters
                    for p in new_params:
                        # NodeGeometryCaptureAttributeItems.new accepts a socket type,
                        # but NodeGeometryCaptureAttributeItem stores an attribute type
                        # (TODO: is this an API bug?)
                        if (collection.bl_rna.identifier == "NodeGeometryCaptureAttributeItems"
                            and p.identifier == "socket_type"):
                            key = "data_type"
                            np = _map_attribute_to_socket_type(item.get(key))
                        else:
                            key = p.identifier
                            np = item.get(key)
                        if not np:
                            break
                        params.append(np)
                        used_keys.add(key)

                    obj = collection.new(*params)
                    # Set all properties not set by the constructor
                    for key, value in item.items():
                        if key not in used_keys:
                            setattr(obj, key, value)

    def _iterate_sockets(node, nd, key):
        for i, sd in nd.get(key, {}).items():
            i = int(i)
            if i >= len(getattr(node, key)):
                continue
            socket = getattr(node, key)[i]
            if socket is None:
                continue
            yield sd, socket

    # Create links
    for nd, node in created.values():
        for sd, from_socket in _iterate_sockets(node, nd, "inputs"):
            for from_name, socket_index in sd.get("links", ()):
                other = created.get(from_name)
                if other is None:
                    continue
                if socket_index >= len(other[1].outputs):
                    continue
                to_socket = other[1].outputs[socket_index]
                # Should not happen, but don't connect virtual sockets
                if isinstance(from_socket, bpy.types.NodeSocketVirtual):
                    continue
                if isinstance(to_socket, bpy.types.NodeSocketVirtual):
                    continue
                target_tree.links.new(from_socket, to_socket)

    # Set socket values
    for nd, node in sorted(created.values(), key=lambda x: "Output" not in x[0]["bl_idname"]):
        for socket_dir in ("inputs", "outputs"):
            for sd, socket in _iterate_sockets(node, nd, socket_dir):
                # Sort "socket_type" to the front, so that any type change happens first
                for k, v in sorted(sd.items(), key=lambda x: x[0] != "socket_type"):
                    k = _long_prop_name(k)
                    if k in ("name", "links"):
                        continue
                    _set_prop_on_idblock(socket, k, v)

def _has_equal_interface(tree_dict, node_group):
    for i, item in enumerate(tree_dict["interface"]["items_tree"]):
        try:
            id_item = node_group.interface.items_tree[i]
        except IndexError:
            return False

        for k, v in item.items():
            k = _long_prop_name(k)
            if not hasattr(id_item, k):
                return False
            id_v = getattr(id_item, k)
            try:
                if isinstance(v, float):
                    # Compare in single precision (TODO: use epsilon?)
                    v = numpy.float32(v)
                    id_v = numpy.float32(v)
                if isinstance(v, list):
                    id_v = list(id_v)
                    if v and isinstance(v[0], float):
                        v = [numpy.float32(x) for x in v]
                        id_v = [numpy.float32(x) for x in id_v]
            except ValueError:
                return False
            if k == "parent":
                id_v = id_v.index
            if v != id_v:
                return False
    return True

def dict_to_nodes(target_tree, target_location, nodes_dict, reuse_existing=True):
    trees = {}
    raw_trees = nodes_dict.get("node_trees", {})
    for name, td in raw_trees.items():
        # Try to find existing node group
        node_group = bpy.data.node_groups.get(name)
        # Or recreate the node group on these conditions
        if (not reuse_existing or
            not node_group or
            not nodes_dict["type"] == node_group.type or
            not _has_equal_interface(td, node_group)):

            node_group = bpy.data.node_groups.new(name, target_tree.bl_idname)
            for k, v in td.get("props", {}).items():
                k = _long_prop_name(k)
                setattr(node_group, k, v)

            new_sockets = []
            for sd in td["interface"].get("items_tree", []):
                socket_name = sd.get("name", "")
                in_out = sd.get("in_out", "PANEL")
                description = sd.get("description", "")
                if in_out == "PANEL":
                    s = node_group.interface.new_panel(
                        socket_name,
                        description=description,
                        default_closed=sd.get("default_closed")
                    )
                else:
                    s = node_group.interface.new_socket(
                        socket_name,
                        description=description,
                        in_out=in_out,
                        socket_type=sd.get("socket_type", "NodeSocketFloat")
                    )
                parent_index = sd.get("parent")
                if parent_index is not None:
                    node_group.interface.move_to_parent(s, new_sockets[parent_index][0], len(new_sockets))
                if "dimensions" in sd and hasattr(s, "dimensions"):
                    s.dimensions = sd["dimensions"]
                    # Dimension changes REPLACE the socket object, refresh our reference
                    # (NB: This seems like *terrible* API design?)
                    s = node_group.interface.items_tree[s.index]

                new_sockets.append((s, sd))

            # Fill the node tree
            _create_nodes(node_group, (0.0, 0.0), td["nodes"], trees, raw_trees)

            # Set other socket properties only after nodes have been created, to propagate menu items
            for s, sd in new_sockets:
                in_out = sd.get("in_out", "PANEL")
                if in_out == "PANEL":
                    # Panels have no other properties
                    continue
                for k, v in sorted(sd.items()):
                    k = _long_prop_name(k)
                    # These should already be set above
                    if k in {"name", "description", "in_out", "socket_type", "parent", "dimensions"}:
                        continue
                    setattr(s, k, v)

        trees[name] = node_group

    if target_location is not None:
        minmax = None
        for nd in nodes_dict["nodes"]:
            location = nd.get("props", {}).get(_short_prop_name("location_absolute"))
            if not location:
                continue
            if minmax is None:
                minmax = tuple(location), tuple(location)
                continue
            minmax = (
                (min(minmax[0][0], location[0]), min(minmax[0][1], location[1])),
                (max(minmax[1][0], location[0]), max(minmax[1][1], location[1]))
            )
        center = (0.5*(minmax[0][0] + minmax[1][0]), 0.5*(minmax[0][1] + minmax[1][1]))
        location_offset = (target_location[0] - center[0], target_location[1] - center[1])
    else:
        location_offset = (0.0, 0.0)

    # Create the root nodes
    _create_nodes(target_tree, location_offset, nodes_dict["nodes"], trees, raw_trees)


def dumps_compact(obj, indent=2, max_inline=90):
    """
    A version of json.dumps that defaults to pretty-printing with indents, but
    tries to keep elements on the same line if they are short
    """
    def render(x, level=0):
        space = " " * (indent * level)
        space_inner = " " * (indent * (level + 1))

        if isinstance(x, dict):
            if not x:
                return "{}"
            items = [f'"{k}": {render(v, level + 1)}' for k, v in x.items()]
            one_line = "{" + ", ".join(items) + "}"
            if len(one_line) <= max_inline:
                return one_line
            lines = [space_inner + item for item in items]
            return "{\n" + ",\n".join(lines) + "\n" + space + "}"

        if isinstance(x, list):
            if not x:
                return "[]"
            items = [render(v, level + 1) for v in x]
            one_line = "[" + ", ".join(items) + "]"
            if len(one_line) <= max_inline:
                return one_line
            lines = [space_inner + item for item in items]
            return "[\n" + ",\n".join(lines) + "\n" + space + "]"

        return json.dumps(x)

    return render(obj)

