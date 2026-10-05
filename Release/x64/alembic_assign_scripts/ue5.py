import unreal
from pathlib import Path
import shlex


class Mtl:
    def __init__(self):
        self.name = ""
        self.textureMap = ""
        self.alphaMap = ""
        self.diffuse = [0.7, 0.7, 0.7]
        self.specular = [0.0, 0.0, 0.0]
        self.ambient = [0.0, 0.0, 0.0]
        self.trans = 1.0
        self.power = 0.0
        self.lum = 1
        self.isAccessory = False


def import_mtl(path, result):
    current = None

    with open(path, "r", encoding="utf-8") as mtl:
        for line in mtl:
            words = shlex.split(line, comments=False)
            if not words:
                continue
            command = words[0]
            if command == "#":
                if current is not None and len(words) > 1 and words[1] == "is_accessory":
                    current.isAccessory = True
                continue
            if command == "newmtl":
                if current is not None and current.name:
                    result[current.name] = current
                current = Mtl()
                current.name = line.split(None, 1)[1].strip()
            elif current is not None and command in ("map_Kd", "map_d"):
                if len(words) < 2:
                    continue
                # MTL map options precede the filename; quoted filenames remain a single token.
                texture_path = words[-1]
                if command == "map_Kd":
                    current.textureMap = texture_path
                else:
                    current.alphaMap = texture_path
            elif current is not None and command in ("Ka", "Kd", "Ks") and len(words) >= 4:
                color = [float(value) for value in words[1:4]]
                if command == "Ka":
                    current.ambient = color
                elif command == "Kd":
                    current.diffuse = color
                else:
                    current.specular = color
            elif current is not None and command == "Ns" and len(words) >= 2:
                current.power = float(words[1])
            elif current is not None and command == "d" and len(words) >= 2:
                current.trans = float(words[1])

    if current != None and current.name != "":
        result[current.name] = current


def importReferencedTextures(mtlDict, mtlPath, assetsPath):
    texturePaths = {}
    for mtlData in mtlDict.values():
        for textureReference in (mtlData.textureMap, mtlData.alphaMap):
            if textureReference:
                texturePath = (mtlPath.parent / textureReference).resolve()
                texturePaths[str(texturePath).casefold()] = texturePath

    if not texturePaths:
        return {}

    tasks = []
    for texturePath in texturePaths.values():
        if not texturePath.is_file():
            raise FileNotFoundError(
                "Texture referenced by the MTL file was not found: {}".format(texturePath)
            )
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(texturePath))
        task.set_editor_property("destination_path", assetsPath)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("save", True)
        tasks.append(task)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
    importedTexDict = {}
    for task in tasks:
        importedPaths = task.get_editor_property("imported_object_paths")
        if not importedPaths:
            raise RuntimeError(
                "Unreal failed to import texture: {}".format(task.get_editor_property("filename"))
            )
        texture = unreal.EditorAssetLibrary.load_asset(importedPaths[0])
        if texture is None:
            raise RuntimeError("Could not load imported texture: {}".format(importedPaths[0]))
        importedTexDict[Path(task.get_editor_property("filename")).stem.casefold()] = texture
    return importedTexDict


def getMaterialKey(assetName):
    if assetName.startswith("M_"):
        return assetName[len("M_"):]
    if assetName.startswith("material_"):
        assetName = assetName[len("material_"):]
    if assetName.startswith("mesh_"):
        assetName = "material_" + assetName[len("mesh_"):]
    return assetName


def findMtlKey(slotName, mtlDict):
    if slotName in mtlDict:
        return slotName

    slotParts = slotName.split("_")
    if len(slotParts) >= 4 and slotParts[0] == "mesh" and slotParts[2] == "material":
        materialKey = "material_{}_{}".format(
            slotParts[1], "_".join(slotParts[3:])
        )
        if materialKey in mtlDict:
            return materialKey

    materialKey = getMaterialKey(slotName)
    if materialKey in mtlDict:
        return materialKey

    prefixedKey = "material_" + materialKey
    if prefixedKey in mtlDict:
        return prefixedKey

    return None


def ensureMaterialAssets(mtlDict, assetsPath, assetRegistry):
    materialAssets = assetRegistry.get_assets(
        unreal.ARFilter(package_paths=[assetsPath], class_names=["Material"])
    )
    materialsByKey = {}

    for assetData in materialAssets:
        assetName = str(assetData.asset_name)
        if assetName in mtlDict:
            materialsByKey[assetName] = assetData.get_asset()

    for assetData in materialAssets:
        assetName = str(assetData.asset_name)
        materialKey = getMaterialKey(assetName)
        if materialKey in mtlDict and materialKey not in materialsByKey:
            materialsByKey[materialKey] = assetData.get_asset()

    assetTools = unreal.AssetToolsHelpers.get_asset_tools()
    for materialKey in mtlDict:
        if materialKey not in materialsByKey:
            material = assetTools.create_asset(
                "M_" + materialKey,
                assetsPath,
                unreal.Material,
                unreal.MaterialFactoryNew()
            )
            if material is None:
                raise RuntimeError(
                    "Could not create material '{}' in '{}'.".format(
                        "M_" + materialKey, assetsPath
                    )
                )
            materialsByKey[materialKey] = material
    return materialsByKey


