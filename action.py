import enum
import common
from common import findAndFetchText, protoFromName
import icon
import globals
from xml.etree import ElementTree as ET
from typing import Union, Dict, List, Callable, Any
import math

class ActionChargeType(enum.Enum):
    NONE = 0
    REGULAR = 1
    AUX = 2

STANDARD_SNARE = {"rate":0.85, "duration":2.0}


SUPPRESS_TARGET_TYPES = (
    "All",
    "LogicalTypeHandUnitsAttack",
    # The guardians mess up SoO's heal action.
    "GuardianSleeping",
    "GuardianSleepingTNA",
    "Football",
)

ACTION_TYPE_NAMES = {
    "HandAttack":"Melee Attack",
    "RangedAttack":"Ranged Attack",
    "AreaHeal":"Area Healing",
    "ChargedHandAttack":"Melee Special Attack",
    "ChargedRangedAttack":"Ranged Special Attack",
    "ChargedSpawn":"Unit Spawning",
    "BuildingAttack":"Melee Attack",
    "IdleDamageBonus":"Idle Stacking Damage Bonus",
    "DeathBoostDamageBonus":"Death Boost Damage Bonus",
    "PetrificationBonus":"Idle Stacking Armor Bonus",
    "OracleRevealEnemyUI":"Building Production Spying",
    "ArgivePatronageMyrmidon":"Passive Myrmidon Production",
    "RangedAttackMyth":"Anti-Myth Attack",
    "BeamAttack":"Beam Attack",
}


def actionDamageBonus(action: ET.Element):
    damageBonuses = action.findall("damagebonus")
    actionDamageBonuses = []
    for damageBonus in damageBonuses:
        targetType = damageBonus.attrib["type"]
        hasIcon = False
        iconNameMatch = globals.unitTypeData.get(targetType)
        multSize = float(damageBonus.text)
        # I'm just going to hardcode this.
        # Fenrir has x999 vs a bunch of silly things and I don't want it showing up
        if multSize < 900:
            if iconNameMatch is not None:
                iconName = findAndFetchText(iconNameMatch, "icon", None)
                if iconName is not None:
                    actionDamageBonuses.append(f"{icon.generalIcon(iconName)} x{multSize:0.3g}")
                    hasIcon = True
            if not hasIcon:
                actionDamageBonuses.append(f"x{multSize:0.3g} vs {common.getDisplayNameForProtoOrClass(targetType, plural=True)}")
    allydamagemultiplier = action.find("allydamagemultiplier")
    if allydamagemultiplier is not None:
        actionDamageBonuses.append(f"x{float(allydamagemultiplier.text):0.3g} to friendly targets")
    if actionDamageBonuses:
        return f"({', '.join(actionDamageBonuses)})"
    return ""
        
def actionDamageOnly(action: ET.Element, isDPS=False, hideRof=False, damageMultiplier=1.0):
    damages = []
    mult = damageMultiplier
    if isDPS:
        mult *= actionDPSMultiplier(action)
        
    for damage in action.findall("damage"):
        damageType = damage.attrib["type"]
        damageAmount = float(damage.text)
        damageAmount *= mult
        # This function has to support some very large numbers (eg bolt's 10000 divine) but also needs to handle
        # smaller noninteger values without giving pointless levels of precision
        intlength = len(str(round(damageAmount)))
        if intlength >= 3:
            damages.append(f"{icon.damageTypeIcon(damageType)} {round(damageAmount)}")
        else:
            damages.append(f"{icon.damageTypeIcon(damageType)} {damageAmount:0.3g}")
    if not isDPS:
        if not hideRof:
            damages.append(actionRof(action))
        damages.append(actionNumProjectiles(action))
    damages = [x for x in damages if len(x.strip()) > 0]
    final = " ".join(damages)
    
    return final

def actionNumProjectiles(action: ET.Element, format=True):
    numProjectiles = findAndFetchText(action, "displayednumberprojectiles", 1, int)
    if numProjectiles == 1:
        numProjectiles = findAndFetchText(action, "numberprojectiles", 1, int)
    if not format:
        return numProjectiles
    if numProjectiles == 1:
        return ""
    numProjectiles = int(numProjectiles)
    return f"{icon.iconNumProjectiles()} x{numProjectiles}"

def actionRof(action: ET.Element):
    rof = findAndFetchText(action, "rof", 1.0, float)
    return f"{icon.iconRof()} {rof:0.3g}"


def actionDPSMultiplier(action: ET.Element):
    rof = findAndFetchText(action, "rof", 1.0, float)
    numProjectiles = actionNumProjectiles(action, format=False)
    rof /= numProjectiles
    return 1.0/rof
    

def actionDamageFull(protoUnit: ET.Element, action: ET.Element, isDPS=False, hideArea=False, damageMultiplier=1.0, hideRof=False, hideRange=False, ignoreActive=False, hideDamageBonuses=False):
    components = [actionDamageOnly(action, isDPS, hideRof=hideRof, damageMultiplier=damageMultiplier)]
    if not hideArea:
        components.append(actionArea(action, True))
    if not hideDamageBonuses:
        components.append(actionDamageBonus(action))
    if not hideRange:
        components.append(actionRange(protoUnit, action, True))
    components = [component for component in components if len(component.strip()) > 0]
    
    dot = actionDamageOverTime(action)
    if len(dot) > 0:
        components.append(f"plus an additional {actionDamageOverTime(action, isDPS)}.")
    elif components:
        components[-1] += "."

    tactics = actionTactics(protoUnit, action)

    trackrating = findAndFetchText(action, "trackrating", None, float)
    if trackrating is None and tactics is not None:
        trackrating = findAndFetchText(tactics, "trackrating", None, float)
    if trackrating is not None and trackrating != 0.0:
        components.append(f"Track rating: {trackrating:0.3g}.")

    if protoUnit.find("./flag[.='AreaDamageConstant']") is not None and actionArea(action) != "":
        components.append("Has no falloff with distance.")
        
    
    for item in action, tactics:
        if item is None:
            continue
        scale = item.find("scalebycontainedunittype")
        if scale is not None:
            for rate in scale:
                components.append(f"Each garrisoned {common.getDisplayNameForProtoOrClass(rate.attrib['type'])} increases damage by {float(rate.text)*100:0.3g}%.")
            break
        
    components.append(actionOnHitNonDoTEffects(protoUnit, action, ignoreActive=ignoreActive))

    components = [x.strip() for x in components if len(x.strip()) > 0]
    final = " ".join(components)
    return final
    
