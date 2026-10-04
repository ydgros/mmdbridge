#https://github.com/Uqbc9/mmdbridge
#Added blender_mmdbridge_import_30_to_42.py, which supports material imports
#Original Name:blender_mmdbridge_import_30_to_42.py
import bpy
import os
import re
from bpy.props import StringProperty, FloatProperty, EnumProperty
from bpy_extras.io_utils import ImportHelper

# MMDBridge writes abc in millimeter-ish scale; 0.08 is the value that matches
# mmd (blender import shrinks 0.08, blender export grows 12.5).
DEFAULT_MODEL_SCALE = 0.08

# mmd is 30 fps; 60 fps gives the same animation length with twice as many frames
SCENE_FPS_ITEMS = [
    ("30", "30 fps", "Frame rate of mmd"),
    ("60", "60 fps", "Twice as many frames for the same animation length"),
]
DEFAULT_SCENE_FPS = "30"

bl_info = {
    "name": "MMDBridge Alembic and Material Import",
    "author": "Kazuma Hatta",
    "version": (1, 3),
    "blender": (3, 0, 0),
    "location": "File > Import > MMDBridge Alembic and Material (.abc, .mtl)",
    "description": "Import Alembic files (.abc) and MMDBridge Materials (.mtl), with model scale and frame rate options",
    "category": "Import-Export",
}

class Mtl():
    def __init__(self):
        self.name = ""    
        self.textureMap = ""
        self.alphaMap = ""
        self.diffuse = [0.7, 0.7, 0.7, 1.0]
        self.specular = [0.0, 0.0, 0.0]
        self.ambient = [0.0, 0.0, 0.0]
        self.trans = 1.0
        self.power = 0.0
        self.lum = 1
        self.faceSize = 0
        self.isAccessory = False

def import_mtl(path, result, relation):
    current = None
    export_mode = 0
    
    with open(path, 'r', encoding="utf-8") as mtl:
        for line in mtl.readlines():
            words = line.split()
            if len(words) < 2:
                continue
            if "newmtl" in words[0]:
                if current is not None and current.name != "":
                    result[current.name] = current
                current = Mtl()
                current.name = str(words[1])
                
                nameSplits = current.name.split("_")
                if len(nameSplits) >= 3:
                    try:
                        objectNumber = int(nameSplits[1])
                        materialNumber = int(nameSplits[2])
                        
                        if objectNumber not in relation.keys():
                            relation[objectNumber] = []
                        
                        relation[objectNumber].append(materialNumber)
                    except ValueError:
                        print(f"Warning: Unable to parse object and material numbers from {current.name}")
                        continue

            if "Ka" == words[0]:
                current.ambient = [float(words[1]), float(words[2]), float(words[3])]
            elif "Kd" == words[0]:
                current.diffuse = [float(words[1]), float(words[2]), float(words[3]), current.diffuse[3]]
            elif "Ks" == words[0]:
                current.specular = [float(words[1]), float(words[2]), float(words[3])]
            elif "Ns" == words[0]:
                current.power = float(words[1])
            elif "d" == words[0]:
                current.trans = float(words[1])
                current.diffuse[3] = current.trans
            elif "map_Kd" == words[0]:
                current.textureMap = line.split(None, 1)[1].strip().strip('"')
            elif "map_d" == words[0]:
                current.alphaMap = line.split(None, 1)[1].strip().strip('"')
            elif "#" == words[0]:
                if words[1] == "face_size":
                    current.faceSize = int(words[2])
                elif words[1] == "is_accessory":
                    current.isAccessory = True
                elif words[1] == "mode":
                    export_mode = int(words[2])

    if current is not None and current.name != "":
        result[current.name] = current

    for rel in relation.values():
        rel.sort()

    return export_mode

