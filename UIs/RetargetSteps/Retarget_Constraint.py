"""Build live constraints directly or through an optional aligned extra joint."""
import re
import maya.cmds as cmds
import NLTA_RetargetV2 as rt

LABEL = "Constraint"


def PairData(pair):
    return {"from": str(pair.get("from") or "").strip(),
            "to": str(pair.get("to") or "").strip(),
            "translate": bool(pair.get("translate", False)),
            "rotate": bool(pair.get("rotate", True)),
            "scale": bool(pair.get("scale", False)),
            "mirror": bool(pair.get("mirror", False))}


def DefaultSetting():
    return {"from_role": "REF", "to_role": "Rig", "maintain_offset": True,
            "use_extra_joint": True, "pairs": [PairData({})]}


def NormalizeSettings(settings):
    # Older UI accidentally stored the edited Pair list in to_role,
    # leaving pairs stale. Recover the latest edited list, including [].
    rows = settings.get("to_role")
    if not isinstance(rows, list):
        rows = settings.get("pairs", [PairData({})])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid Constraint Pair data.")
    from_role = settings.get("from_role", "REF")
    to_role = settings.get("to_role", "Rig")
    if isinstance(to_role, list):
        to_role = "Rig"  # Recover legacy misplaced Pair list.
    if from_role not in ("Rig", "Anim", "REF") or to_role not in ("Rig", "Anim", "REF"):
        raise ValueError("Constraint namespaces must be Rig, Anim or REF.")
    return {"from_role": from_role, "to_role": to_role,
            "maintain_offset": bool(settings.get("maintain_offset", True)),
            "use_extra_joint": bool(settings.get("use_extra_joint", True)),
            "pairs": [PairData(row) for row in rows]}


def Fields():
    return [("Constraint Pairs", "pairs", "constraint_pairs")]


def _namespaces(context, from_role="REF", to_role="Rig"):
    refs = context.get("reference_namespaces") or {}

    def namespace(role):
        if role == "REF":
            value = refs.get("reference_pose") or context.get("reference_pose_namespace")
            if context.get("reference_pose_loaded") is False:
                raise ValueError("Constraint requires a Reference Pose for the selected REF role.")
        elif role == "Anim":
            value = refs.get("old_animations") or context.get("source_namespace_animation")
        elif role == "Rig":
            value = refs.get("new_rig") or context.get("target_namespace")
        else:
            raise ValueError("Invalid Constraint namespace role: " + str(role))
        if not value:
            raise ValueError("Constraint namespace is unavailable: " + role)
        return str(value).strip(":")

    return namespace(from_role), namespace(to_role)


def _resolve(namespace, name):
    leaf = rt.leaf(name)
    if not leaf:
        raise ValueError("Constraint requires an object name in " + namespace)
    # Absolute namespace lookup avoids Maya's current namespace and any
    # stale aliases or similarly named objects in REF / Anim / Rig.
    qualified = ":" + namespace + ":" + leaf
    matches = cmds.ls(qualified, long=True, objectsOnly=True) or []
    matches = [node for node in dict.fromkeys(matches)
               if node.split("|")[-1].lstrip(":") == qualified.lstrip(":")
               and cmds.nodeType(node) in ("joint", "transform")]
    if len(matches) != 1:
        raise ValueError("Constraint: expected one object at {}, found {}".format(
            qualified, len(matches)))
    return matches[0]


def _build_extra(source, target, pair, maintain_offset=True):
    namespace = source.split("|")[-1].rpartition(":")[0]
    name = ":" + (namespace + ":" if namespace else "") + rt.leaf(target) + "_extraJoint"
    joint = cmds.createNode("joint", name=name, skipSelect=True)
    cmds.setAttr(joint + ".segmentScaleCompensate", False)
    match = target if maintain_offset else source
    cmds.delete(cmds.parentConstraint(match, joint, maintainOffset=False))
    if pair["scale"]:
        cmds.delete(cmds.scaleConstraint(match, joint, maintainOffset=False))
    joint = cmds.parent(joint, source, absolute=True)[0]
    joint = cmds.ls(joint, long=True)[0]
    cmds.makeIdentity(joint, apply=True, translate=False, rotate=True, scale=False)
    return joint


def _connect(extra, target, pair, maintain_offset=True):
    nodes = []
    if pair["translate"] and pair["rotate"]:
        nodes.extend(cmds.parentConstraint(extra, target, maintainOffset=maintain_offset))
    elif pair["translate"]:
        nodes.extend(cmds.pointConstraint(extra, target, maintainOffset=maintain_offset))
    elif pair["rotate"]:
        nodes.extend(cmds.orientConstraint(extra, target, maintainOffset=maintain_offset))
    if pair["scale"]:
        nodes.extend(cmds.scaleConstraint(extra, target, maintainOffset=maintain_offset))
    return nodes