def actionArea(action: ET.Element, useIcon=False):
    areaElement = action.find("damagearea")
    if areaElement is not None:
        rawArea = float(areaElement.text)
        if rawArea > 0.0:
            if useIcon:
                return f"{icon.iconAoe()} {rawArea:0.3g}"
            else:
                return f"{float(areaElement.text):0.3g}m"
    return ""
   
def rechargeRate(proto: ET.Element, action:ET.Element, chargeType: ActionChargeType, tech: Union[ET.Element, None]=None):
    techRechargeTime = techRechargeType = None
    if tech is not None:
        techRechargeType = tech.find("effects/effect[@subtype='RechargeType']")
        techRechargeTime = tech.find("effects/effect[@subtype='RechargeTime']")
    if chargeType == ActionChargeType.NONE and (techRechargeType is None or techRechargeTime is None):
        return ""
    recharge = proto.find("auxrechargetime" if chargeType == ActionChargeType.AUX else "rechargetime")
    if recharge is None or techRechargeTime is not None:
        if tech is not None and techRechargeType is not None and techRechargeTime is not None:
            rechargeValue = int(float(techRechargeTime.attrib['amount']))
            if techRechargeType.attrib['rechargetype'] == "attacks":
                return f"Used every {rechargeValue} attacks"
            elif techRechargeType.attrib['rechargetype'] == "damage":
                targets = [x.attrib['type'] for x in action.findall("minrate")]
                targetString = targetListToString(targets)
                return f"Occurs after every {rechargeValue} damage dealt to {targetString}"
        return "Unknown"
    return f"{icon.iconTime()} {float(recharge.text):0.3g}"

def actionDamageOverTime(action: ET.Element, isDPS=False):
    dots = action.findall("onhiteffect[@type='DamageOverTime']")
    dur = None
    targetType = None
    damages = ""
    mult = 1.0
    if isDPS:
        mult = actionDPSMultiplier(action)
    for dot in dots:
        thisDur = float(dot.attrib["duration"])
        if dur is not None and thisDur != dur:
            raise ValueError(f"Unsupported mismatched DoT durations for {action.find('name').text}")
        thisTargetType = dot.get("targetunittype", None)
        if targetType is not None and thisTargetType != targetType:
            raise ValueError(f"Unsupported mismatched DoT target types for {action.find('name').text}")
        dur = thisDur
        targetType = thisTargetType
        damages += f"{icon.damageTypeIcon(dot.get('dmgtype'))} {mult*dur*float(dot.get('rate')):0.3g} "
    if damages == "":
        return ""
    targetString = ""
    if targetType is not None:
        targetString = f" to {common.UNIT_CLASS_LABELS_PLURAL[targetType]}"
    return f"{damages.strip()} over {dur:0.3g}s{targetString}"

