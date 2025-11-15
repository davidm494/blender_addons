This repository contains these [Blender](https://www.blender.org) extensions:

- [Copy Paste Nodes](#copy-paste-nodes)
- [Auto Track Weights](#auto-track-weights)

## Installation

The preferred method for installation is via the [Blender Extensions](https://extensions.blender.org/) platform.

# Copy Paste Nodes

**Copy Paste Nodes** allows to copy and paste nodes in all node editors as JSON text. Some of the possible usecases are:

- copy between different open blender instances and versions
- share node trees online, without rebuilding from screenshots, where .blend files are not easy to share
- check changes between node tree versions by comparing the difference in the JSON output

NOTE: The structure of the generated JSON is NOT finalized, this should be considered in an alpha state. I hope to gather feedback on the exact fields that are necessary for the serialization to be useful.

The code tries to keep the generated JSON short, only keeping fields that are not default. This results in almost human-readable output, but it is very easy to trigger exceptions if this output is edited by hand. Quite a bit more error checking should be done in future versions.

The stored structure and property names are mostly mirroring the internal structure of the node trees. One exception is that `default_value` and `location_absolute` have been renamed to `_val` and `_loc`. They occur in almost every node, and the long names make the output much more verbose and the actual useful information less readable.

## Usage

Two new keyboard shortcuts are added in all **Node Editors**: CTRL+ALT+C and CTRL+ALT+V (CMD on macos). These will copy/paste nodes as text to the system clipboard instead of the internal clipboard used by CTRL+C/CTRL+V.


# Auto Track Weights

**Auto Track Weights** automatically modulates the influence weight of tracking markers in Motion Tracking. It helps improve solver stability by fading marker weights near the edges of tracked regions and across gaps, reducing abrupt jumps in the reconstructed motion.

## Usage

In the **Movie Clip Editor** select some or all tracking markers. The default shortcut is ALT+W (for weights), alternatively there is a **Set Track Weights** button in the **Track** tab of the sidebar. After running the operator you can adjust the **Falloff Frames** in the operator properties.

---

This is inspired by the **Fade Marker Weights** addon by Sebastian König, but is compatible with blender versions newer than 2.79 and is rewritten to fix a couple of issues. Improved are handling of gaps in tracks, clips with frame offsets and edge cases at start and end points of clips. Additionally it also handles object tracks, not just camera tracks.