def ensureMaterialInstances(materialsByKey, assetsPath):
    assetTools = unreal.AssetToolsHelpers.get_asset_tools()
    instancesByKey = {}

    for materialKey, parentMaterial in materialsByKey.items():
        instanceName = "MI_" + materialKey
        instancePath = assetsPath.rstrip("/") + "/" + instanceName
        instance = unreal.EditorAssetLibrary.load_asset(instancePath)
        if instance is None:
            instance = assetTools.create_asset(
                instanceName,
                assetsPath,
                unreal.MaterialInstanceConstant,
                unreal.MaterialInstanceConstantFactoryNew()
            )
        if instance is None or instance.get_class().get_name() != "MaterialInstanceConstant":
            raise RuntimeError(
                "Could not create or load material instance '{}' in '{}'.".format(
                    instanceName, assetsPath
                )
            )

        instance.set_editor_property("parent", parentMaterial)
        unreal.EditorAssetLibrary.save_loaded_asset(instance)
        instancesByKey[materialKey] = instance
    return instancesByKey


def assignTexAndMat(mtlDict, importedTexDict, materialsByKey):
    ME = unreal.MaterialEditingLibrary
    for materialKey, mtlData in mtlDict.items():
        matInstance = materialsByKey[materialKey]
        if len(mtlData.textureMap) > 0:
            texKey = Path(mtlData.textureMap).stem.casefold()
            importedTex = importedTexDict.get(texKey)
            if importedTex is None:
                raise RuntimeError(
                    "Texture '{}' referenced by material '{}' was not imported.".format(
                        mtlData.textureMap, materialKey
                    )
                )
            colorTexNode = ME.get_material_property_input_node(matInstance, unreal.MaterialProperty.MP_BASE_COLOR)
            if colorTexNode is None:
                colorTexNode = ME.create_material_expression(
                    matInstance, unreal.MaterialExpressionTextureSample, -350, -200
                )
                ME.connect_material_property(colorTexNode, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
            colorTexNode.set_editor_property("texture", importedTex)

            if len(mtlData.alphaMap) > 0:
                alphaKey = Path(mtlData.alphaMap).stem.casefold()
                alphaTex = importedTexDict.get(alphaKey)
                if alphaTex is None:
                    raise RuntimeError(
                        "Alpha texture '{}' referenced by material '{}' was not imported.".format(
                            mtlData.alphaMap, materialKey
                        )
                    )
                alphaTexNode = ME.create_material_expression(
                    matInstance, unreal.MaterialExpressionTextureSample, -350, 100
                )
                alphaTexNode.set_editor_property("texture", alphaTex)
                ME.connect_material_property(alphaTexNode, "R", unreal.MaterialProperty.MP_OPACITY_MASK)
                matInstance.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        else:
            colorNode = ME.create_material_expression(
                matInstance, unreal.MaterialExpressionConstant4Vector, -350, -200
            )
            col = unreal.LinearColor()
            if mtlData.isAccessory:
                col.set_editor_property("r", pow(mtlData.diffuse[0] + 0.5 * mtlData.ambient[0], 2.2))
                col.set_editor_property("g", pow(mtlData.diffuse[1] + 0.5 * mtlData.ambient[1], 2.2))
                col.set_editor_property("b", pow(mtlData.diffuse[2] + 0.5 * mtlData.ambient[2], 2.2))
                col.set_editor_property("a", mtlData.trans)
            else:
                col.set_editor_property("r", pow(mtlData.diffuse[0], 2.2))
                col.set_editor_property("g", pow(mtlData.diffuse[1], 2.2))
                col.set_editor_property("b", pow(mtlData.diffuse[2], 2.2))
                col.set_editor_property("a", mtlData.trans)
            colorNode.constant = col
            ME.connect_material_property(colorNode, "", unreal.MaterialProperty.MP_BASE_COLOR)

        ME.layout_material_expressions(matInstance)
        ME.recompile_material(matInstance)
        unreal.EditorAssetLibrary.save_loaded_asset(matInstance)


def assignMaterialsToMesh(mesh, materialsByKey, mtlDict):
    if isinstance(mesh, unreal.SkeletalMesh):
        propertyName = "materials"
        meshType = "Skeletal Mesh"
    elif isinstance(mesh, unreal.StaticMesh):
        propertyName = "static_materials"
        meshType = "Static Mesh"
    else:
        raise TypeError("Unsupported model type for material assignment: {}".format(mesh.get_class().get_name()))

    meshMaterials = list(mesh.get_editor_property(propertyName))
    assignedSlots = []
    unmatchedSlots = []

    for index, meshMaterial in enumerate(meshMaterials):
        slotName = str(meshMaterial.get_editor_property("material_slot_name"))
        materialKey = findMtlKey(slotName, mtlDict)
        if materialKey is None:
            unmatchedSlots.append(slotName)
            continue
        meshMaterial.set_editor_property("material_interface", materialsByKey[materialKey])
        meshMaterials[index] = meshMaterial
        assignedSlots.append(slotName)

    if not assignedSlots:
        slotNames = ", ".join(
            str(meshMaterial.get_editor_property("material_slot_name"))
            for meshMaterial in meshMaterials
        ) or "<no material slots>"
        raise RuntimeError(
            "No material slots on {} '{}' matched the MTL material names. "
            "Model slots: {}. MTL materials: {}".format(
                meshType, mesh.get_name(), slotNames, ", ".join(mtlDict.keys())
            )
        )

    mesh.set_editor_property(propertyName, meshMaterials)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh)
    unreal.log("Assigned MTL materials to {} '{}': {}".format(
        meshType, mesh.get_name(), ", ".join(assignedSlots)
    ))
    if unmatchedSlots:
        unreal.log_warning(
            "No matching MTL material for {} slot(s) on '{}': {}".format(
                meshType, mesh.get_name(), ", ".join(unmatchedSlots)
            )
        )


