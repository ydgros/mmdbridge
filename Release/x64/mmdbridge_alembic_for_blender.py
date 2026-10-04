import mmdbridge
from mmdbridge import *
import mmdbridge_abc
from mmdbridge_abc import *
import os
import shutil

# settings
export_normals = True
export_uvs = True
is_use_euler_rotation_for_camera = True
is_use_ogawa = True

# 0 = create buffer every marerials, fixed vertex index for face
# 1 = create buffer every objects, original vertex index for face
# 2 = create buffer every marerials, direct vertex index for face
export_mode = 0



def export_mtl(mtlpath, texture_export_dir, export_mode):
	if os.path.isfile(mtlpath):
		os.remove(mtlpath)

	mtlfile = open(mtlpath, 'a', encoding = "utf-8")

	mtlfile.write("# mode "+str(export_mode)+"\n")

	for buf in range(get_vertex_buffer_size()):
		for mat in range(get_material_size(buf)):
			material_name = "material_" + str(buf) + "_" + str(mat)
			mtlfile.write("newmtl "+material_name+"\n")

			if is_accessory(buf):
				mtlfile.write("# is_accessory"+"\n")

			if export_mode == 1:
				face_size = get_face_size(buf, mat)
				mtlfile.write("# face_size "+str(face_size)+"\n")

			ambient = get_ambient(buf, mat)
			diffuse = get_diffuse(buf, mat)
			specular = get_specular(buf, mat)
			emissive = get_emissive(buf, mat)
			power = get_power(buf, mat)
			texture = get_texture(buf, mat)

			mtlfile.write("Ka "+str(ambient[0])+" "+str(ambient[1])+" "+str(ambient[2])+"\n")
			if diffuse[0] < 0 or diffuse[1] < 0 or diffuse[2] < 0:
				diffuse[0] = 1
				diffuse[1] = 1
				diffuse[2] = 1

			if specular[0] < 0 or specular[1] < 0 or specular[2] < 0:
				specular[0] = 0
				specular[1] = 0
				specular[2] = 0

			mtlfile.write("Kd "+str(diffuse[0])+" "+str(diffuse[1])+" "+str(diffuse[2])+"\n")
			mtlfile.write("Ks "+str(specular[0])+" "+str(specular[1])+" "+str(specular[2])+"\n")
			if (diffuse[3] < 1):
				mtlfile.write("d "+str(diffuse[3])+"\n")				
			mtlfile.write("Ns "+str(power)+"\n")
			#mtlfile.write("Ni 1.33\n")
			# lum = 1 no specular highlights, lum = 2 light normaly
			mtlfile.write("lum 1\n")
			if len(texture) > 0:
				texname = os.path.basename(texture.replace("\\", "/"))
				if os.path.isfile(texture):
					destination = os.path.join(texture_export_dir, texname)
					shutil.copy2(texture, destination)
					if os.path.isfile(destination):
					mtlfile.write("map_Kd "+texname+"\n")
					if (diffuse[3] < 1):
						mtlfile.write("map_d "+texname+"\n")

	mtlfile.close()


outpath = get_base_path().replace("\\", "/") + "out/"
mtlpath = outpath + "alembic_file.mtl"
texture_export_dir = outpath.replace("/", "\\")
start_frame = get_start_frame()
end_frame = get_end_frame()

framenumber = get_frame_number()
if (framenumber == start_frame):
	export_mtl(mtlpath, texture_export_dir, export_mode)
	copy_textures(mtlpath.replace("/", "\\"))
	start_alembic_export("", export_mode, export_normals, export_uvs, is_use_euler_rotation_for_camera, is_use_ogawa)

if (framenumber >= start_frame and framenumber <= end_frame):
	execute_alembic_export(framenumber)

if (framenumber == end_frame):
	end_alembic_export()