def normalize_object_key(name):
    # Blender appends ".001" to names that are already used in the file
    name = re.sub(r"\.\d+$", "", name)
    # "mesh_0_material_1" / "xform_0_material_1" -> "0_1", "mesh_0" -> "0"
    for prefix in ("mesh_", "xform_"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    return name.replace("_material_", "_")


def find_materials_for_object(obj, mtlDict):
    # objects imported from an mmdbridge .abc are named "mesh_<buffer>_material_<material>"
    # (export mode 0/2/3) or "mesh_<buffer>" (export mode 1, one mesh per vertex buffer)
    names = []
    if obj.data is not None:
        names.append(obj.data.name)
    names.append(obj.name)
    parent = obj.parent
    while parent is not None:
        names.append(parent.name)
        parent = parent.parent

    for name in names:
        key = normalize_object_key(name)
        # export mode 0/2/3: one material per mesh
        if "material_" + key in mtlDict:
            return [mtlDict["material_" + key]]
        # export mode 1: the mesh holds all materials of its vertex buffer
        prefix = "material_" + key + "_"
        material_names = [n for n in mtlDict if n.startswith(prefix)]
        if material_names:
            material_names.sort(key=lambda n: int(n.rsplit("_", 1)[1]))
            return [mtlDict[n] for n in material_names]
    return []


def load_texture(base_path, file_name, image_dict):
    if not file_name:
        return None
    texture_file_path = os.path.normpath(bpy.path.abspath(os.path.join(base_path, file_name)))
    if texture_file_path in image_dict:
        return image_dict[texture_file_path]
    if not os.path.exists(texture_file_path):
        print(f"Warning: texture not found: {texture_file_path}")
        return None
    try:
        image = bpy.data.images.load(texture_file_path)
    except RuntimeError as error:
        print(f"Warning: unable to load texture {texture_file_path} ({error})")
        return None
    image_dict[texture_file_path] = image
    return image


def assign_material(base_path, mesh, mtlmat, image_dict):
    if mtlmat.name in bpy.data.materials:
        mat = bpy.data.materials[mtlmat.name]
    else:
        mat = bpy.data.materials.new(name=mtlmat.name)

    if not mat.use_nodes:
        mat.use_nodes = True

    if mat.name not in mesh.materials:
        mesh.materials.append(mat)

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    nodes.clear()

    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    material_output = nodes.new(type='ShaderNodeOutputMaterial')

    bsdf.location = (0, 0)
    material_output.location = (400, 0)

    links.new(bsdf.outputs['BSDF'], material_output.inputs['Surface'])

    bsdf.inputs['Base Color'].default_value = mtlmat.diffuse

    # Check Blender version and adjust specular input accordingly
    if bpy.app.version >= (4, 0, 0):
        # For Blender 4.0 and above
        if 'Specular IOR Level' in bsdf.inputs:
            bsdf.inputs['Specular IOR Level'].default_value = sum(mtlmat.specular) / 3
    else:
        # For Blender 3.6 and below
        if 'Specular' in bsdf.inputs:
            bsdf.inputs['Specular'].default_value = sum(mtlmat.specular) / 3

    bsdf.inputs['Roughness'].default_value = 1.0 - (mtlmat.power / 100)

    texture_image = load_texture(base_path, mtlmat.textureMap, image_dict)
    if texture_image:
        tex_image_node = nodes.new('ShaderNodeTexImage')
        tex_image_node.location = (-300, 0)
        tex_image_node.image = texture_image
        links.new(tex_image_node.outputs['Color'], bsdf.inputs['Base Color'])

    if mtlmat.trans < 1.0:
        bsdf.inputs['Alpha'].default_value = mtlmat.trans

        alpha_image = load_texture(base_path, mtlmat.alphaMap, image_dict)
        if alpha_image and alpha_image.channels >= 4:
            alpha_node = nodes.new('ShaderNodeTexImage')
            alpha_node.location = (-300, -320)
            alpha_node.image = alpha_image
            links.new(alpha_node.outputs['Alpha'], bsdf.inputs['Alpha'])

        # Blender 4.2 and above use surface_render_method, older versions use blend_method
        if hasattr(mat, 'blend_method'):
            mat.blend_method = 'BLEND'
        if hasattr(mat, 'surface_render_method'):
            mat.surface_render_method = 'BLENDED'

    return mat


def assign_materials_to_mesh(base_path, mesh, mtlmat_list, image_dict):
    mesh.materials.clear()
    for mtlmat in mtlmat_list:
        assign_material(base_path, mesh, mtlmat, image_dict)

    face_sizes = [mtlmat.faceSize for mtlmat in mtlmat_list]
    if len(mtlmat_list) > 1 and all(size > 0 for size in face_sizes) \
            and sum(face_sizes) <= len(mesh.polygons):
        # export mode 1: the faces of all materials are stored in material order
        face_offset = 0
        for index, face_size in enumerate(face_sizes):
            for polygon in mesh.polygons[face_offset:face_offset + face_size]:
                polygon.material_index = index
            face_offset += face_size
    else:
        for polygon in mesh.polygons:
            polygon.material_index = 0

def import_mmdbridge_material(filepath, context):
    image_dict = {}
    mtlDict = {}
    relationDict = {}
    import_mtl(filepath, mtlDict, relationDict)

    base_path, file_name = os.path.split(filepath)

    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        mtlmat_list = find_materials_for_object(obj, mtlDict)
        if not mtlmat_list:
            continue
        assign_materials_to_mesh(base_path, obj.data, mtlmat_list, image_dict)
        material_names = ", ".join(mtlmat.name for mtlmat in mtlmat_list)
        print(f"Assigned material {material_names} to object {obj.name}")

def import_alembic_and_mtl(filepath, context, model_scale=DEFAULT_MODEL_SCALE, scene_fps=DEFAULT_SCENE_FPS):
    # abc stores time in seconds and the importer converts it into frames with
    # the scene frame rate, so the frame rate has to be set before importing
    scene = bpy.context.scene
    scene.render.fps = int(scene_fps)
    scene.render.fps_base = 1.0

    # Create a new collection called "abc"
    abc_collection = bpy.data.collections.new("abc")
    bpy.context.scene.collection.children.link(abc_collection)

    # Import Alembic file (.abc)
    bpy.ops.wm.alembic_import(filepath=filepath, scale=model_scale)

    # Move all newly imported objects to the "abc" collection
    for obj in bpy.context.selected_objects:
        for collection in obj.users_collection:
            collection.objects.unlink(obj)
        abc_collection.objects.link(obj)

    # Clear all materials
    for obj in abc_collection.objects:
        if obj.type == 'MESH':
            obj.data.materials.clear()

    # Find .mtl file in the same directory
    base_path, file_name = os.path.split(filepath)
    mtl_file = os.path.join(base_path, file_name.replace(".abc", ".mtl"))
    
    if os.path.exists(mtl_file):
        # If corresponding .mtl file is found, import materials
        import_mmdbridge_material(mtl_file, context)
    else:
        print("Warning: .mtl file not found for Alembic file.")

class MMDBridgeAlembicImportOperator(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.mmdbridge_alembic_material"
    bl_label = "MMDBridge Alembic and Material Importer (.abc, .mtl)"
    
    filename_ext = ".abc"
    filter_glob: StringProperty(default="*.abc", options={'HIDDEN'})
    model_scale: FloatProperty(
        name="Scale",
        description="Size of the imported model (1.0 = no scaling, 0.08 = mmd scale)",
        default=DEFAULT_MODEL_SCALE,
        min=0.000001,
        soft_max=100.0,
    )
    scene_fps: EnumProperty(
        name="FPS",
        description="Frame rate of the scene; the abc time is converted into frames with this value",
        items=SCENE_FPS_ITEMS,
        default=DEFAULT_SCENE_FPS,
    )

    def execute(self, context):
        import_alembic_and_mtl(self.filepath, context, self.model_scale, self.scene_fps)
        return {'FINISHED'}

def menu_func_import(self, context):
    self.layout.operator(MMDBridgeAlembicImportOperator.bl_idname, text="MMDBridge Alembic and Material (.abc, .mtl)")

def register():
    bpy.utils.register_class(MMDBridgeAlembicImportOperator)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)

def unregister():
    bpy.utils.unregister_class(MMDBridgeAlembicImportOperator)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)

if __name__ == "__main__":
    register()