def generateMtlDict(abcPath: Path):
    mtlPath = abcPath.with_suffix(".mtl")
    if not mtlPath.is_file():
        raise FileNotFoundError("Matching MTL file was not found: {}".format(mtlPath))
    mtlDict = {}
    import_mtl(mtlPath, mtlDict)
    print(mtlDict.keys())
    return mtlDict, mtlPath


def getPathToOriginalAbc(selectedAssets):
    geometryCaches = unreal.EditorFilterLibrary.by_class(selectedAssets, unreal.GeometryCache)
    staticMeshes = unreal.EditorFilterLibrary.by_class(selectedAssets, unreal.StaticMesh)
    skeletalMeshes = unreal.EditorFilterLibrary.by_class(selectedAssets, unreal.SkeletalMesh)
    importableAssets = list(geometryCaches) + list(staticMeshes) + list(skeletalMeshes)
    if not importableAssets:
        selection = ", ".join(
            "{} ({})".format(asset.get_name(), asset.get_class().get_name())
            for asset in selectedAssets
        ) or "no assets selected"
        raise RuntimeError(
            "Expected a selected Geometry Cache, Static Mesh, or Skeletal Mesh imported from an ABC file. "
            "Select the imported asset in the Content Browser and run the script again. "
            "Current selection: {}".format(selection)
        )

    assetImportData = importableAssets[0].get_editor_property("asset_import_data")
    sourceAbcPathStr = assetImportData.get_first_filename()
    if not sourceAbcPathStr or Path(sourceAbcPathStr).suffix.lower() != ".abc":
        raise RuntimeError(
            "The selected asset does not have an Alembic (.abc) source file: {}".format(
                sourceAbcPathStr or "<no source file>"
            )
        )

    abcPath = Path(sourceAbcPathStr)
    return abcPath


def main():
    selectedAssets = unreal.EditorUtilityLibrary.get_selected_assets()
    staticMeshes = list(unreal.EditorFilterLibrary.by_class(selectedAssets, unreal.StaticMesh))
    skeletalMeshes = list(unreal.EditorFilterLibrary.by_class(selectedAssets, unreal.SkeletalMesh))
    selectedMeshes = staticMeshes + skeletalMeshes
    if not selectedMeshes:
        selection = ", ".join(
            "{} ({})".format(asset.get_name(), asset.get_class().get_name())
            for asset in selectedAssets
        ) or "no assets selected"
        raise RuntimeError(
            "Select the Static Mesh or Skeletal Mesh that should receive the MTL materials. "
            "Current selection: {}".format(selection)
        )

    abcPath = getPathToOriginalAbc(selectedAssets)
    mtlDict, mtlPath = generateMtlDict(abcPath)

    assetsPath = unreal.EditorUtilityLibrary.get_current_content_browser_path()
    importedTexDict = importReferencedTextures(mtlDict, mtlPath, assetsPath)
    assetRegistry = unreal.AssetRegistryHelpers.get_asset_registry()
    materialsByKey = ensureMaterialAssets(mtlDict, assetsPath, assetRegistry)

    assignTexAndMat(mtlDict, importedTexDict, materialsByKey)
    for mesh in selectedMeshes:
        assignMaterialsToMesh(mesh, materialsByKey, mtlDict)


main()