def _mirror_name(name):
    """Swap explicit side tokens without changing unrelated letters."""
    swaps = {"L": "R", "R": "L", "l": "r", "r": "l",
             "Left": "Right", "Right": "Left",
             "left": "right", "right": "left",
             "LEFT": "RIGHT", "RIGHT": "LEFT"}
    patterns = (
        r"(?<=FBXASC032)[LR](?=FBXASC032)",
        r"(?<![A-Za-z0-9])(?:Left|Right|left|right|LEFT|RIGHT|L|R|l|r)(?![A-Za-z0-9])",
        r"^(?:Left|Right)(?=[A-Z0-9])",
        r"(?:Left|Right)$",
    )
    for pattern in patterns:
        mirrored, count = re.subn(pattern, lambda match: swaps[match.group()], name)
        if count:
            return mirrored
    return name

def _expand_pairs(rows):
    pairs = []
    for index, row in enumerate(rows, 1):
        pair = PairData(row)
        if not any(pair[key] for key in ("translate", "rotate", "scale")):
            continue
        if not pair["from"] and not pair["to"]:
            continue  # Empty editor placeholder, not a mapping.
        if not pair["from"] or not pair["to"]:
            missing = "From" if not pair["from"] else "To"
            raise ValueError("Constraint Pair {}: missing {} object (From={!r}, To={!r})".format(
                index, missing, pair["from"], pair["to"]))
        pairs.append(pair)
    explicit = {rt.leaf(pair["to"]) for pair in pairs}
    generated = set()
    result = []
    for pair in pairs:
        result.append(pair)
        if not pair["mirror"]:
            continue
        target = rt.leaf(pair["to"])
        opposite = _mirror_name(target)
        if opposite == target or opposite in explicit or opposite in generated:
            continue
        source = rt.leaf(pair["from"])
        mirrored_source = _mirror_name(source)
        if mirrored_source == source:
            raise ValueError("Constraint Mirror needs a side token on From: " + source)
        result.append(dict(pair, **{"from": mirrored_source, "to": opposite, "mirror": False}))
        generated.add(opposite)
    return result


def MatchByName(settings, context):
    """Return only new, unique same-name joints/controllers for the current roles."""
    settings = NormalizeSettings(settings)
    source_ns, target_ns = _namespaces(context, settings["from_role"], settings["to_role"])
    if source_ns == target_ns:
        return []  # Same-name objects in the same namespace would constrain themselves.

    def candidates(namespace):
        names = {}
        for node in dict.fromkeys(rt.mapping_candidates(namespace)):
            qualified = node.split("|")[-1].lstrip(":")
            name = rt.leaf(node)
            if qualified != namespace + ":" + name or re.search(r"_extraJoint\d*$", name):
                continue
            names.setdefault(name, []).append(node)
        return {name: nodes[0] for name, nodes in names.items() if len(nodes) == 1}

    sources, targets = candidates(source_ns), candidates(target_ns)
    used = set()
    for pair in settings["pairs"]:
        source, target = rt.leaf(pair["from"]), rt.leaf(pair["to"])
        used.update((source, target))
        if pair["mirror"] and any(pair[key] for key in ("translate", "rotate", "scale")):
            if target and _mirror_name(target) != target:
                used.update((_mirror_name(source), _mirror_name(target)))
    names = sorted((sources.keys() & targets.keys()) - used,
                   key=lambda name: (sources[name].count("|"), name))
    return [PairData({"from": name, "to": name}) for name in names]


def Run(settings, context):
    settings = NormalizeSettings(settings)
    from_role, to_role = settings["from_role"], settings["to_role"]
    source_ns, target_ns = _namespaces(context, from_role, to_role)
    pending = []
    targets = set()
    existing = {entry["target"] for entry in context.get("constraint_pairs", [])
                if any(cmds.objExists(node) for node in entry["constraints"])}
    for pair in _expand_pairs(settings.get("pairs", [])):
        source = _resolve(source_ns, pair["from"])
        target = _resolve(target_ns, pair["to"])
        if source == target or source.startswith(target + "|"):
            raise ValueError("Constraint would create a cycle: {} -> {}".format(source, target))
        if target in targets or target in existing:
            raise ValueError("Constraint already configured for: " + target)
        targets.add(target)
        pending.append((pair, source, target))

    # Prepare every helper in the initial pose before driving any target.
    prepared = [(pair, source, target,
                 _build_extra(source, target, pair, settings["maintain_offset"])
                 if settings["use_extra_joint"] else None)
                for pair, source, target in pending]
    entries = []
    print("[Constraint] From {}={} -> {}={}".format(from_role, source_ns, to_role, target_ns))
    for pair, source, target, extra in prepared:
        driver = extra or source
        print("[Constraint] From: {} | Driver: {} | To: {}".format(source, driver, target))
        constraints = _connect(driver, target, pair, settings["maintain_offset"])
        entries.append({"reference": source if from_role == "REF" else None,
                        "source_role": from_role, "source": source,
                        "target_role": to_role, "target": target, "extra_joint": extra,
                        "constraints": constraints,
                        "translate": pair["translate"], "rotate": pair["rotate"],
                        "scale": pair["scale"]})
    context.setdefault("constraint_pairs", []).extend(entries)
    if entries:
        context["baked"] = False
    return {"pairs": len(entries),
            "joints": [entry["extra_joint"] for entry in entries if entry["extra_joint"]],
            "constraints": sum(len(entry["constraints"]) for entry in entries)}