def actionOnHitNonDoTEffects(proto: ET.Element, action: ET.Element, ignoreActive=False):
    onhiteffects = action.findall("onhiteffect")
    tactics = actionTactics(proto, action)
    if tactics is not None:
        onhiteffects += tactics.findall("onhiteffect")
    items = []
    forcedTargets = []
    forcedTargetDuration = None
    nodesByType = {}
    for onhiteffect in onhiteffects:
        if not int(onhiteffect.attrib.get("active", "1")) and not ignoreActive:
            continue
        onhitType = onhiteffect.attrib["type"]
        thisItem = ""
        if onhitType in ("Attach", "ShadingFade", "ProgShading", "TreeFlatten", "DamageOverTime", "AnimOverride", "Shading"):
            continue
        elif onhitType == "Freeze":
            damage = float(onhiteffect.attrib.get("damage", 0.0))
            thisItem = f"Freezes targets in place for {float(onhiteffect.attrib['duration']):0.3g} seconds."
            if damage > 0.0:
                thisItem += f" Inflicts {icon.damageTypeIcon('divine')} {damage:0.3g}."
        elif onhitType == "StatModify" or onhitType == "SelfModify":
            armorMods = []
            otherEffects = []
            subject = "targets'" if onhitType == "StatModify" else "the user's"
            for child in onhiteffect:
                if child.attrib["type"] == "ArmorSpecific":
                    armorMods.append(f"{icon.armorTypeIcon(child.attrib['dmgtype'].lower())} {'' if float(child.text) > 1.0 else '+'}{(1.0-float(child.text))*100:0.3g}%")
                elif child.attrib["type"] == "ForcedTarget":
                    forcedTargets.append(onhiteffect.attrib.get("targetunittype", "All"))
                    if forcedTargetDuration is None:
                        forcedTargetDuration = onhiteffect.attrib["duration"]
                    elif forcedTargetDuration != onhiteffect.attrib["duration"]:
                        raise ValueError("Unsupported: mixed ForcedTarget durations")
                elif child.attrib["type"] == "Chaos":
                    otherEffects.append(f"uncontrollable and attack anything nearby, including friends")
                elif child.attrib["type"] == "ROF":
                    otherEffects.append(f"have {float(child.text):0.3g}x attack interval")
                elif child.attrib["type"] == "Speed":
                    otherEffects.append(f"have {float(child.text):0.3g}x movement speed")
                else:
                    raise ValueError(f"Unknown onhit stat modification: {child.attrib['type']}")
            if len(armorMods):
                thisItem += f" Changes {subject} damage vulnerabilities by {' '.join(armorMods)} for {float(onhiteffect.attrib['duration']):0.3g} seconds."
            if len(otherEffects):
                thisItem += f" Makes targets {common.commaSeparatedList(otherEffects)} for {float(onhiteffect.attrib['duration']):0.3g} seconds."
        elif onhitType == "Snare":
            if float(onhiteffect.attrib['rate']) != STANDARD_SNARE['rate'] or float(onhiteffect.attrib['duration']) != STANDARD_SNARE['duration']:
                thisItem = f"Slows targets' movement by {100.0-100*float(onhiteffect.attrib['rate']):0.3g}% for {float(onhiteffect.attrib['duration']):0.3g} seconds."
        elif onhitType == "Stun":
            if "Stun" not in nodesByType:
                nodesByType['Stun'] = []
            nodesByType['Stun'].append(onhiteffect)
        elif onhitType == "Throw":
            if "Throw" not in nodesByType:
                nodesByType['Throw'] = []
            nodesByType['Throw'].append(onhiteffect)
        elif onhitType == "Boost":
            if "Boost" not in nodesByType:
                nodesByType['Boost'] = []
            nodesByType['Boost'].append(onhiteffect)
        elif onhitType == "Reincarnation":
            thisItem = f"If targets die within {float(onhiteffect.attrib['duration']):0.3g} seconds, they are returned to life as a {common.getObjectDisplayName(protoFromName(onhiteffect.attrib['proto']))} under your control."
        elif onhitType == "Lifesteal":
            thisItem = f"Heals for {100*float(onhiteffect.attrib['rate']):0.3g}% of damage inflicted."
        elif onhitType == "Pull":
            if "Pull" not in nodesByType:
                nodesByType['Pull'] = []
            nodesByType['Pull'].append(onhiteffect)
        elif onhitType == "MutateNature":
            thisItem = f"Transforms targets into a {common.getObjectDisplayName(protoFromName(onhiteffect.attrib['proto']))} owned by Mother Nature."
        elif onhitType in ("ProgFreezeSpeed", "ProgFreezeROF", "ProgFreeze"):
            if "ProgFreeze" not in nodesByType:
                nodesByType['ProgFreeze'] = []
            nodesByType['ProgFreeze'].append(onhiteffect)
        else:
            raise ValueError(f"Unknown onhiteffect type: {onhitType}")
        thisItem = thisItem.strip()
        if len(thisItem):
            items.append(thisItem)

    if len(forcedTargets):
        items.append(f" Makes {targetListToString(forcedTargets)} attack the user for {float(onhiteffect.attrib['duration']):0.3g} seconds.")

    for onhitType, nodes in nodesByType.items():
        if onhitType == "Throw":
            targets = targetListToString([x.attrib['targetunittype'] for x in nodes])
            text = f"Launches hit {targets}"
            maxSizeClass = findAndFetchText(action, "maxsizeclass", None, int)
            if maxSizeClass is not None:
                text += f" with a weight class of {maxSizeClass} and below"
            text += "."
            items.append(text)
        elif onhitType == "Stun":
            if len(set([node.attrib.get("duration") for node in nodes])) != 1:
                raise ValueError(f"Stun for {proto.attrib['name']} has mixed durations")
            targets = [node.attrib.get("targetunittype") for node in nodes]
            targets = [target for target in targets if target is not None]
            if len(targets):
                targets = targetListToString(targets)
            else:
                targets = "targets"

            text = f"Stuns {targets} for {float(nodes[0].attrib['duration']):0.3g} seconds."
            items.append(text)
        elif onhitType == "Pull":
            targets = targetListToString([x.attrib['targetunittype'] for x in nodes])
            text = f"Pulls hit {targets} slightly closer."
            items.append(text)
        elif onhitType == "Boost":
            boostType = None
            boostAmount = None
            for item in nodes:
                if item.attrib['duration'] != nodes[0].attrib['duration']:
                    raise ValueError(f"Boost for {item.attrib['targetunittype']} unsupported: multiple targets and mismatched duration")
                if item.attrib['radius'] != nodes[0].attrib['radius']:
                    raise ValueError(f"Boost for {item.attrib['targetunittype']} unsupported: multiple targets and mismatched radius")
                for index, child in enumerate(item):
                    if boostType is None:
                        boostType = child.tag
                    if child.tag != boostType:
                        raise ValueError(f"Boost for {item.attrib['targetunittype']}: unsupported: mismatched modify types {child.tag} and {boostType}")
                    if child.tag == "modify":
                        amt = child.text
                    else:
                        amt = child.attrib['init']
                    if boostAmount is None:
                        boostAmount = amt
                    if amt != boostAmount:
                        raise ValueError(f"Boost for {item.attrib['targetunittype']}: unsupported: mismatched modify amounts {boostAmount} and {amt}")

                               
            text = f"Boosts {common.commaSeparatedList([x.attrib['type'] for x in nodes[0]])} by {float(boostAmount):0.3g}x"
            if boostType == "modifyramp":
                text += f", decaying linearly over the duration of {float(nodes[0].attrib['duration']):0.3g} seconds."
            else:
                text += f" for {float(nodes[0].attrib['duration']):0.3g} seconds."
            targetListString = targetListToString([x.attrib['targetunittype'] for x in nodes])
            if targetListString:
                text += f" Affects {targetListString}."
            items.append(text)
        elif onhitType == "ProgFreeze":
            duration = None
            increment = None
            freezeDuration = None
            components = set()
            for item in nodes:
                components.add(item.attrib['type'])
                if duration is None:
                    duration = item.attrib['duration']
                elif item.attrib['duration'] != duration:
                    raise ValueError(f"{item.attrib['type']} for {item.attrib['targetunittype']}: unsupported: mismatched durations {item.attrib['duration']} and {duration}")
                if increment is None:
                    increment = item.attrib['rate']
                elif item.attrib['rate'] != increment:
                    raise ValueError(f"{item.attrib['type']} for {item.attrib['targetunittype']}: unsupported: mismatched rates {item.attrib['rate']} and {increment}")
                if freezeDuration is None:
                    freezeDuration = item.attrib['freezeduration']
                elif item.attrib['freezeduration'] != freezeDuration:
                    raise ValueError(f"{item.attrib['type']} for {item.attrib['targetunittype']}: unsupported: mismatched freezeduration {item.attrib['freezeduration']} and {freezeDuration}")
            if "ProgFreeze" not in components and ("ProgFreezeROF" not in components or "ProgFreezeSpeed" not in components):
                raise ValueError(f"Incomplete ProgFreeze: components = {components}")
            hitsForFreeze = math.ceil(1.0/float(increment))
            text = f"Each hit slows the target's movement and attack speeds cumulatively by {100*float(increment):0.3g}% for {float(duration):0.3g} seconds. Upon being hit {hitsForFreeze} times in this window, the target is completely frozen for {float(freezeDuration):0.3g} seconds."
            items.append(text)
    return " ".join(items)



