import mmdbridge
from mmdbridge import *
import mmdbridge_vmd
from mmdbridge_vmd import *

# export mode
# 0 = physics + ik
# 1 = physics only
# 2 = all (buggy)
#export_mode = 0
export_mode = 2

# bake the facial expressions (morphs) as face frames
export_morph = True

# show the export summary (morph and frame counts) when the export ends
show_summary = True

start_frame = get_start_frame()
end_frame = get_end_frame()

framenumber = get_frame_number()
if (framenumber == start_frame):
	messagebox("vmd export started")
	start_vmd_export("", export_mode, export_morph)

if (framenumber >= start_frame and framenumber <= end_frame):
	execute_vmd_export(framenumber)

if (framenumber == end_frame):
	if (show_summary):
		messagebox(get_vmd_export_summary())
	messagebox("vmd export ended at " + str(framenumber))
	end_vmd_export()
