import maya.cmds as cmds

def CreateUI(*arr):
    """Open the ordered, multi-vertex skin-weight transfer window."""

    window_name = "NLTA_SkinWeightTransferByOrder"
    if cmds.window(window_name, exists=True):
        cmds.deleteUI(window_name)

    # Enable BEFORE choosing items so orderedSelection is reliable.
    cmds.selectPref(trackSelectionOrder=True)

    groups = {
        "source_joints": [],
        "source_vertices": [],
        "target_joints": [],
        "target_vertices": [],
    }
    ui = {}
    epsilon = 1e-7

    def set_status(message):
        cmds.text(ui["status"], edit=True, label=message)

    def refresh():
        for key, objects in groups.items():
            control = ui[key + "_list"]
            cmds.textScrollList(control, edit=True, removeAll=True)
            if objects:
                cmds.textScrollList(
                    control,
                    edit=True,
                    append=["{:02d}. {}".format(i, item.rsplit("|", 1)[-1])
                            for i, item in enumerate(objects, start=1)]
                )
            cmds.text(ui[key + "_count"], edit=True,
                      label="{} selected".format(len(objects)))

    def capture(key, *_):
        selected = cmds.ls(orderedSelection=True, flatten=True, long=True) or []
        if not selected:
            cmds.warning("Select some joints or vertices first.")
            return
        want_vertices = key.endswith("vertices")
        for item in selected:
            is_vertex = bool(re.search(r"\.vtx\[\d+\]$", item))
            if want_vertices:
                if not is_vertex:
                    cmds.warning("Only polygon vertices are allowed in this group.")
                    return
            elif is_vertex or cmds.nodeType(item) != "joint":
                cmds.warning("Only joints are allowed in this group.")
                return
        if len(selected) != len(set(selected)):
            cmds.warning("Repeated entries within one group are not supported.")
            return
        groups[key] = list(selected)
        refresh()
        set_status("Captured {} item(s) for {}.".format(len(selected), key))

    def clear(key, *_):
        groups[key] = []
        refresh()
        set_status("Cleared {}.".format(key))

    def clear_all(*_):
        for key in groups:
            groups[key] = []
        refresh()
        set_status("All groups cleared.")

    def get_skin(vertex, cache):
        mesh = vertex.split(".vtx[", 1)[0]
        if mesh not in cache:
            history = cmds.listHistory(mesh) or []
            skins = list(dict.fromkeys(cmds.ls(history, type="skinCluster") or []))
            if len(skins) != 1:
                raise ValueError("Expected one skinCluster for {} (found {}).".format(
                    mesh, len(skins)))
            cache[mesh] = skins[0]
        return cache[mesh]

    def get_influences(skin, cache):
        if skin not in cache:
            original = cmds.skinCluster(skin, query=True, influence=True) or []
            cache[skin] = cmds.ls(original, long=True) or []
        return cache[skin]

    def read_weight(skin, vertex, joint):
        result = cmds.skinPercent(skin, vertex, query=True, transform=joint)
        if isinstance(result, (tuple, list)):
            result = result[0] if result else 0.0
        return float(result or 0.0)

    def is_locked(joint):
        return (cmds.attributeQuery("liw", node=joint, exists=True)
                and bool(cmds.getAttr(joint + ".liw")))

    def run_transfer(mode, *_):
        # The clicked button supplies the mode directly; no optionMenu needed.
        source_joints = groups["source_joints"][:]
        source_vertices = groups["source_vertices"][:]
        target_joints = groups["target_joints"][:]
        target_vertices = groups["target_vertices"][:]

        if not all((source_joints, source_vertices, target_joints, target_vertices)):
            cmds.warning("Capture all four groups first.")
            return
        if len(source_joints) != len(target_joints):
            cmds.warning("Source and target must have the same number of joints.")
            return
        if len(source_vertices) not in (1, len(target_vertices)):
            cmds.warning("Use one source vertex, or matching source/target vertex counts.")
            return

        # Do ALL reads and validation before performing any edits. This also
        # handles transfers in which a target vertex is another pair's source.
        try:
            skin_cache = {}
            influence_cache = {}
            plans = []
            for i, target_vertex in enumerate(target_vertices):
                source_vertex = source_vertices[0] if len(source_vertices) == 1 else source_vertices[i]
                source_skin = get_skin(source_vertex, skin_cache)
                target_skin = get_skin(target_vertex, skin_cache)
                source_influences = set(get_influences(source_skin, influence_cache))
                target_influences = get_influences(target_skin, influence_cache)
                target_set = set(target_joints)

                if any(j not in source_influences for j in source_joints):
                    raise ValueError("Source joint missing from skinCluster: {}".format(source_skin))
                if any(j not in target_influences for j in target_joints):
                    raise ValueError("Target joint missing from skinCluster: {}".format(target_skin))
                if any(is_locked(j) for j in target_joints):
                    raise ValueError("Unlock Hold Weights on the target joints before transfer.")

                source_weights = [read_weight(source_skin, source_vertex, j)
                                  for j in source_joints]
                total_source = sum(source_weights)
                if total_source <= epsilon:
                    raise ValueError("Selected source joints have zero total weight on {}".format(
                        source_vertex))
                ratios = [w / total_source for w in source_weights]
                other_joints = [j for j in target_influences if j not in target_set]
                other_weights = {j: read_weight(target_skin, target_vertex, j)
                                 for j in other_joints}

                if mode == "REPLACE":
                    for joint, weight in other_weights.items():
                        if weight > epsilon and is_locked(joint):
                            raise ValueError("Locked joint {} has nonzero weight on {}".format(
                                joint, target_vertex))
                    available = 1.0
                    final_other = {}
                else:
                    other_sum = sum(other_weights.values())
                    if other_sum > 1.0 + epsilon:
                        raise ValueError("Other weights exceed 1.0 on {}".format(target_vertex))
                    available = max(0.0, 1.0 - other_sum)
                    if available <= epsilon:
                        raise ValueError("No free weight left on {} in PRESERVE mode.".format(
                            target_vertex))
                    final_other = other_weights

                new_weights = [available * ratio for ratio in ratios]

                max_attr = target_skin + ".maintainMaxInfluences"
                if cmds.objExists(max_attr) and cmds.getAttr(max_attr):
                    allowed = int(cmds.getAttr(target_skin + ".maxInfluences"))
                    count = (sum(w > epsilon for w in new_weights)
                             + sum(w > epsilon for w in final_other.values()))
                    if count > allowed:
                        raise ValueError(
                            "{} needs {} active influences, but Max Influences is {}.".format(
                                target_vertex, count, allowed))

                plans.append((target_skin, target_vertex,
                              list(zip(target_joints, new_weights)), final_other))

        except (ValueError, RuntimeError) as error:
            set_status("Validation failed - see Script Editor.")
            cmds.warning("Skin Transfer: {}".format(error))
            return

        began_write = False
        error = None
        cmds.undoInfo(openChunk=True, chunkName="Skin Weight Transfer By Order")
        try:
            for skin, vertex, pairs, other_expected in plans:
                began_write = True
                cmds.skinPercent(
                    skin, vertex,
                    transformValue=pairs,
                    zeroRemainingInfluences=(mode == "REPLACE"),
                    normalize=False
                )
                # Confirm Maya did not silently alter weights.
                for joint, expected in pairs:
                    if abs(read_weight(skin, vertex, joint) - expected) > 1e-4:
                        raise RuntimeError("Weight mismatch on {} / {}".format(vertex, joint))
                for joint, expected in other_expected.items():
                    if abs(read_weight(skin, vertex, joint) - expected) > 1e-4:
                        raise RuntimeError("Other influence changed on {} / {}".format(
                            vertex, joint))
        except Exception as exc:
            error = exc
        finally:
            cmds.undoInfo(closeChunk=True)

        if error is not None:
            if began_write:
                cmds.undo()  # Roll back the whole undo chunk on any failure.
            set_status("Transfer failed and was undone - see Script Editor.")
            cmds.warning("Skin Transfer rolled back: {}".format(error))
            return

        set_status("DONE - {} vertex pair(s), {} joint pair(s), {}.".format(
            len(plans), len(source_joints), mode))
        print("Skin Weight Transfer complete: {} vertices, {} joint pairs, {}".format(
            len(plans), len(source_joints), mode))
        for a, b in zip(source_joints, target_joints):
            print("  {} -> {}".format(a, b))

    # -------------------- UI --------------------
    window = cmds.window(
        window_name,
        title="Skin Weight Transfer By Order",
        sizeable=True,
        widthHeight=(740, 590)
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=9)
    cmds.text(
        label="Capture each group in order. Joint and vertex pairing follows list order.",
        align="center", height=28
    )

    # 2 columns x 2 rows:
    # SOURCE JOINTS   | SOURCE VERTICES
    # TARGET JOINTS   | TARGET VERTICES
    cmds.rowColumnLayout(
        numberOfColumns=2,
        columnWidth=[(1, 354), (2, 354)],
        columnSpacing=[(1, 6), (2, 6)],
        rowSpacing=[(1, 8), (2, 8)]
    )

    blocks = [
        ("source_joints", "1 - SOURCE JOINTS"),
        ("source_vertices", "2 - SOURCE VERTICES"),
        ("target_joints", "3 - TARGET JOINTS"),
        ("target_vertices", "4 - TARGET VERTICES"),
    ]

    for key, title in blocks:
        cmds.frameLayout(
            label=title,
            collapsable=False,
            marginWidth=7,
            marginHeight=6
        )
        cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        cmds.rowLayout(
            numberOfColumns=3,
            columnWidth3=(150, 55, 120),
            columnAttach=[(1, "left", 0), (2, "left", 0), (3, "left", 5)]
        )
        cmds.button(
            label="Capture Selection", width=148, height=27,
            command=lambda *a, k=key: capture(k)
        )
        cmds.button(
            label="Clear", width=53, height=27,
            command=lambda *a, k=key: clear(k)
        )
        ui[key + "_count"] = cmds.text(label="0 selected", align="left")
        cmds.setParent("..")  # rowLayout
        ui[key + "_list"] = cmds.textScrollList(
            allowMultiSelection=False, height=115
        )
        cmds.setParent("..")  # columnLayout
        cmds.setParent("..")  # frameLayout

    cmds.setParent("..")  # 2-column rowColumnLayout

    # Mode selection is now one-click: two independent buttons.
    cmds.rowLayout(
        numberOfColumns=2,
        columnWidth2=(355, 355),
        columnAttach=[(1, "both", 0), (2, "both", 6)]
    )
    cmds.button(
        label="TRANSFER - REPLACE",
        width=348,
        height=42,
        backgroundColor=(0.23, 0.43, 0.33),
        annotation="Replace all other target influences and distribute 100% of weight.",
        command=lambda *_: run_transfer("REPLACE")
    )
    cmds.button(
        label="TRANSFER - PRESERVE",
        width=348,
        height=42,
        backgroundColor=(0.29, 0.39, 0.51),
        annotation="Keep other target influences and distribute only the remaining weight.",
        command=lambda *_: run_transfer("PRESERVE")
    )
    cmds.setParent("..")  # rowLayout

    cmds.button(
        label="Clear All Captured Groups", height=27,
        command=clear_all
    )
    ui["status"] = cmds.text(
        label="Ready. Select items, then capture each group.",
        align="left", height=28
    )
    cmds.text(
        label="Vertices: N to N by order, or 1 source to N targets.",
        align="center"
    )
    cmds.text(
        label="REPLACE: 100% target joints   |   PRESERVE: retain other influences",
        align="center"
    )
    cmds.showWindow(window)
    refresh()