def actionPreDamageInfoText(action: ET.Element):
    notes = []
    bounces = action.find("numberbounces")
    if bounces is not None:
        notes.append(f"Beam attack strikes up to {int(bounces.text)-1} additional targets.")
    passthrough = findAndFetchText(action, "passthrough", None) is not None or findAndFetchText(action, "passthroughbuildings", None) is not None
    if passthrough:
        notes.append("Pierces, hitting all targets in a line.")
    if findAndFetchText(action, "perfectaccuracy", None) is not None:
        notes.append("Has perfect accuracy.")
    if findAndFetchText(action, "homingballistics", None) is not None:
        notes.append("Homing.")
    if findAndFetchText(action, "activeifcontainsunits", None) is not None:
        notes.append("Requires a garrisoned unit to fire.")
    return " ".join(notes)
    
    
def findActionByName(proto: Union[ET.Element, str], actionName: str):
    if isinstance(proto, str):
        proto = protoFromName(proto)
    if proto is None:
        return None
    result = proto.find(f"protoaction[name='{actionName}']")
    if result is not None:
        return result
    # The game does this in a case insensitive manner, it looks like trying to get native support for case insensitive xpath in ElementTree is way way more trouble than doing this
    # and accepting it's a bit inefficient
    allActions = proto.findall("protoaction")
    for action in allActions:
        if findAndFetchText(action, "name", "").lower() == actionName.lower():
            return action

    # It could still be an action defined only in the tactics file
    tactics = actionTactics(proto, actionName)
    return tactics

    
def actionTactics(proto: Union[ET.Element, str], action: Union[ET.Element, str, None]) -> Union[None, ET.Element]:
    if isinstance(proto, str):
        proto = protoFromName(proto)
    tacticsNode = proto.find("tactics")
    if tacticsNode is None:
        #raise ValueError(f"Failed to get tactics for {proto.attrib.get('name', 'unknown')}")
        return None
    tacticsFile = globals.dataCollection["tactics"][tacticsNode.text]
    if action is None:
        return tacticsFile
    if not isinstance(action, str):
        action = action.find("name").text
    tacticsNode = tacticsFile.find(f"./action/[name='{action}']")
    if tacticsNode is None:
        #raise ValueError(f"Failed to get tactics node for {proto.attrib.get('name', 'unknown')}'s {actionTypeNode.text}")
        return None
    return tacticsNode

def actionRange(proto: ET.Element, action: ET.Element, useIcon=False):
    minRange = findAndFetchText(action, "minrange", 0.0, float)
    maxRange = findAndFetchText(action, "maxrange", 0.0, float)
    if minRange == 0.0 and maxRange == 0.0:
        tactics = actionTactics(proto, action)
        if tactics is not None:
            minRange = findAndFetchText(tactics, "minrange", 0.0, float)
            maxRange = findAndFetchText(tactics, "maxrange", 0.0, float)
        if minRange == 0.0 and maxRange == 0.0:
            return ""
    rangeString = ""
    if minRange > 0.0:
        rangeString = f"{minRange:0.3g}-"
    rangeString += f"{maxRange:0.3g}"
    if useIcon:
        return f"{icon.iconRange()} {rangeString}"
    return f"{rangeString}m"

def tacticsGetChargeType(tactics: Union[ET.Element, None]):
    if tactics is None:
        return ActionChargeType.NONE
    if tactics.find("auxchargeaction") is not None:
        return ActionChargeType.AUX
    if tactics.find("chargeaction") is not None:
        return ActionChargeType.REGULAR
    return ActionChargeType.NONE

def actionTargetList(action: ET.Element, tactics: Union[None, ET.Element]):
    unitList = []
    for root in action, tactics:
        if root is None:
            continue
        rates = root.findall("rate")
        rates = [rate.attrib['type'] for rate in rates]
        unitList += rates
    unitList = [target for target in unitList if target not in SUPPRESS_TARGET_TYPES]
    return targetListToString(unitList, "and")

def actionDamageOverTimeDamageFromAction(damageAction: ET.Element, includeDamageBonus=True):
    return f"{icon.damageTypeIcon(damageAction.find('modifydamagetype').text.lower())} {float(damageAction.find('modifyamount').text)*-1:0.3g} {actionDamageBonus(damageAction) + ' ' if includeDamageBonus else ''}per second"

def actionDamageOverTimeArea(damageProto: str, damageActionName: str="AreaDamage", altDamageText: str="", lateText: str="", parentAction=None):
    proto = protoFromName(damageProto)
    lifespan = f"{float(proto.find('lifespan').text):0.3g}"
    damageAction = findActionByName(proto, damageActionName)
    radius = f"{float(damageAction.find('maxrange').text):0.3g}m"

    includeDamageBonus = True
    if parentAction is not None:
        includeDamageBonus = actionDamageBonus(damageAction) != actionDamageBonus(parentAction)
    
    if not altDamageText:
        altDamageText = actionDamageOverTimeDamageFromAction(damageAction, includeDamageBonus)
    return f"Creates a damaging area lasting {lifespan} seconds with a radius of {radius}, dealing {altDamageText}. This damage has no falloff with distance. {lateText}".strip()

        
