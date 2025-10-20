# Auto Track Weights

**Auto Track Weights** is a Python extension for Blender that automatically modulates the influence weight of tracking markers in Motion Tracking. It helps improve solver stability by fading marker weights near the edges of tracked regions and across gaps, reducing abrupt jumps in the reconstructed motion.

---

## Usage

In the **Movie Clip Editor** select some or all tracking markers. The default shortcut is ALT+W (for weights), alternatively there is a **Set Track Weights** button in the **Track** tab of the sidebar. After running the operator, you can adjust the **Falloff Frames** in the operator properties.

---

## Installation

The preferred method for installation is via the blender extension platform https://extensions.blender.org/.