def handleGoreAction(proto: ET.Element, action: ET.Element, tactics: ET.Element, actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    weightClassElement = action.find("maxsizeclass")
    weightClass = ""
    if weightClassElement is not None:
        weightClass = f" with a weight class of {weightClassElement.text} or below"
    shape = ""
    distance = actionArea(action)
    angleElement = action.find("coneareaangle")
    if angleElement is not None:
        shape = f" in a {distance} long {float(angleElement.text):0.3g}° cone"
    else:
        if distance != "":
            shape = f" in a {distance} radius"
        else:
            shape = ""
    
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Launches targets{weightClass}{shape}. {actionDamageFull(proto, action, hideArea=True, ignoreActive=tech is not None)}".replace("  ", " ")

def handleThrowAction(proto: ET.Element, action: ET.Element, tactics: ET.Element, actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    if proto.find("flag/[.='KillsTargetAfterPickupAction']") is not None:
        return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Kills the victim.".replace("  ", " ")
    
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Grabs a target, and throws it (can be retargeted manually). Damages both the thrown unit and nearby {actionDamageFlagNames(action)} objects. {actionDamageFull(proto, action, ignoreActive=tech is not None)}".replace("  ", " ")

def handleBuckAttackAction(proto: ET.Element, action: ET.Element, tactics: ET.Element, actionName: str, chargeType:ActionChargeType, tech: Union[None, ET.Element]=None):
    maxsizeclass = findAndFetchText(action, "maxsizeclass", None, int)
    sizeclass = ""
    if maxsizeclass:
        sizeclass = f"with a weight class of {maxsizeclass} and below "
    stuntext = ""
    if action.find("shockstun") is not None:
        stunduration = findAndFetchText(action, "stunduration", 0.0, float)
        if stunduration > 0.0:
            stuntext = f"Affected targets are stunned for {stunduration:0.3g} seconds. "
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Knocks nearby {actionDamageFlagNames(action)} targets {sizeclass}away. {stuntext}{actionDamageFull(proto, action, ignoreActive=tech is not None)}".replace("  ", " ")


def actionTargetTypeText(proto: ET.Element, action: ET.Element):
    tactics = actionTactics(proto, action)
    stringList = actionTargetList(action, tactics)
    if stringList:
        return f"Targets {stringList}."
    return ""

def simpleActionHandler(additionalText=""):
    def inner(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
        useDPS = chargeType == ActionChargeType.NONE
        items = [actionName, rechargeRate(proto, action, chargeType, tech), actionTargetTypeText(proto, action), additionalText, actionPreDamageInfoText(action), "DPS: " if useDPS else "", actionDamageFull(proto, action, isDPS=useDPS, ignoreActive=tech is not None)]
        if len(items[1]):
            items[1] += ":"
        items = [x for x in items if len(x) > 0]
        return f"{' '.join(items)}"
    return inner

def targetListToString(targetList: List[str], joiner="and"):
    unitClassNames = common.unwrapAbstractClass(targetList, plural=True)
    return common.commaSeparatedList(unitClassNames, joiner)

def handleHealAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rateNode = action.find("rate")
    healRate = f"{float(rateNode.text):0.3g}"
    slowHealMultiplier = findAndFetchText(action, "slowhealmultiplier", 1.0, float) * 100

    items = [actionName, rechargeRate(proto, action, chargeType, tech), "Heals", actionTargetList(action, tactics), f"{healRate} hitpoints/second.", actionRange(proto, action, True)]
    if slowHealMultiplier != 100.0:
        if len(items[-1]):
            items[-1] += "."
        items.append(f"Targets that are not idle are healed at {slowHealMultiplier:0.3g}% speed")
    items = [x for x in items if len(x) > 0]
    return f"{' '.join(items)}."

def handleAutoConvertAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    s = f"If no nearby units of its owner are near, may be converted by other players' units within {actionRange(proto, action)}."
    if action.find("cannotbeconvertedbyallies") is not None:
        s += " Cannot be converted by allies."
    return s

def handleAutoGatherFoodAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rateNodes = action.findall("rate")
    if len(rateNodes) == 0: return ""
    rates = []
    for rateNode in rateNodes:
        rates.append(f"{icon.resourceIcon(rateNode.attrib['type'])} {float(rateNode.text):0.3g}")
    return f"Gains {' '.join(rates)} per second."

def handleAutoGatherAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rateNodes = action.findall("rate")
    if len(rateNodes) == 0: return ""
    rates = []
    for rateNode in rateNodes:
        rates.append(f"{icon.resourceIcon(rateNode.attrib['type'])} {float(rateNode.text):0.3g}")
    return f"Generates {' '.join(rates)} per second."

def handleSelfDestructAttack(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    return f"Explodes on death, dealing {selfDestructActionDamage(proto)}."

def handleBuildAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    buildNodes = proto.findall("train")
    if len(buildNodes) == 0 or len(buildNodes) > 5:
        return ""
    items = []
    for node in buildNodes:
        items.append(common.getObjectDisplayName(protoFromName(node.text)))
    return f"Builds: {common.commaSeparatedList(items)}."

def handleEatAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    return f"Can eat trees and gold mines, draining {float(action.find('rate').text):0.3g} resources per second to heal the same amount of hitpoints."

def handleTradeAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    protoRate = float(action.find("rate[@type='AbstractTownCenter']").text)
    speed = float(proto.find("maxvelocity").text)
    actualRate = globals.dataCollection["game.cfg"]["TradeFullLengthGoldPerSecond"] * protoRate * (speed/globals.dataCollection["game.cfg"]["TradeBaseSpeed"])
    allyRate = globals.dataCollection["game.cfg"]["TradePlayerBonus"]
    # Practical testing suggests this is an overestimate - most likely collision radii means that this function has a small constant term that seemed to be about
    # -3.5/(TradeBaseSpeed^2)
    return f"Trades between friendly Town Centers and your Markets, with more income for travelling further distance (ignoring obstructions). Income if trading along the entirety of the longest map edge is about {icon.resourceIcon('gold')} {actualRate:0.3g} per second. Longer journeys (eg diagonally) can produce more than this. Trading with an ally grants {allyRate}x as much."

def handleEmpowerAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    buildRate = float(tactics.find(".//*[@modifytype='BuildRate']").text)
    researchRate = float(tactics.find(".//*[@modifytype='ResearchRate']").text)
    militaryTrainRate = float(tactics.find(".//*[@modifytype='ResearchRate']").text)
    losFactor = float(tactics.find(".//*[@modifytype='LOSFactor']").text)
    rof = float(tactics.find(".//*[@modifytype='ROF']").text)
    dropsiteRate = float(tactics.find(".//*[@modifytype='DropsiteRate']").text)
    favorRate = float(tactics.find(".//*[@modifytype='FavorGatherRate']").text)
    if buildRate != researchRate or researchRate != militaryTrainRate or militaryTrainRate != losFactor:
        raise ValueError(f"No handling for mixed build/research/los/train empowerments for {proto.attrib['name']}")
    if dropsiteRate != favorRate:
        raise ValueError(f"No handling for mixed dropsite/monument empowerments for {proto.attrib['name']}")
    
    empowerItems = [f"{buildRate:0.3g}x build/research/military train rates and Lighthouse/Obelisk LOS", f"{rof:0.3g}x building attack interval", f"{dropsiteRate:0.3g}x dropsite income and favor rate"]
    godpowerblockradius = findAndFetchText(tactics, ".//*[@modifytype='GodPowerBlockRadius']", None, float)
    if godpowerblockradius is not None:
        empowerItems.append(f"{godpowerblockradius}x god power blocking radius")
    empowerItems[-1] = "and " + empowerItems[-1]
    text = f"Empowers: {', '.join(empowerItems)}."
    return text

def handleAoEAttackAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    duration = float(action.find("rof").text)
    items = [actionName, rechargeRate(proto, action, chargeType, tech), actionTargetTypeText(proto, action), actionPreDamageInfoText(action), f"Continuously damages nearby {actionDamageFlagNames(action)} objects over {duration:0.3g} seconds. Damage dealt per second: ", actionDamageFull(proto, action, damageMultiplier=20.0, hideRof=True, ignoreActive=tech is not None)]
    if len(items[1]):
        items[1] += ":"
    items = [x for x in items if len(x) > 0]
    return f"{' '.join(items)}"

def handleLikeBonusAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    stat = findAndFetchText(action, "modifytype", None)
    if stat is None:
        stat = findAndFetchText(action, "modifydamagetype", None)
        if stat is not None:
            stat += " damage"
    mult = findAndFetchText(action, "modifymultiplier", None, float)
    targetunit = "other unit of the same type"
    modifyprotoid = findAndFetchText(action, "modifyprotoid", None)
    if modifyprotoid is not None:
        mult = findAndFetchText(action, f"./rate[@type='{modifyprotoid}']", None, float)
        targetunit = common.getObjectDisplayName(protoFromName(modifyprotoid))
    if mult is None:
        print(f"Info: LikeBonus for {proto.attrib['name']} seemingly has no modifymultiplier")
        return ""
    mult *= 100
    area = findAndFetchText(action, "maxrange", None, float)
    targetLimit = findAndFetchText(action, "modifytargetlimit", None, int)
    text = f"Increases {stat} by {mult:0.3g}% for each {targetunit} within {area:0.3g}m"
    if targetLimit is not None:
        text += f", to a maximum bonus of {targetLimit*mult:0.3g}% with {targetLimit} other group members"
    return text + "."

def handleMaintainAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    killontrain = findAndFetchText(tactics, "killontrain", None, int)
    trainpoints = findAndFetchText(tactics, "maintaintrainpoints", None, float)
    targettype = common.getObjectDisplayName(protoFromName(tactics.find("rate").attrib['type']))
    if killontrain:
        return f"After {trainpoints:0.3g} seconds, dies and is replaced with a {targettype}."
    else:
        return f"Produces a {targettype} every {trainpoints:0.3g} seconds."

def handleBurstHealAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rateNode = action.find("rate")
    healRate = f"{float(rateNode.text):0.3g}"
    items = [actionName, "Heals", actionTargetList(action, tactics), f"{healRate} hitpoints instantly.", actionRange(proto, action, True), actionRof(action)]
    if chargeType != ActionChargeType.NONE:
        items.insert(1, rechargeRate(proto, action, chargeType, tech)+":")
    return f"{' '.join(items)}."

def handleDelayedTransformAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    return f"Can freely transform into a {common.getObjectDisplayName(protoFromName(action.find('modifyprotoid').text))} after {findAndFetchText(action, 'modifyduration', 0.0, float)/1000.0:0.3g} seconds."

def handleAutoRangedAttachAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    modifyAbstractType = findAndFetchText(action, "modifyabstracttype", None)
    components = []
    attachUnit = findAndFetchText(action, "attachprotounit", None)
    maxRange = findAndFetchText(action, "maxrange", 0.0, float)

    components.append(f"Creates a {common.getDisplayNameForProtoOrClass(attachUnit)} on {targetListToString([modifyAbstractType])} within {maxRange:0.3g}m.")

    return " ".join(components)

def handleIdleStatBonusAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    modifyType = findAndFetchText(action, "modifytype", None)
    components = []

    modifyamount = findAndFetchText(action, "modifyamount", None, float)
    modifyratecap = findAndFetchText(action, "modifyratecap", None, float)
    modifydecay = findAndFetchText(action, "modifydecay", None, float)
    modifybase = findAndFetchText(action, "modifybase", 0.0, float)

    timeToMax = (modifyratecap - modifybase)/modifyamount
    timeToMax = f"{timeToMax:0.3g}"

    components.append("While idle,")

    if modifyType in ("ArmorSpecific", "Damage", "LOS", "Speed"):
        isPercentile = modifyType not in ("LOS")
        percentileMult = 100 if isPercentile else 1
        suffix = "%" if isPercentile else ""
        modifyTypeName = modifyType
        if modifyType in ("ArmorSpecific"):
            modifyamount *= -1.0
            modifyratecap = 1.0 + (1.0-modifyratecap)
            modifydecay *= -1.0
            modifyTypeName = findAndFetchText(action, "modifydamagetype", None) + " vulnerability"
        if modifyamount > 0.0:
            components.append(f"increases {modifyTypeName} by {percentileMult*(modifyamount):0.3g}{suffix} per second, to a maximum increase of {percentileMult*(modifyratecap-modifybase):0.4g}{suffix} after {timeToMax} seconds of idleness.")
            if modifydecay is not None:
                components.append(f"When not idle and not moving, the bonus does not change. When moving, this effect decays at {percentileMult*(modifydecay):0.3g}{suffix} per second.")
        elif modifyamount < 0.0:
            components.append(f"reduces {modifyTypeName} by {-percentileMult*(modifyamount):0.3g}{suffix} per second, to a maximum reduction of {-percentileMult*(modifyratecap-modifybase):0.4g}{suffix} after {timeToMax} seconds of idleness.")
            if modifydecay is not None:
                components.append(f"When not idle and not moving, the bonus does not change. When moving, this effect decays at {-percentileMult*(modifydecay):0.3g}{suffix} per second.")
    else:
        print(f"Warning: Unknown IdleStatBonus modify type {modifyType} for {proto.attrib['name']}")
        return ""

    #print(components)
    return " ".join(components)

def handleSpawnAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rateNode = action.find("rate")
    spawnCount = int(float(rateNode.text))
    spawnedProto = common.getObjectDisplayName(protoFromName(rateNode.attrib['type']))
    unitTypeText = f"{spawnCount} {spawnedProto}"
    if spawnCount == 1:
        unitTypeText = f"a {spawnedProto}"
    items = []
    if len(actionName):
        items.append(actionName+":")
    items.append(rechargeRate(proto, action, chargeType, tech) +":")
    items += ["Spawns", unitTypeText]
    return f"{' '.join(items)}."

def handleLinearAreaAttackAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    # Approximately:
    # The unit travels minrate metres
    # The movement speed is modifyamount
    # rof seemingly does not matter at all

    distance = findAndFetchText(action, "minrate", None, float)
    movespeed = findAndFetchText(action, "modifyamount", None, float)
    width = findAndFetchText(action, "damagearea", None, float)
    attackTime = distance/movespeed

    # Testing shows the RoF doesn't matter, but the total time is time in flight plus the entry and exit animations
    # For the nidhogg this is 3.24s
    targetList = actionTargetList(action, tactics)
    if targetList == "":
        targetList = "objects"

    items = [actionName, rechargeRate(proto, action, chargeType, tech) +":", "Hits", actionDamageFlagNames(action), targetList, f"in a {width:0.3g}x{distance:0.3g}m area for approximately", actionDamageFull(proto, action, damageMultiplier=attackTime, hideRof=True, hideArea=True, hideRange=True, ignoreActive=tech is not None)]
    return f"{' '.join(items)}"

def handleDistanceModifyAtion(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    maxSpeed = findAndFetchText(proto, "maxvelocity", 0.0, float)
    minSpeed = findAndFetchText(action, "minrate", 0.0, float) * maxSpeed
    speedDelta = maxSpeed - minSpeed
    maxRange = findAndFetchText(action, "maxrange", 0.0, float)
    minRange = findAndFetchText(action, "minrange", 0.0, float)
    rangeDelta = maxRange-minRange

    speedPerRange = speedDelta/rangeDelta

    return f"Once more than {minRange:0.3g}m from the Town Center it was spawned around, it starts to lose {10*speedPerRange:0.3g} speed per 10m travelled. Once it is more than {maxRange:0.3g}m away, its speed drops to the minimum of {minSpeed:0.3g}."


MODIFY_TYPE_DISPLAY = {
    "Armor":"Damage Vulnerability",
    "MaxHP":"Max Hitpoints",
    "Speed":"Movement Speed",
    "BuildRate":"Build Speed",
    "MilitaryTrainingCost":"Military Unit Cost",
}


def handleAutoRangedModifyAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    modifyType = findAndFetchText(tactics, "modifytype", None)
    if modifyType is None:
        return ""

    components = []
    lateComponents = []
    if len(actionName):
        components += f"{actionName}:"

    range = findAndFetchText(tactics, "maxrange", None, float)
    if range is None:
        range = findAndFetchText(action, "maxrange", None, float)
        if range is None:
            return ""

    restrictempowertype = findAndFetchText(tactics, "restrictempowertype", None, str)
    if restrictempowertype is not None:
        restrictProto = protoFromName(restrictempowertype)
        if restrictProto is not None:
            empowerer = common.getObjectDisplayName()
        else:
            empowerer = common.getDisplayNameForProtoOrClass(restrictempowertype) # KeyError if a missing unit class
        components.append(f"If empowered by a {empowerer},") 

    modifyrangeuselos = findAndFetchText(tactics, "modifyrangeuselos", None, int)
    if modifyrangeuselos is not None and modifyrangeuselos > 0:
        components.append(f"Projects an aura over its LOS which")
    else:
        components.append(f"Projects a {range:0.3g}m aura which")
    
    if len(components) > 1:
        components[-1] = "p" + components[-1][1:]

    modifyTargetLimit = findAndFetchText(action, "modifytargetlimit", None, int)

    if modifyType == "HealRate":
        damageType = findAndFetchText(action, "modifydamagetype", "Divine")
        damageAmount = findAndFetchText(tactics, "modifyamount", None, float)
        if damageAmount is None:
            damageAmount = findAndFetchText(action, "modifyamount", None, float)
        if damageAmount < 0.0:
            components.append(f"deals {icon.damageTypeIcon(damageType)} {damageAmount*-1:0.3g}")
            components.append(actionDamageBonus(action))
            components.append("per second to")
        elif damageAmount > 0.0:
            components.append(f"heals {damageAmount:0.3g} hitpoints per second to")
            slowHealMultiplier = findAndFetchText(action, "slowhealmultiplier", 1.0, float)
            if modifyTargetLimit is not None:
                lateComponents.append(f"Heals up to {modifyTargetLimit} targets at once.")
            if slowHealMultiplier < 1.0:
                lateComponents.append(f"Targets that are not idle are healed at {slowHealMultiplier*100:0.3g}% speed.")
    elif modifyType in ("Damage", "Armor", "MaxHP", "Speed", "BuildRate", "MilitaryTrainingCost"):
        multiplier = findAndFetchText(tactics, "modifymultiplier", None, float)
        modifyTypeName = MODIFY_TYPE_DISPLAY.get(modifyType, modifyType)
        if modifyType in ("Armor"):
            multiplier = 1.0 + (1.0-multiplier)
        if multiplier > 1.0:
            components.append(f"increases {modifyTypeName} by {100*(multiplier-1.0):0.3g}% for")
        elif multiplier < 1.0:
            components.append(f"decreases {modifyTypeName} by {-100*(multiplier-1.0):0.3g}% for")
    elif modifyType == "RevealUI":
        components.append("allows you to check the actions of")
    elif modifyType == "AuraEmpower":
        components.append(f"{handleEmpowerAction(proto, action, tactics, '', chargeType)} Affects")
    else:
        print(f"Warning: Unknown AutoRangedModify type {modifyType} for {proto.attrib['name']}")
        return ""

    playerRelation = "your"
    if findAndFetchText(tactics, "targetenemy", ""):
        playerRelation = "enemy"
    elif findAndFetchText(tactics, "targetnonally", ""):
        playerRelation = "non-allied"
    if findAndFetchText(tactics, "targetunbuilt", ""):
        playerRelation += " unfinished"

    components.append(playerRelation)

    allowedTargetTypes = [x.text for x in tactics.findall("modifyabstracttype")]
    forbidTargetTypes = [x.text for x in tactics.findall("forbidabstracttype")+tactics.findall("forbidunittype")]

    if len(allowedTargetTypes):
        components.append(targetListToString(allowedTargetTypes))
    else:
        components.append("objects")

    if len(forbidTargetTypes):
        components[-1] += ","
        components.append(f"except {targetListToString(forbidTargetTypes)}")

    components[-1] += "."

    components += lateComponents

    

    if findAndFetchText(tactics, "nostack", 0, int) == 0:
        components.append("Stacking")
    else:
        components.append("Does not stack")

    components = [component.strip() for component in components if len(component.strip()) > 0]
    return " ".join(components) + "."


def doNothingHandler(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    return ""

ACTION_TYPE_HANDLERS: Dict[str, Callable[[ET.Element, ET.Element, Union[None, ET.Element], str, ActionChargeType, Union[None, ET.Element]], str]] = {
    # Overrides for proto action names go here
    # These are not real action types
    "ChopAttack":doNothingHandler,

    # Actual action types.
    "Pickup":doNothingHandler,
    "DropOff":doNothingHandler,
    "RelicNoPickup":doNothingHandler,
    "Repair":doNothingHandler,
    "Hunting":doNothingHandler,
    "Gather":doNothingHandler,
    "NoWork":doNothingHandler,
    "SmartDropsite":doNothingHandler,

    "Build":handleBuildAction,
    "Heal":handleHealAction,
    "Gore":handleGoreAction,
    "AutoConvert":handleAutoConvertAction,
    "AutoGatherFood":handleAutoGatherFoodAction,
    "AutoGather":handleAutoGatherAction,
    "SelfDestructAttack":handleSelfDestructAttack,
    "Eat":handleEatAction,
    "Throw":handleThrowAction,
    "BuckAttack":handleBuckAttackAction,
    "Trade":handleTradeAction,
    "Empower":handleEmpowerAction,
    "AoEAttack":handleAoEAttackAction,
    "AutoRangedModify":handleAutoRangedModifyAction,
    "LikeBonus":handleLikeBonusAction,
    "Maintain":handleMaintainAction,
    "BurstHeal":handleBurstHealAction,
    "DelayedTransform":handleDelayedTransformAction,
    "IdleStatBonus":handleIdleStatBonusAction,
    "Spawn":handleSpawnAction,
    "LinearAreaAttack":handleLinearAreaAttackAction,
    "AutoRangedAttach":handleAutoRangedAttachAction,
    "DistanceModify":handleDistanceModifyAtion,
    
    
    "JumpAttack":simpleActionHandler("Leaps over obstacles on the way to the target."),
    "Attack":simpleActionHandler(),
    "ChainAttack":simpleActionHandler(),
    "AutoBoost":simpleActionHandler(),
}

def actionDamageFlagNames(action: ET.Element):
    flags = action.find("damageflags")
    if flags is None:
        return ""
    split = flags.text.split("|")
    if "Nature" in split:
        split.remove("Nature")
    if "Enemy" in split and "Self" in split and "Ally" in split:
        return "all"
    if "Self" in split and "Ally" in split:
        split.remove("Self")
        split.remove("Ally")
        split.add("friendlies")
    return common.commaSeparatedList(split).lower()

def selfDestructActionDamage(proto: Union[str, ET.Element]):
    action = findActionByName(proto, "SelfDestructAttack")
    if action is not None:
        return f"{actionDamageOnly(action, hideRof=True)} {actionDamageBonus(action)} to {actionDamageFlagNames(action)} objects within {actionArea(action)}"
    return ""

def getCivAbilitiesNode(proto: Union[ET.Element, str], action: Union[ET.Element, str], forceAbilityLink: Union[str, None]=None):
    if isinstance(proto, str):
        proto = common.protoFromName(proto)
    if isinstance(action, str):
        action = findActionByName(proto, action)
    
    actionInternalName = findAndFetchText(action, "name", None)
    abilityInfo = None

    if forceAbilityLink is not None:
        abilityInfo = globals.dataCollection["abilities_combined"].find(f"power[@name='{forceAbilityLink}']")
    else:
        unitAbilitiesEntry = globals.dataCollection["abilities"]["abilities.xml"].find(proto.attrib["name"].lower())
        if unitAbilitiesEntry is None:
            pass
        else:
            for abilityNode in unitAbilitiesEntry:
                abilityInfo = globals.dataCollection["abilities_combined"].find(f"power[@name='{abilityNode.text}']")
                if findAndFetchText(abilityInfo, "unitaction", None) == actionInternalName:
                    break
                abilityInfo = None
    return abilityInfo

def getActionName(proto: Union[ET.Element, str], action: Union[ET.Element, str], forceAbilityLink: Union[str, None]=None, nameNonChargeActions=False):
    if isinstance(proto, str):
        proto = common.protoFromName(proto)
    if isinstance(action, str):
        action = findActionByName(proto, action)
    actionName = ""
    actionInternalName = findAndFetchText(action, "name", None)
    abilityInfo = getCivAbilitiesNode(proto, action, forceAbilityLink)

    if abilityInfo is not None:
        actionName = common.getObjectDisplayName(abilityInfo)
        if actionName is None:
            print(f"Warning: No name for charge action {actionInternalName} -> on {proto.get('name')}")
            actionName = actionInternalName
    if len(actionName) == 0 and nameNonChargeActions:
        actionName = ACTION_TYPE_NAMES.get(actionInternalName, actionInternalName)

    return actionName


def describeAction(proto: ET.Element, action: ET.Element, chargeType: ActionChargeType=ActionChargeType.NONE, nameOverride: Union[str, None] = None, forceAbilityLink: Union[str, None] = None, overrideText: Union[str, None]=None, tech: Union[ET.Element, None]=None):
    # Display names for charge actions only
    actionName = ""
    actionInternalName = findAndFetchText(action, "name", None)
    actionInternalType = findAndFetchText(action, "type", actionInternalName)
    tactics = actionTactics(proto, action)
    if tactics is not None:
        tacticsTypeNode = tactics.find("type")
        if tacticsTypeNode is not None:
            actionInternalType = tacticsTypeNode.text

    
    abilityInfo = getCivAbilitiesNode(proto, action, forceAbilityLink)
    actionName = ""
    if chargeType != ActionChargeType.NONE:
        if abilityInfo is None:
            print(f"Info: No abilities.xml entry found for {proto.attrib['name']} but it has a charge action {actionInternalName}")
        if nameOverride:
            actionName = nameOverride
        else:
            actionName = getActionName(proto, action, forceAbilityLink)
    
    result = ""
    handler = ACTION_TYPE_HANDLERS.get(actionInternalName, ACTION_TYPE_HANDLERS.get(actionInternalType, None))
    if handler is None:
        print(f"Warning: No handler for action: internal type={actionInternalType}; action name={actionInternalName}; display name={actionName}; on {proto.get('name')}")
    else:
        result = handler(proto, action, actionTactics(proto, action), actionName, chargeType, tech)
        if overrideText is not None:
            result = overrideText
        if abilityInfo is not None and proto.attrib["name"] not in common.PROTOS_TO_IGNORE_FOR_ABILITY_TOOLTIPS:
            common.addToGlobalAbilityStrings(proto, abilityInfo, result)
        
        
    return result
