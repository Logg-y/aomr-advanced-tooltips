import enum
import common
from common import findAndFetchText, protoFromName
import icon
import globals
from xml.etree import ElementTree as ET
from typing import Union, Dict, List, Callable, Any, Type, Tuple
import math
import copy
import re
import unitdescription
import functools
import dataclasses

class ActionChargeType(enum.Enum):
    NONE = 0
    REGULAR = 1
    AUX = 2

STANDARD_SNARE = {"rate":0.85, "duration":2.0}

# Writing out identical infection text for each action creates a lot of redundant text
# It makes much more sense to do it once per unit, and then list it at the end...
UNIT_INFECTION_TEXT = {}


SUPPRESS_TARGET_TYPES = (
    # The guardians mess up SoO's heal action.
    "GuardianSleeping",
    "GuardianSleepingTNA",
    "Football",
    # Also a valid heal action target
    "TitanGateSPC",
    "MonumentToVillagersSPC",
    "MonumentToPriestsSPC",
    "MonumentToPharaohsSPC",
    "InvisibleTarget",
    "CluckCluckBoom",
)

SUPPRESS_TARGET_TYPES_IF_EXCLUSIVE = (
    "All",
    "LogicalTypeHandUnitsAttack",
    "LogicalTypeRangedUnitsAttack",
    "LogicalTypeVillagersAttack",
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
    "AOTGKronosUniqueAura":"Slow Aura",
    "AreaEnhanceWithTechHack":"Hack Protection Aura",
    "AreaEnhanceWithTechPierce":"Pierce Protection Aura",
    "PierceArmorInverseAura":"Scaling Pierce Protection",
    "HackArmorInverseAura":"Scaling Hack Protection",
    "SelfDestructAttack":"Death Explosion",
    "Demolition":"Demolition",
    "SpeedBoost":"Speed Boost Aura",
    "IncreaseDamageWithLikeUnits":"Group Powerup",
    "ChopAttack":"Wood Chopping",
    "ThornedWallsAttack":"Melee Retaliation Attack",
    "AbductDrop":"Drop",
}

def findFromActionOrTactics(action: ET.Element, tactics: ET.Element, query: str, default: Any=None, conversion: Union[None, Type] = None):
    val = findAndFetchText(action, query, None, conversion)
    if val is None and tactics is not None:
        val = findAndFetchText(tactics, query, None, conversion)
    if val is None:
        return default
    return val

def findAllFromActionOrTactics(action: Union[None, ET.Element], tactics: Union[None, ET.Element], query: str) -> List[ET.Element]:
    results = []
    if tactics is not None:
        results += tactics.findall(query)
    if action is not None:
        results += action.findall(query)
    return results




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
            unitClassIcon = icon.iconUnitClass(targetType)
            if unitClassIcon is not None:
                actionDamageBonuses.append(f"{unitClassIcon} x{multSize:0.3g}")
            else:
                actionDamageBonuses.append(f"x{multSize:0.3g} vs {common.getDisplayNameForProtoOrClass(targetType, plural=True)}")
    allydamagemultiplier = action.find("allydamagemultiplier")
    if allydamagemultiplier is not None:
        actionDamageBonuses.append(f"x{float(allydamagemultiplier.text):0.3g} to friendly targets")
    if actionDamageBonuses:
        return f"({', '.join(actionDamageBonuses)})"
    return ""
        
def actionDamageOnly(proto: ET.Element, action: ET.Element, isDPS=False, hideNumProjectiles=False, damageMultiplier=1.0):
    damages = []
    # I used to not multiply up if showing projectiles to show damage per projectile...
    # But then it was multiplying up the DoT anyway, so it's probably better to show numbers assuming everything hits
    mult = damageMultiplier * actionDamageMultiplier(proto, action, isDPS=isDPS)

    for damage in action.findall("damage"):
        damageType = damage.attrib["type"]
        damageAmount = float(damage.text)
        damageAmount *= mult
        # This function has to support some very large numbers (eg bolt's 10000 divine) but also needs to handle
        # smaller noninteger values without giving pointless levels of precision
        intlength = len(str(round(damageAmount)))
        if damageAmount > 0.0:
            if intlength >= 3:
                damages.append(f"{icon.damageTypeIcon(damageType)} {round(damageAmount)}")
            else:
                damages.append(f"{icon.damageTypeIcon(damageType)} {damageAmount:0.3g}")
    if not hideNumProjectiles:
        damages.append(actionNumProjectiles(proto, action))
    damages = [x for x in damages if len(x.strip()) > 0]
    final = " ".join(damages)
    
    return final

def actionNumProjectiles(proto: ET.Element, action: ET.Element, format=True):
    displayedNumProjectiles = findAndFetchText(action, "displayednumberprojectiles", None, int)
    numProjectilesFromData = findAndFetchText(action, "numberprojectiles", 1, int)
    if displayedNumProjectiles is None:
        displayedNumProjectiles = numProjectilesFromData
    simdataAttackCount = getActionAttackCount(proto, action)
    numProjectiles = simdataAttackCount * numProjectilesFromData
    if numProjectiles != displayedNumProjectiles:
        common.warn(f"{proto.attrib['name']}'s action {getActionDisplayName(proto, action, nameNonChargeActions=True)} has projectile count mismatch: data reports {simdataAttackCount} (simdata.simjson attack count) with {numProjectilesFromData} each (proto numprojectiles), but {displayedNumProjectiles} from UI")
    if not format:
        return numProjectiles
    if numProjectiles == 1:
        return ""
    numProjectiles = int(numProjectiles)
    return f"{icon.iconNumProjectiles()} x{numProjectiles}"

def actionRof(action: ET.Element):
    rof = findAndFetchText(action, "rof", 1.0, float)
    return f"{icon.iconRof()} {rof:0.3g}"


def actionDamageMultiplier(proto: ET.Element, action: ET.Element, isDPS=True, singleProjectile=False):
    rof = findAndFetchText(action, "rof", 1.0, float)
    if not isDPS:
        rof = 1.0
    if singleProjectile:
        numProjectiles = 1
    else:
        numProjectiles = actionNumProjectiles(proto, action, format=False)
    
    rof /= numProjectiles
    return 1.0/rof
    

def actionDamageFull(protoUnit: ET.Element, action: ET.Element, isDPS=False, hideArea=False, damageMultiplier=1.0, hideRof=False, hideRange=False, ignoreActive=False, hideDamageBonuses=False, hideDamage=False):
    # Scorpion man special attack has displayed num projectiles but no actual projectiles
    # I think it makes 3 little attacks and this is how the developers opted to represent that
    # but it'd be much less confusing to multiply these out for the tooltip
    hideNumProjectiles = False
    numProjectiles = actionNumProjectiles(protoUnit, action, format=False)
    
    hasProjectile = findAndFetchText(action, "projectile", None) is not None
    if not hasProjectile or numProjectiles < 2:
        hideNumProjectiles = True
    components = []
    if not hideDamage:
        components.append(actionDamageOnly(protoUnit, action, isDPS, damageMultiplier=damageMultiplier, hideNumProjectiles=hideNumProjectiles))
    if not hideRof:
        components.append(actionRof(action))
    if not hideArea:
        components.append(actionArea(action, True))
    if not hideDamageBonuses and not hideDamage:
        components.append(actionDamageBonus(action))
    if not hideRange:
        components.append(actionRange(protoUnit, action, True))
    if action.find("damagearea") is not None:
        damageFlags = actionDamageFlagNames(action)
        # The intention behind this is to specifically flag things that can friendly fire
        if damageFlags != "" and damageFlags != "enemy":
            components.append(f"Affects {damageFlags} objects.")
    components = [component for component in components if len(component.strip()) > 0]
    
    dot = actionDamageOverTime(protoUnit, action, isDPS, damageMultiplier=damageMultiplier)
    if len(dot) > 0:
        components.append(f"plus an additional {dot}.")
    elif components:
        components[-1] += "."

    tactics = actionTactics(protoUnit, action)

    trackrating = findFromActionOrTactics(action, tactics, "trackrating", None, float)
    if trackrating is not None and trackrating != 0.0:
        components.append(f"Track rating: {trackrating:0.3g}.")
    accuracy = findFromActionOrTactics(action, tactics, "accuracy", None, float)
    if accuracy is not None:
        if findFromActionOrTactics(action, tactics, "perfectaccuracy") is None:
            components.append(f"Accuracy: {100*accuracy:0.3g}%.")
    if findFromActionOrTactics(action, tactics, "autoretarget", 0, int) > 0 and getActionAttackCount(protoUnit, action) > 1:
        components.append(f"Later attacks in the animation retarget if the victim dies partway through.")

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

    if findFromActionOrTactics(action, tactics, "selfdestruct", 0, int) > 0:
        components.append("Kills the user.")

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
    # If a tech is specified, for one of the water charged spawn enableds, we have to assume that the tech
    # also sets the charge requirements on the action to work properly
    
    # Otherwise if the action is not charged, we don't have to supply a recharge timer
    if chargeType == ActionChargeType.NONE and tech is None:
        return ""
    
    # Use unit type data first
    rechargeType = None
    rechargeTime = findAndFetchText(proto, "auxrechargetime" if chargeType == ActionChargeType.AUX else "rechargetime", None, float)
    rechargeElem = proto.find("auxrecharge" if chargeType == ActionChargeType.AUX else "recharge")
    if rechargeElem is not None:
        rechargeTime = float(rechargeElem.text)
        rechargeType = rechargeElem.attrib.get("type", None)
    # Override with techs if supplied, assumes that the techs will be setting the recharge settings on the right proto (and there's only one of these effects)
    if tech is not None:
        techRechargeType = tech.find("effects/effect[@subtype='RechargeType']")
        if techRechargeType is not None:
            rechargeType = techRechargeType.attrib['rechargetype'].lower()
        techRechargeTime = tech.find("effects/effect[@subtype='RechargeTime']")
        if techRechargeTime is not None:
            rechargeTime = float(techRechargeTime.attrib['amount'])

    if rechargeType is not None:
        rechargeType = rechargeType.lower()
    
    if rechargeTime is None:
        common.warn_data(f"No recharge time found for an action of {proto.attrib['name']}")
        return ""
    
    if rechargeType is not None and rechargeTime is not None:
        if rechargeType == "attacks":
            targets = [x.attrib['type'] for x in action.findall("minrate") if float(x.text) != 0.0]
            excludes = [x.attrib['type'] for x in action.findall("minrate") if float(x.text) == 0.0]
            text = f"Occurs every {rechargeTime:0.3g} attacks"
            if len(targets) + len(excludes) > 0:
                text += f" against {targetListToString(targets, excludes)}"
            return text 
            

        elif rechargeType == "damage":
            targets = [x.attrib['type'] for x in action.findall("minrate") if float(x.text) != 0.0]
            excludes = [x.attrib['type'] for x in action.findall("minrate") if float(x.text) == 0.0]
            targets += [elem.text for elem in proto.findall('rechargeincludetypes/unittype')]
            excludes += [elem.text for elem in proto.findall('rechargeexcludetypes/unittype')]
            targetString = targetListToString(targets, excludes)
            return f"Occurs every {rechargeTime:0.3g} damage dealt to {targetString}"
        else:
            common.warn_unhandled(f"Unhandled action recharge type {rechargeType} on {proto.attrib['name']}")
            return "Unknown"
        
    return f"{icon.iconTime()} {rechargeTime:0.3g}"

def onhiteffectTargetString(onhiteffect: ET.Element, hitword="hit", default="targets", additionalHitTargets: Union[str, None, List[str]]=None, additionalForbiddenTargets: Union[str, None, List[str]]=None):
    targetElems = onhiteffect.findall("target")
    targetTypes = []
    ignoreTypes = []
    if additionalHitTargets is not None:
        if isinstance(additionalHitTargets, str):
            targetTypes.append(additionalHitTargets)
        else:
            targetTypes += additionalHitTargets
    if additionalForbiddenTargets is not None:
        if isinstance(additionalForbiddenTargets, str):
            ignoreTypes.append(additionalForbiddenTargets)
        else:
            ignoreTypes += additionalForbiddenTargets
    onhiteffectTarget = onhiteffect.attrib.get("targetunittype", None)
    if onhiteffectTarget is not None:
        targetTypes.append(onhiteffectTarget)
    for elem in targetElems:
        if "attacktype" in elem.attrib:
            targetTypes.append(elem.attrib["attacktype"])
        elif "ignoretype" in elem.attrib:
            ignoreTypes.append(elem.attrib["ignoretype"])
        else:
            raise ValueError(f"On hit effect target has an unknown onhit target specifier: likely one of: {elem.attrib}")
    targetTypes = list(set(targetTypes))
    ignoreTypes = list(set(ignoreTypes))
    if len(targetTypes) + len(ignoreTypes) > 0:
        if len(targetTypes) == 0:
            targetTypes = ["All"]
        targets = targetListToString(targetTypes, ignoreTypes)
        targetString = f"{hitword} {targets}"
        return targetString.strip()
    if default.strip() == "":
        return ""
    return f"{hitword} {default}"

def actionDamageOverTime(proto: ET.Element, action: ET.Element, isDPS=False, damageMultiplier=1.0, singleProjectile=False, ignoreActive=False):
    dots = action.findall("onhiteffect[@type='DamageOverTime']")
    dur = None
    targetType = None
    damages = ""
    prob = None
    mult = damageMultiplier * actionDamageMultiplier(proto, action, isDPS=isDPS, singleProjectile=singleProjectile)
    for dot in dots:
        if ignoreActive == False and int(dot.attrib.get("active", 1)) == 0:
            continue
        thisDur = float(dot.attrib["duration"])
        if dur is not None and thisDur != dur:
            raise ValueError(f"Unsupported mismatched DoT durations for {action.find('name').text}")
        dur = thisDur

        thisTargetType = onhiteffectTargetString(dot, default="", additionalHitTargets=dot.get("targetunittype", None))
        if targetType is not None and thisTargetType != targetType:
            raise ValueError(f"Unsupported mismatched DoT target types for {action.find('name').text}")
        
        targetType = thisTargetType
        damageElems = dot.findall("damage")
        for damageElem in damageElems:
            damages += f"{icon.damageTypeIcon(damageElem.get('type'))} {mult*dur*float(damageElem.text):0.3g} "

        # From the docs:
        # Damage defines through the rate parameter does not account for damage bonuses or target armor.
        if "rate" in dot.attrib:
            damages += f"{icon.damageTypeIcon('divine')} {mult*dur*float(dot.attrib['rate']):0.3g} (not multiplied by damage bonuses) "
        
        thisProb = dot.attrib.get("prob", dot.attrib.get("globalprob", prob))
        if thisProb != prob and prob is not None:
            raise ValueError(f"Unsupported mismatched DoT probabilities for {action.find('name').text}")
        elif thisProb is not None:
            prob = thisProb
        
    if damages == "":
        return ""
    
    if targetType != "":
        targetType = f" to {targetType}"

    probText = ""
    if prob is not None:
        probText = f"{prob}% chance: "
    return f"{probText}{damages.strip()} over {dur:0.3g}s{targetType}"

def elementsEqual(e1: ET.Element, e2: ET.Element) -> bool:
    if e1.tag != e2.tag: return False
    if e1.text != e2.text: return False
    if e1.attrib != e2.attrib: return False
    if len(e1) != len(e2): return False
    return all(elementsEqual(c1, c2) for c1, c2 in zip(e1, e2))

def groupUpNearIdenticalElements(elements: List[ET.Element], attribtoignore: str, additionalMatchPreprocessor: Callable[[ET.Element], ET.Element]=lambda elem: elem) -> List[List[ET.Element]]:
    """
    Given a list of elements, makes deep copies of each and removes the passed attribtoignore from their attributes and returns lists of then-identical elements.
    If additionalMatchPreprocessor is passed, this is called on all deep copies prior to the identicality test.
    """
    removedAttributesForGrouping: List[ET.Element] = []
    elementGroups: List[List[ET.Element]] = []
    for child in elements:
        stripped = copy.deepcopy(child)
        stripped = additionalMatchPreprocessor(stripped)
        if attribtoignore in stripped.attrib:
            del stripped.attrib[attribtoignore]
        match = next((x for x in removedAttributesForGrouping if elementsEqual(x, stripped)), None)
        if match is None:
            removedAttributesForGrouping.append(stripped)
            elementGroups.append([child])
        else:
            index = removedAttributesForGrouping.index(match)
            elementGroups[index].append(child)
    return elementGroups

def handleModifyStructure(parentElem: ET.Element) -> str:
    """Handle parent onhiteffect elements with <modify> and <modifyramp> children.

    Might return something like "Increases Damage and Movement Speed by 1.5x, decaying over 5 seconds." - it is up to the caller to say what relation it has to the action (modify self, targets, boost)
    or the radius, or what unit types it affects.
    """
    # The challenges here:
    # 1) Some units have multiple on hit effects that do the exact same thing, but have one for each affected abstract type (eg Arkantos boost)
    # 2) Some units have one on hit effect with multiple modifies that do nearly the same thing and the natural way to write a tooltip would be to combine them (eg: Einheri boost)
    # (Einheri does both of these AT THE SAME TIME!)

    # Approach: gather up onhit effects, look for ones that are identical except for targetunittype and group them together (solves 2) - the parent onhit handler should do this probably
    # Within a single onhit effect parent group, look for ones that are identical except for type and group those together

    simpleModifyTypeToDisplayStrings = {
        "ROF":"Attack Interval",
        "Speed":"Movement Speed",
        "Damage":"Damage",
        "MaxShieldPoints":"Shield Points",
        "LifeSteal":"Lifesteal",
        "DamageSpecific":"{damagetype} Damage",
        
    }

    simpleModifyTypeFormatAmounts = {
        "LifeSteal": lambda amt: f"{amt*100:0.3g}%"
    }
    # ArmorSpecific is really strange here.
    # Any INCREASE in vulnerability (petrify, scorching feathers) simply does the listed multiplication to their armor stat
    # Any DECREASE in vulnerability (myth unit specials etc) uses the same calcs techs do for vulnerability reduction

    # ArmorSpecific should merge regardless of the types and values
    def additionalMatchPreprocessor(elem: ET.Element):
        if elem.attrib.get("type", None) == "ArmorSpecific":
            elem.text = 0.0
            del elem.attrib['dmgtype']
        elem.text = 0.0
        if "applytype" in elem.attrib:
            del elem.attrib['applytype']
        return elem

    effectGroups = groupUpNearIdenticalElements([child for child in parentElem], "type", additionalMatchPreprocessor=additionalMatchPreprocessor)
    items = []
    for effectGroup in effectGroups:
        otherEffects = []
        needMentionDecay = False
        for child in effectGroup:
            useApplyTypeText = False
            if child.tag == "modifyramp":
                # "modify": the value is in child.text
                # "modifyramp": the initial value is in "init" and goes down to "final"
                amountInitial = float(child.attrib['init'])
                amountFinal = float(child.attrib['final'])
            elif child.tag == "modify":
                amountInitial = float(child.text)
                amountFinal = None
            else:
                continue
            if child.attrib["type"] == "ForcedTarget":
                text = f"forces victims to attack the user"
                otherEffects.append(text)
            elif child.attrib["type"] == "Chaos":
                otherEffects.append(f"victims become uncontrollable and attack anything nearby")
            elif child.attrib["type"] == "ArmorSpecific":
                if amountInitial < 1.0:
                    otherEffects.append(f"{icon.armorTypeIcon(child.attrib.get('dmgtype', ''))} x{amountInitial:0.3g}")
                else:
                    otherEffects.append(f"-{100.0*(amountInitial-1.0):0.3g}% {child.attrib.get('dmgtype', '')} vulnerability")

            elif child.attrib["type"] in simpleModifyTypeToDisplayStrings:
                displayString = simpleModifyTypeToDisplayStrings[child.attrib['type']]
                displayString = displayString.format(damagetype=child.attrib.get("dmgtype", "").lower()).strip()
                applyType = child.attrib.get("applytype", "multiply").lower()
                amountFormatter = simpleModifyTypeFormatAmounts.get(child.attrib['type'], lambda amt: f"{amt:0.3g}")

                if applyType == "multiply":
                    text = f"{displayString} x{amountFormatter(amountInitial)}"
                    if amountFinal is not None and amountFinal != 1.0:
                        text += f" (decays to x{amountFormatter(amountFinal)} over the duration)"
                    if amountFinal == 1.0:
                        needMentionDecay = True
                    
                    
                elif applyType == "add":
                    text = f"{displayString} {'+' if amountInitial > 0 else '-'}{amountFormatter(amountInitial)}"
                    if amountFinal is not None and amountFinal != 0.0:
                        text += f" (decays to {'+' if amountFinal > 0 else '-'}{amountFormatter(amountFinal)} over the duration)"
                    if amountFinal == 0.0:
                        needMentionDecay = True

                elif applyType == "set":
                    text = f"{displayString} set to {amountFormatter(amountInitial)}"

                else:
                    raise ValueError(f"Unknown modify tag with applytype {applyType}")
                otherEffects.append(text)
                
            else:
                raise ValueError(f"Unknown onhit stat modification: {child.attrib['type']}")
        thisItem = ""
        if len(otherEffects):
            otherEffectsJoined = common.commaSeparatedList(otherEffects)
            otherEffectsJoined = " " + otherEffectsJoined[0].upper() + otherEffectsJoined[1:] + "."
            thisItem += otherEffectsJoined
        if needMentionDecay:
            thisItem += " Bonuses decay over the duration."
        if len(thisItem) > 0:
            thisItem += f" Lasts {float(parentElem.attrib['duration']):0.3g} seconds."
        items.append(thisItem)
    return " ".join(items)

def actionOnHitNonDoTEffects(proto: ET.Element, action: ET.Element, ignoreActive=False, filterOnHitTypes: Union[None, List[str]]=None):
    onhiteffects = action.findall("onhiteffect")
    tactics = actionTactics(proto, action)
    if tactics is not None:
        onhiteffects += tactics.findall("onhiteffect")
    items = []
    if filterOnHitTypes is not None:
        onhiteffects = list(filter(lambda x: x.attrib['type'] in filterOnHitTypes, onhiteffects))
    nodesByType = {}

    for onhiteffect in onhiteffects:
        if not int(onhiteffect.attrib.get("active", "1")) and not ignoreActive:
            continue
        probString = ""
        prob = int(onhiteffect.attrib.get("prob", onhiteffect.attrib.get("globalprob", "100")))
        if prob < 100:
            probString = f"{prob}% chance: "
        targetString = onhiteffectTargetString(onhiteffect)

        onhitType = onhiteffect.attrib["type"]
        thisItem = ""
        if onhitType in ("Attach", "ShadingFade", "ProgShading", "TreeFlatten", "DamageOverTime", "AnimOverride", "Shading"):
            continue
        elif onhitType == "Freeze":
            damage = float(onhiteffect.attrib.get("damage", 0.0))
            thisItem = f"{probString}Freezes {targetString} in place for {float(onhiteffect.attrib['duration']):0.3g} seconds."
            if damage > 0.0:
                thisItem += f" Inflicts {icon.damageTypeIcon('divine')} {damage:0.3g}."
        elif onhitType in ("StatModify", "SelfModify", "Boost"):
            if onhitType not in nodesByType:
                nodesByType[onhitType] = []
            nodesByType[onhitType].append(onhiteffect)
        elif onhitType == "Snare":
            if float(onhiteffect.attrib['rate']) != STANDARD_SNARE['rate'] or float(onhiteffect.attrib['duration']) != STANDARD_SNARE['duration']:
                thisItem = f"{probString}Slows movement of {targetString} by {100.0-100*float(onhiteffect.attrib['rate']):0.3g}% for {float(onhiteffect.attrib['duration']):0.3g} seconds."
            else:
                thisItem += f"{probString}Snares."
        elif onhitType == "Stun":
            if "Stun" not in nodesByType:
                nodesByType['Stun'] = []
            nodesByType['Stun'].append(onhiteffect)
        elif onhitType == "Throw":
            if "Throw" not in nodesByType:
                nodesByType['Throw'] = []
            nodesByType['Throw'].append(onhiteffect)
        elif onhitType == "Reincarnation":
            thisItem = f"{probString}If {targetString} die within {float(onhiteffect.attrib['duration']):0.3g} seconds, they are returned to life as a {common.getObjectDisplayName(protoFromName(onhiteffect.attrib['proto']))} under your control."
        elif onhitType == "Lifesteal":
            thisItem = f"{probString}Heals for {100*float(onhiteffect.attrib['rate']):0.3g}% of damage inflicted."
        elif onhitType == "Pull":
            if "Pull" not in nodesByType:
                nodesByType['Pull'] = []
            nodesByType['Pull'].append(onhiteffect)
        elif onhitType == "MutateNature":
            thisItem = f"{probString}Transforms {targetString} into a {common.getObjectDisplayName(protoFromName(onhiteffect.attrib['proto']))} owned by Mother Nature."
        elif onhitType in ("ProgFreezeSpeed", "ProgFreezeROF", "ProgFreeze"):
            if "ProgFreeze" not in nodesByType:
                nodesByType['ProgFreeze'] = []
            nodesByType['ProgFreeze'].append(onhiteffect)
        elif onhitType == "Spawn":
            thisItem = f"{probString}Spawns"
            amount = int(onhiteffect.attrib.get("amount", 1))
            if amount > 1:
                thisItem += f" {amount}x"
            else:
                thisItem += " a"
            thisItem += f" {common.getObjectDisplayName(protoFromName(onhiteffect.attrib['proto']))}."
        elif onhitType == "Root":
            thisItem = f"{probString}Roots {targetString} for {float(onhiteffect.attrib['duration']):0.3g}s."
        elif onhitType == "Flee":
            thisItem = f"{probString}Causes {targetString} to run in fear for {float(onhiteffect.attrib['duration']):0.3g}s."
        elif onhitType == "SelfStealth":
            thisItem = f"{probString}Becomes invisible for {float(onhiteffect.attrib['duration']):0.3g}s."
        elif onhitType == "Exile":
            thisItem = f"{probString}Removes {targetString} from the world for {float(onhiteffect.attrib['duration']):0.3g}s, after which they reappear."
        elif onhitType == "Infect":
            infectionActionName = onhiteffect.attrib['protoaction']
            infectionAction = findActionByName(proto, infectionActionName)
            infectionDuration = common.findAndFetchText(infectionAction, "infectionduration", None, float)/1000.0

            infectionActionType = findFromActionOrTactics(infectionAction, actionTactics(proto, infectionAction), "type")
            if infectionActionType == "AutoRangedModify":
                infectionActionContent = handleAutoRangedModifyAction(proto, infectionAction, actionTactics(proto, infectionAction), "", isInfection=True)
            else:
                common.warn_unhandled(f"{proto.attrib['name']} attempts to apply infection action of type {infectionActionType}, no handling for this")
                continue

            thisItem = f"{probString}Infects {targetString} for {infectionDuration:0.3g}s: {infectionActionContent}"
        else:
            raise ValueError(f"Unknown onhiteffect type: {onhitType}")
        thisItem = thisItem.strip()
        if len(thisItem):
            items.append(thisItem)

    for onhitType, nodes in nodesByType.items():
        probText = ""
        probValue = None
        for node in nodes:
            thisProb = float(node.attrib.get("prob", node.attrib.get("globalprob", 100.0)))
            if thisProb != 100.0:
                if probValue is not None and probValue != thisProb:
                    common.warn_unhandled(f"Mixed onhit effect probability nodes for {proto.attrib['name']}")
                elif probValue is None:
                    probValue = thisProb
        if probValue is not None:
            probText = f"{probValue:0.3g}% chance: "
        if onhitType == "Throw":
            onhitGroups = groupUpNearIdenticalElements(nodes, "targetunittype")
            for group in onhitGroups:
                additionalTargets = [elem.attrib['targetunittype'] for elem in group[1:] if 'targetunittype' in elem.attrib]
                targetTypeString = onhiteffectTargetString(group[0], additionalHitTargets=additionalTargets)
                text = f"{probText}Launches {targetTypeString}"
                maxSizeClass = findAndFetchText(action, "maxsizeclass", None, int)
                if maxSizeClass is not None:
                    text += f" with a weight class of {maxSizeClass} and below"
                text += "."
            items.append(text)

        elif onhitType == "Stun":            
            onhitGroups = groupUpNearIdenticalElements(nodes, "targetunittype")
            for group in onhitGroups:
                additionalTargets = [elem.attrib['targetunittype'] for elem in group[1:] if 'targetunittype' in elem.attrib]
                targetTypeString = onhiteffectTargetString(group[0], additionalHitTargets=additionalTargets)
                dur = float(group[0].attrib['duration'])
                text = f"{probText}Stuns {targetTypeString} for {dur:0.3g} {'second' if dur == 1.0 else 'seconds'}."
            items.append(text)
        elif onhitType == "Pull":
            onhitGroups = groupUpNearIdenticalElements(nodes, "targetunittype")
            for group in onhitGroups:
                additionalTargets = [elem.attrib['targetunittype'] for elem in group[1:] if 'targetunittype' in elem.attrib]
                targetTypeString = onhiteffectTargetString(group[0], additionalHitTargets=additionalTargets)
                text = f"{probText}Pulls {targetTypeString} slightly closer."
            items.append(text)
        elif onhitType in ("StatModify", "SelfModify", "Boost"):
            onhitGroups = groupUpNearIdenticalElements(nodes, "targetunittype")
            for group in onhitGroups:
                additionalTargets = [elem.attrib['targetunittype'] for elem in group[1:] if 'targetunittype' in elem.attrib]
                hitword = "hit"
                if onhitType == "StatModify":
                    text = "Affects {targetTypeString}: "
                elif onhitType == "SelfModify":
                    text = "Affects the user: "
                elif onhitType == "Boost":
                    text = f"Buffs {{targetTypeString}} within {float(group[0].attrib['radius']):0.3g}m: "
                    hitword = "your"
                targetTypeString = onhiteffectTargetString(group[0], default="objects", additionalHitTargets=additionalTargets, hitword=hitword)
                text = text.format(targetTypeString=targetTypeString)
                text += handleModifyStructure(group[0])
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
            text = f"{probText}Each hit slows the target's movement and attack speeds cumulatively by {100*float(increment):0.3g}% for {float(duration):0.3g} seconds. Upon being hit {hitsForFreeze} times in this window, the target is completely frozen for {float(freezeDuration):0.3g} seconds."
            items.append(text)
    result = " ".join(items)
    return re.sub(" +", " ", result)



def actionPreDamageInfoText(action: ET.Element):
    notes = []
    bounces = action.find("numberbounces")
    if bounces is not None:
        notes.append(f"Beam attack strikes up to {int(bounces.text)-1} additional target{'s' if int(bounces.text) > 2 else ''}.")
    passthrough = findAndFetchText(action, "passthrough", None) is not None or findAndFetchText(action, "passthroughbuildings", None) is not None
    if passthrough:
        projectile = findAndFetchText(action, "projectile", None)
        if projectile is not None:
            obstruction = findAndFetchText(protoFromName(projectile), "obstructionradiusx", None, float)
            if obstruction is None:
                projectile = None
            else:
                notes.append(f"Pierces, hitting all targets in a {obstruction:0.3g}m wide line.")
        if projectile is None:
            notes.append("Pierces, hitting all targets in a line.")
    coneAngle = action.find("coneareaangle")
    if coneAngle is not None:
        notes.append(f"Hits targets in a {float(coneAngle.text):0.3g}° cone.")
            
    if findAndFetchText(action, "perfectaccuracy", None) is not None:
        notes.append("Has perfect accuracy.")
    if findAndFetchText(action, "homingballistics", None) is not None:
        notes.append("Homing.")
    if findAndFetchText(action, "activeifcontainsunits", None) is not None:
        notes.append("Requires a garrisoned unit to fire.")
    return " ".join(notes)
    
    
def findActionByName(proto: Union[ET.Element, str], actionName: Union[ET.Element, str]):
    if not isinstance(actionName, str):
        return actionName
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
        nameElem = action.find("name")
        if nameElem is None:
            return None
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

def actionGetChargeType(action: Union[ET.Element, None], tactics: Union[ET.Element, None]):
    chargeType = ActionChargeType.NONE
    if tactics is not None:
        if tactics.find("auxchargeaction") is not None:
            chargeType = ActionChargeType.AUX
        if tactics.find("chargeaction") is not None:
            chargeType = ActionChargeType.REGULAR
    if chargeType == ActionChargeType.NONE and action is not None:
        if action.find("auxchargeaction") is not None:
            chargeType = ActionChargeType.AUX
        if action.find("chargeaction") is not None:
            chargeType = ActionChargeType.REGULAR
    return chargeType

def actionTargetList(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element]):
    # It looks like the tactics file gives the final word on what can and can't target with attacks
    tacticsAttackTypes = []
    additionalExcludeText = []
    if findFromActionOrTactics(action, tactics, "attackaction", 0, int) > 0:
        tacticsFile = actionTactics(proto, None)
        if tacticsFile is not None:
            actInternalName = findFromActionOrTactics(action, tactics, "name")
            for tactic in tacticsFile.findall("tactic"):
                if tactic.find(f"action/[.='{actInternalName}']") is None:
                    continue
                attacktype = findAndFetchText(tactic, "attacktype", None, str)
                if attacktype is not None:
                    tacticsAttackTypes.append(attacktype)
        tacticsAttackTypes = list(set(tacticsAttackTypes))

    unitList = []
    disallowedList = []
    for root in action, tactics:
        if root is None:
            continue
        rates = root.findall("rate")
        unitList += filter(lambda elem: float(elem.text) > 0.0, rates)
        disallowedList += filter(lambda elem: float(elem.text) <= 0.0, rates)

    typeFromElem = lambda elem: elem.attrib['type']
    unitList = list(map(typeFromElem, unitList))
    disallowedList = list(map(typeFromElem, disallowedList))

    # Sort out the tactics attacktype mess:
    # We need to know if it has to get involved at all:
    # - which means it specifies restrictions that the rate elems would miss
    # - we also want to cull any rate elems that don't actually do anything because of the tactics - eg...

    # tactics provides LogicalTypeHandUnitsAttack; rate elems specify LogicalTypeHandUnitsAttack + LogicalTypeMythUnitNotFlying
    # In this case LogicalTypeMythUnitNotFlying is not useful info
    uselessRateElems = []
    if len(tacticsAttackTypes) > 0:
        suppressTargetSet = set(SUPPRESS_TARGET_TYPES)
        for index, rateTarget in enumerate(unitList):
            # Restriction missed by rate elem?
            if not common.isUnitClassASubsetOfOthers(rateTarget, tacticsAttackTypes):
                # If a tactics one is entirely a subset of the rate defined one, switching the two is okay
                doneSwitch = False
                for tacticsTarget in tacticsAttackTypes:
                    if common.isUnitClassASubsetOfOther(tacticsTarget, rateTarget):
                        unitList[index] = tacticsTarget
                        #if tacticsTarget != rateTarget: print(f"Tactics target subsitution: tactics contained {tacticsTarget} which is a subset of rate set {rateTarget}, switching...")
                        doneSwitch = True
                        break
                if not doneSwitch:
                    # Silence some basic complaints using the logic flags: it's pretty obvious to most people what does and doesn't have "reach"
                    if "LogicalTypeRangedUnitsAttack" in tacticsAttackTypes and findFromActionOrTactics(action, tactics, "rangedlogic", 0, int) > 0:
                        pass
                    elif "LogicalTypeHandUnitsAttack" in tacticsAttackTypes and findFromActionOrTactics(action, tactics, "handlogic", 0, int) > 0:
                        pass
                    # On second thoughts, it is probably never worth caring about LogicalTypeRangedUnitsAttack here since "except those that can't be attacked at range" is almost a nonexistent group anyway
                    elif "LogicalTypeRangedUnitsAttack" in tacticsAttackTypes:
                        pass
                    # "can't be attacked with melee" and "flying" are nearly synonymous. It should be good enough, unless someone really cares about what kills herdables or something
                    elif "LogicalTypeHandUnitsAttack" in tacticsAttackTypes:
                        # As always, no point specifying this unless there is some overlap
                        # This matters for some things like Shinobi's anti-building attack
                        if 'AbstractFlyingUnit' not in disallowedList and set(globals.protosByUnitType.get(rateTarget, [rateTarget])).intersection(set(globals.protosByUnitType['AbstractFlyingUnit'])):
                            disallowedList.append("AbstractFlyingUnit")
                    else:
                        common.warn_unhandled(f"{proto.attrib['name']}:{findFromActionOrTactics(action, tactics, 'name', "?")}: {rateTarget} has nonoverlapping area with tactics defined {tacticsAttackTypes}")

            # Useless target class?
            isUseless = False
            rateSet = set(globals.protosByUnitType.get(rateTarget, [rateTarget]))
            rateSet -= suppressTargetSet
            for tacticsTarget in tacticsAttackTypes:
                tacticsSet = set(globals.protosByUnitType.get(tacticsTarget, [tacticsTarget]))
                intersection = rateSet.intersection(tacticsSet)
                for otherRateTarget in unitList:
                    if otherRateTarget != rateTarget:
                        otherRateSet = set(globals.protosByUnitType.get(otherRateTarget, [otherRateTarget]))
                        intersection -= otherRateSet
                        if len(intersection) == 0:
                            #print(f"Remove rate elem {rateTarget} constrained by {tacticsTarget} since it doesn't contribute anything any more, last checked against {otherRateTarget}")
                            isUseless = True
                            uselessRateElems.append(rateTarget)
                            break
                        #print(len(intersection), rateTarget, otherRateTarget, intersection)
                if isUseless:
                    break
                

    for useless in uselessRateElems:
        if useless in unitList:
            unitList.remove(useless)    
    nonSuppressed = lambda target: target not in SUPPRESS_TARGET_TYPES

    unitListFiltered = list(filter(nonSuppressed, unitList))
    disallowedListFiltered = list(filter(nonSuppressed, disallowedList))
    # We have to stop suppressing the suppressible types if it would leave us with nothing
    if len(unitListFiltered) == 0 and len(disallowedListFiltered) > 0:
        unitListFiltered = (list(map(typeFromElem, unitList)))
    # the exclusive list = filter if all are in there
    # If all that's left is stuff on this list, we want to be left with nothing
    # ... unless there's an exclusion
    if all(map(lambda x: x in SUPPRESS_TARGET_TYPES_IF_EXCLUSIVE, unitListFiltered)) and len(disallowedListFiltered) == 0:
        unitListFiltered = []
    text = targetListToString(unitListFiltered, disallowedListFiltered, joiner="and")
    return text

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

def handleAbductAction(proto: ET.Element, action: ET.Element, tactics: ET.Element, actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    duration = findFromActionOrTactics(action, tactics, "modifyduration", 0, int)
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Picks up and carries around the victim for {duration/1000:0.3g} seconds, disabling other actions in this time. They cannot be released manually. At the end of the duration, they are dropped: {actionDamageFull(proto, action, ignoreActive=tech is not None)} If dropped over impassable terrain, the victim will be moved to a walkable edge if one is close enough, otherwise they simply die.".replace("  ", " ")


        
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

def handleRampageAction(proto: ET.Element, action: ET.Element, tactics: ET.Element, actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    weightClassElement = action.find("maxsizeclass")
    weightClass = ""
    if weightClassElement is not None:
        weightClass = f" with a weight class of {weightClassElement.text} or below"
    distance = actionArea(action)
    if distance != "":
        shape = f" within {distance}"
    else:
        shape = ""
    
    chargeStructure = '. '.join(handleChargeStructure(action.find("charged")))
    
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: Enters a rampage: {chargeStructure}. While active, damages targets (each target can be hit once per activation, has no distance falloff) {shape}. Launches targets{weightClass}. {actionDamageFull(proto, action, hideArea=True, hideRof=True, ignoreActive=tech is not None)}".replace("  ", " ")


def handleThrowAction(proto: ET.Element, action: ET.Element, tactics: ET.Element, actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    if proto.find("flag/[.='KillsTargetAfterPickupAction']") is not None:
        return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Kills the victim. {actionDamageFull(proto, action, hideDamage=True, hideArea=True, ignoreActive=tech is not None)}".replace("  ", " ")
    
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

def handleReflectAttackAction(proto: ET.Element, action: ET.Element, tactics: ET.Element, actionName: str, chargeType:ActionChargeType, tech: Union[None, ET.Element]=None):
    items = [actionName, rechargeRate(proto, action, chargeType, tech), actionTargetTypeText(proto, action), "Damages when attacked in melee.", actionPreDamageInfoText(action), actionDamageFull(proto, action, isDPS=False, hideRof=True, ignoreActive=tech is not None)]
    for index in (1, 0):
        if len(items[index]):
            items[index] += ":"
            break
    items = [x for x in items if len(x) > 0]
    return f"{' '.join(items)}"

def actionTargetTypeText(proto: ET.Element, action: ET.Element):
    tactics = actionTactics(proto, action)
    stringList = actionTargetList(proto, action, tactics)
    text = ""
    if stringList:
        text += f"Targets {stringList}."
    if findFromActionOrTactics(action, tactics, "restricttowater", 0, int):
        text += " Can only be used while in water, and can only target water."
    if findFromActionOrTactics(action, tactics, "maxrange", 0.0, float) > 900.0:
        text += " Requires line of sight to use."
    return text.strip()

def simpleActionHandler(additionalText=""):
    def inner(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
        useDPS = chargeType == ActionChargeType.NONE and findFromActionOrTactics(action, tactics, "selfdestruct", 0, int) == 0
        items = [actionName, rechargeRate(proto, action, chargeType, tech), actionTargetTypeText(proto, action), additionalText, actionPreDamageInfoText(action), "DPS: " if useDPS else "", actionDamageFull(proto, action, isDPS=useDPS, ignoreActive=tech is not None)]
        for index in (1, 0):
            if len(items[index]):
                items[index] += ":"
                break
        items = [x for x in items if len(x) > 0]
        return f"{' '.join(items)}"
    return inner

def targetListToString(targetList: List[str], excludeTargets: List[str] = [], joiner="and", additionalExclusionText=[]):
    # Various logic ends up with repeated exclusions being listed - no point checking the same things multii
    targetList = list(set(targetList))
    excludeTargets = list(set(excludeTargets))

    # Some things redundantly specify multiple target types, but some of them turn out to be subsets of other specified targets
    # so those can get removed
    for list_ in targetList, excludeTargets:
        for item in list_[:]:
            if common.isUnitClassASubsetOfOthers(item, list_):
                list_.remove(item)    

    unitClassNames = common.getListOfDisplayNamesForProtoOrClass(targetList, plural=True)
    
    text = common.commaSeparatedList(unitClassNames, joiner)
    
    # Also, some things exclude targets pointlessly that were never in the targeted unit types to begin with
    # eg farms already lack the "affected by earthquake" flag, don't need to exclude them again
    # This is especially common for autorangedmodify actions since they exclude flying targets by default
    # an aura that damages buildings need not mention that it doesn't affect flying because there are no flying buildings
    attackTargetsExpandedTypes = []
    
    for target in targetList:
        if target not in globals.protosByUnitType:
            attackTargetsExpandedTypes.append(target)
        else:
            attackTargetsExpandedTypes += globals.protosByUnitType[target]
    
    restrictedTargetsRevised = []
    for target in excludeTargets:
        targetWouldBeHit = False
        if target in attackTargetsExpandedTypes or len(attackTargetsExpandedTypes) == 0:
            targetWouldBeHit = True
        elif target in globals.protosByUnitType:
            # Exclude if no members of this unit type are in the list of valid targets
            for abstractTypeMember in globals.protosByUnitType[target]:
                if abstractTypeMember in attackTargetsExpandedTypes:
                    targetWouldBeHit = True
                    break
        if targetWouldBeHit:
            restrictedTargetsRevised.append(target)

    if len(restrictedTargetsRevised) + len(additionalExclusionText) > 0:
        excludeText = common.commaSeparatedList(common.getListOfDisplayNamesForProtoOrClass(restrictedTargetsRevised, plural=True) + additionalExclusionText, joiner)
        if len(targetList) == 0:
            text += f"cannot target {excludeText}"
        else:
            text += f" (except {excludeText})"
    
    return text

def handleHealAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rateNode = action.find("rate")
    if rateNode is None:
        common.warn_data(f"Heal for {proto.attrib['name']}: no rate node found, ignoring")
        return ""
    healRate = f"{float(rateNode.text):0.3g}"
    slowHealMultiplier = findAndFetchText(action, "slowhealmultiplier", 1.0, float) * 100

    items = [actionName, rechargeRate(proto, action, chargeType, tech), "Heals", actionTargetList(proto, action, tactics), f"{healRate} hitpoints/second.", actionRange(proto, action, True)]
    for index in range(0, 2):
        if len(items[index]):
            items[index] += ":"
            break
    if slowHealMultiplier != 100.0:
        if len(items[-1]):
            items[-1] += "."
        items.append(f"Targets that have moved or been involved in combat in the last 3 seconds are healed at {slowHealMultiplier:0.3g}% speed.")
    modifytargetlimit = action.find("modifytargetlimit")
    outerdamageareadistance = action.find("outerdamageareadistance")
    modifyamount = action.find("modifyamount")
    if modifytargetlimit is not None and outerdamageareadistance is not None:
        additionaltargettext = f"Affects up to {int(modifytargetlimit.text)} additional targets within {float(outerdamageareadistance.text):0.3g}m"
        if modifyamount is not None:
            additionaltargettext += f", with each successive target being healed at {float(modifyamount.text)*100:0.4g}% of the rate of the previous target."
            maxOutputMultiplier = 1.0
            for x in range(0, int(modifytargetlimit.text)):
                maxOutputMultiplier += 1/(2**(1+x))
            totalHealing = float(rateNode.text)*maxOutputMultiplier
            additionaltargettext += f" Total output at maximum efficiency: {totalHealing:0.3g} hitpoints/second."
        items.append(additionaltargettext)
    items = [x for x in items if len(x) > 0]
    return f"{' '.join(items)}"


def handleAreaMutateAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    allowed, forbidden = getAllowForbidTargetTypes(action, tactics)
    targetProto = common.getDisplayNameForProtoOrClassPlural(findFromActionOrTactics(action, tactics, "modifyprotoid", None))
    # Stating that things aren't converted into themselves seems fairly redundant
    for item in allowed:
        if item in forbidden:
            forbidden.remove(item)
    radius = findFromActionOrTactics(action, tactics, "maxrange", 0.0, float)

    return f"Converts {targetListToString(allowed, forbidden)} within {radius:0.3g}m into {targetProto}."

def handleAutoConvertAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    s = f"If no nearby units of its owner are near, may be converted by other players' units within {actionRange(proto, action)}."
    modifyabstracttypes = findAllFromActionOrTactics(action, tactics, "modifyabstracttype")
    if len(modifyabstracttypes) > 0:
        s += f" Cannot be converted if the owner has nearby {common.commaSeparatedList(common.getListOfDisplayNamesForProtoOrClass([elem.text for elem in modifyabstracttypes], plural=True), 'or')}."
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
        rate = float(rateNode.text)
        stringForm = format(rate, "0.3g")
        # This is a horrible fudge which hopefully handles very small numbers without displaying standard form
        # if the 3sf rounded form has no accurate floating point representation this will need more work though
        if rate < 0.01:
            stringForm = format(float(format(rate, "0.3g")), "10f").rstrip("0")
        rates.append(f"{icon.resourceIcon(rateNode.attrib['type'])} {stringForm}")

    if findFromActionOrTactics(action, tactics, "autogatherscalebygatherrate", 0, int):
        targetTypeElems = findAllFromActionOrTactics(action, tactics, "donotautogatherunlessgatheringtypes/unittype")
        targetTypes = [elem.text for elem in targetTypeElems]
        if len(targetTypes) == 0:
            return f"Generates {' '.join(rates)} per resource gathered."
        
        return f"Generates {' '.join(rates)} per resource gathered while gathering from {common.getDisplayNameForProtoOrClassPlural(targetTypes)}."
    
    text = f"Generates {' '.join(rates)} per second."
    if findFromActionOrTactics(action, tactics, "addresourcestoinventory", 0, int) > 0:
        text = f"Adds {' '.join(rates)} to its inventory per second."
    if findFromActionOrTactics(action, tactics, "donotautogatherifgathered", 0, int) > 0:
        text += " Stops once something has started gathering from it."
    return text

def handleSelfDestructAttack(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    items = [actionName, rechargeRate(proto, action, chargeType, tech), actionTargetTypeText(proto, action), "On death:", actionPreDamageInfoText(action), actionDamageFull(proto, action, isDPS=False, ignoreActive=tech is not None, hideRof=True)]
    for index in (1, 0):
        if len(items[index]):
            items[index] += ":"
            break
    items = [x for x in items if len(x) > 0]
    return f"{' '.join(items)}"

def handleBuildAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    buildNodes = proto.findall("train")
    stem = ""
    #if len(buildNodes) > 0 and len(buildNodes) <= 5:
    #    stem += f" Can build: {common.getDisplayNameForProtoOrClassPlural([node.text for node in buildNodes])}."
    
    targetElems = action.findall("rate")
    rateItems = [f"{common.getDisplayNameForProtoOrClassPlural(elem.attrib['type'])} at {float(elem.text):0.3g} unit{'s' if float(elem.text) != 1.0 else ''}/s" for elem in targetElems]
    stem += f"Builds {common.commaSeparatedList(rateItems)}."
    
    return stem.strip()

def handleEatAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    return f"Can eat trees and gold mines, draining {float(action.find('rate').text):0.3g} resources per second to heal the same amount of hitpoints."

def handleTradeAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    protoRate = float(action.find("rate[@type='AbstractTownCenter']").text)
    speed = float(proto.find("maxvelocity").text)
    actualRate = globals.dataCollection["game.cfg"]["TradeFullLengthGoldPerSecond"] * protoRate * (speed/globals.dataCollection["game.cfg"]["TradeBaseSpeed"])
    allyRate = globals.dataCollection["game.cfg"]["TradePlayerBonus"]
    # Practical testing suggests this is an overestimate - most likely collision radii means that this function has a small constant term that seemed to be about
    # -3.5/(TradeBaseSpeed^2)
    return f"Trades between friendly Town Centers and your Markets, with faster income for travelling further distance (ignoring obstructions). Income if trading along the entirety of the longest map edge is about {icon.resourceIcon('gold')} {actualRate:0.3g} per second. Longer journeys (eg diagonally) can produce more than this. Trading with an ally grants {allyRate}x as much."

def handleReleaseSkyLanternAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    targetProto = common.protoFromName(action.find("rate").attrib['type'])
    targetInfo = []
    targetInfo.append(f"{findAndFetchText(targetProto, 'los', None, float):0.3g} LOS")
    targetInfo.append(f"{findAndFetchText(targetProto, 'maxvelocity', None, float):0.3g} speed")
    if targetProto.find("lifespan") is not None:
        targetInfo.append(f"lives for {findAndFetchText(targetProto, 'lifespan', None, float):0.3g} seconds")
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: Releases a {common.getDisplayNameForProtoOrClass(targetProto)} which starts moving in the targeted direction. It has {common.commaSeparatedList(targetInfo)}."

def handleConvertAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    if findFromActionOrTactics(action, tactics, "charmedconvert", 0, int):
        exclusive = ""
        if findFromActionOrTactics(action, tactics, "exclusive", 0, int):
            exclusive = "A target cannot be affected by this action until previous conversions expire. "
        duration = findFromActionOrTactics(action, tactics, "typedduration", 0.0, float)/1000.0
        stunDuration = findFromActionOrTactics(action, tactics, "typedstunduration", 0.0, float)/1000.0
        return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Stuns targets for {stunDuration:0.3g}s, creating a copy under your control next to the user that lasts for the {duration:0.3g}s. This copy inherits any upgrades on the original, and appears at full health with special attacks ready to use. {exclusive}{actionRange(proto, action, True)} {actionRof(action)}"

    converttargets = {}
    forbiddenTargets = []
    for elem in findAllFromActionOrTactics(action, tactics, "rate"):
        dur = float(elem.text)
        if dur == 0.0:
            forbiddenTargets.append(elem.attrib['type'])
        else:
            converttargets[elem.attrib['type']] = dur
    if len(converttargets) > 1:
        common.warn_unhandled(f"Convert action on {proto.attrib['name']} has more than one target type or forbidden targets")
        return ""
    else:
        target = list(converttargets.keys())[0]
        time = converttargets[target]
        timeText = f"{time:0.3g} seconds"
        timeperhitpoint = findFromActionOrTactics(action, tactics, "extraratepertargethp", 0.0, float)
        if timeperhitpoint > 0.0:
            hpPerSecond = 1/timeperhitpoint
            timeText += f", plus an additional 1 second per {hpPerSecond:0.3g} hitpoints of the target"
        return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Permanently converts the target in {timeText}. {actionRange(proto, action, True)}"

def handleTrailAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    protoElem = action.find("trailprotounit")
    freq = float(protoElem.attrib['frequency'])
    targetProto = protoFromName(protoElem.text)
    targetActions = targetProto.findall("protoaction")
    if len(targetActions) != 1:
        common.warn(f"Trail action for {proto.attrib['name']} has {targetActions} possible actions, unsure which to describe, ignored")
        return ""
    actionName = targetActions[0].find("name").text
    actionElem = findActionByName(targetProto, actionName)

    lifespan = f"{float(targetProto.find('lifespan').text):0.3g}"
    return f"Every {freq:0.3g}s while moving: leaves a trail which lasts {lifespan}s. {describeAction(targetProto, actionElem)}"

def handleSpawnAssistUnitAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    protoElem = protoFromName(action.find("projectile").text)
    projectileAttack = findActionByName(protoElem, "AssistAttack")
    projectileTactics = actionTactics(protoElem, projectileAttack)
    bounces = findFromActionOrTactics(projectileAttack, projectileTactics, "modifytargetlimit", 1, int)
    dist = findFromActionOrTactics(projectileAttack, projectileTactics, "maxrange", 1.0, float)
    healRate = findFromActionOrTactics(projectileAttack, projectileTactics, "modifymultiplier", 1.0, float)
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Fires a projectile which bounces between targets, hitting up to {bounces:0.3g} different targets. Each successive target can be no further from {dist:0.3g}m from the last. Upon returning to the user, they are healed for {100*healRate:0.3g}% of the total damage dealt. {actionDamageFull(proto, action, hideArea=True, ignoreActive=tech is not None)}"

def handleAreaRestrictAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    radius = findFromActionOrTactics(action, tactics, "damagearea", 0.0, float)
    duration = findFromActionOrTactics(action, tactics, "modifyduration", 0.0, float)/1000.0
    
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Creates a circular barrier with a {radius:0.3g}m radius for {duration:0.3g}s. Enemy units in the area are stunned for the duration. Non-flying units cannot pass the barrier. {actionRange(proto, action, True)} {actionRof(action)}"

def handleMaulAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    areaActionName = findFromActionOrTactics(action, tactics, "areaprotoaction", None)
    areaAction = ""
    if areaActionName is not None:
        areaActionElem = findActionByName(proto, areaActionName)
        areaAction = f"Additionally, hits nearby targets other than the primary victim for {actionDamageFull(proto, areaActionElem, ignoreActive=tech is not None)}"
    else:
        return ""
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Leaps onto a target. May be targeted at ground to bypass obstacles. Hits a primary target: {actionDamageFull(proto, action, hideArea=True, ignoreActive=tech is not None)} {areaAction}"

def handleBolsterAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    chargeds = action.findall("charged")
    chargedText = []
    for charged in chargeds:
        chargedText += handleChargeStructure(charged, ignoreConditionText=True)
    chargedText = common.attemptAllWordwiseTextMerges(chargedText, proto.attrib['name'])
    effects = ". ".join(chargedText)
    if len(effects) > 0:
        effects = effects[0].upper() + effects[1:]
        effects += "."
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Continually buffs the target until cancelled or killed. {effects} {actionRange(proto, action, True)}"


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
    increaseDecrease = "Increases"
    isArmor = False
    stat = findAndFetchText(action, "modifytype", None)
    mult = findAndFetchText(action, "modifymultiplier", None, float)
    targetunit = "unit of the same type"
    modifyprotoid = findAndFetchText(action, "modifyprotoid", None)
    if modifyprotoid is None:
        modifyprotoid = findAndFetchText(action, "modifyabstracttype", None)
    if modifyprotoid is not None:
        mult = findAndFetchText(action, f"./rate[@type='{modifyprotoid}']", None, float)
        targetunit = common.getDisplayNameForProtoOrClass(modifyprotoid)
    if mult is None:
        print(f"Info: LikeBonus for {proto.attrib['name']} seemingly has no modifymultiplier")
        return ""
    damageType = findAndFetchText(action, "modifydamagetype", None)
    if stat is None and damageType is not None:
        stat = f"{damageType} damage"
    elif stat == "ArmorSpecific":
        increaseDecrease = "Decreases" if mult > 0.0 else "Increases"
        stat = f"{damageType} vulnerability"
        isArmor = True
        
    mult *= 100
    area = findAndFetchText(action, "maxrange", None, float)
    targetLimit = findAndFetchText(action, "modifytargetlimit", None, int)
    relation = "other"
    if findAndFetchText(action, "targetenemy", 0, int) > 0:
        relation = "enemy"
    text = f"{increaseDecrease} {stat} by {mult:0.3g}% for each {relation} {targetunit} within {area:0.3g}m"
    if targetLimit is not None:
        text += f", to a maximum bonus of {targetLimit*mult:0.3g}% with {targetLimit} other group members"
    else:
        modifyRateCap = findAndFetchText(action, "modifyratecap", None, float)
        if modifyRateCap is not None:
            if isArmor:
                text += f", to a maximum bonus of {100*(modifyRateCap-1.0):0.3g}%"
            else:
                text += f", to a maximum bonus of {modifyRateCap:0.3g}%"
    return text + "."

def handleMaintainAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    killontrain = findFromActionOrTactics(action, tactics, "killontrain", None, int)
    trainpoints = findFromActionOrTactics(action, tactics, "maintaintrainpoints", None, float)
    modifytargetlimit = findFromActionOrTactics(action, tactics, "modifytargetlimit", None, int)
    modifybase = findFromActionOrTactics(action, tactics, "modifybase", None, int)
    maxrange = findFromActionOrTactics(action, tactics, "maxrange", None, float)
    spawnedObject = protoFromName(findAllFromActionOrTactics(action, tactics, "rate")[0].attrib['type'])
    targettype = common.getDisplayNameForProtoOrClass(spawnedObject)
    targettypePlural = common.getDisplayNameForProtoOrClassPlural(spawnedObject)
    sentences = []
    if modifybase:
        sentences.append(f"Produces {modifybase} {targettypePlural if modifybase > 1 else targettype} upon creation.")

    if killontrain:
        sentences.append(f"After {trainpoints:0.3g} seconds, dies and is replaced with a {targettype}.")
    else:
        sentences.append(f"Produces a {targettype} every {trainpoints:0.3g} seconds.")
    if modifytargetlimit and maxrange:
        sentences.append(f"Cannot begin production if there {'are' if modifytargetlimit > 1 else 'is'} already {modifytargetlimit} {targettypePlural if modifytargetlimit > 1 else targettype} within {maxrange:0.3g}m.")
    
    return " ".join(sentences)

def handleBurstHealAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rateNode = action.find("rate")
    healRate = f"{float(rateNode.text):0.3g}"
    items = [actionName, "Heals", actionTargetList(proto, action, tactics), f"{healRate} hitpoints instantly.", actionRange(proto, action, True), actionRof(action)]
    if chargeType != ActionChargeType.NONE:
        items.insert(1, rechargeRate(proto, action, chargeType, tech)+":")
    return f"{' '.join(items)}."

def handleInlineAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    if action.find("ismanualtransform") is not None:
        return handleDelayedTransformAction(proto, action, tactics, actionName, chargeType, tech)
    elif action.find("isabductdrop") is not None:
        return "May be commanded to drop abducted units instantly."
    
    common.warn_unhandled(f"Unknown Inline action on {proto.attrib['name']}")

    return ""

def handleLureAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    movespeed = findFromActionOrTactics(action, tactics, "targetedspeedmultiplier", 1.0, float)
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Lures in one targeted unit, making them uncontrollable and having them move in at {movespeed*100:0.3g}% speed. Once they are in melee range, they remain stunned and are attacked: {actionDamageFull(proto, action, damageMultiplier=0.5, ignoreActive=tech is not None)}".replace("  ", " ")

def handleConditionalTransformAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rule = action.find("conditionaltransformrule")
    modifyprotoid = findFromActionOrTactics(action, tactics, "modifyprotoid", None, str)
    skipmutatespawnevents = findFromActionOrTactics(action, tactics, "skipmutatespawnevents", 0, int)
    text = ""
    if rule.attrib['type'] == "NotIdle":
        text = f"Transforms into a {common.getDisplayNameForProtoOrClass(modifyprotoid)} if not idle."
    elif rule.attrib['type'] == "EnemyInRange":
        text = f"Transforms into a {common.getDisplayNameForProtoOrClass(modifyprotoid)} if any enemy {actionTargetList(proto, action, tactics)} are within {float(rule.text):0.3g}m."
    elif rule.attrib['type'] == "DamageTaken":
        text = f"Transforms into a {common.getDisplayNameForProtoOrClass(modifyprotoid)} if damaged."
    elif rule.attrib['type'] == "DamageDealt":
        text = f"Transforms into a {common.getDisplayNameForProtoOrClass(modifyprotoid)} upon dealing damage."
    else:
        common.warn_unhandled(f"Unknown ConditionalTransform rule {rule.attrib['type']} on {proto.attrib['name']}")
        return ""
    if not skipmutatespawnevents:
        targetProto = common.protoFromName(modifyprotoid)
        # Since this is currently used for only one thing, it is probably reasonable to hardcode like this for now
        # A more flexible approach would be to have it use the unit description for whatever it's spawning
        mutatespawn = targetProto.findall("spawn[@type='mutate']")
        if len(mutatespawn) > 0:
            text += " Transforming this way releases an explosion: "
        for spawn in mutatespawn:
            spawnedproto = common.protoFromName(spawn.text)
            text += selfDestructActionDamage(spawnedproto)
            text += "."
    return text


def handleDelayedTransformAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    text = f"Transforms into a {common.getObjectDisplayName(protoFromName(action.find('modifyprotoid').text))} "
    transformDuration = findAndFetchText(action, 'modifyduration', 0.0, float)/1000.0
    if transformDuration > 0.0:
        text += f"(takes {transformDuration:0.3g} seconds)."
    else:
        text += "instantly."
    items = [actionName, text]
    if proto.find("flag[.='CanAutoTransform']") is not None and chargeType == ActionChargeType.NONE:
        chargeType = ActionChargeType.REGULAR
    if chargeType != ActionChargeType.NONE:
        items.insert(1, rechargeRate(proto, action, chargeType, tech)+":")
    elif len(actionName) > 0:
        items[0] += ":"
    return " ".join(items)

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
        common.warn_unhandled(f"Unknown IdleStatBonus modify type {modifyType} for {proto.attrib['name']}")
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
    if distance is None:
        attackTime = None
    else:
        attackTime = distance/movespeed

    # Testing shows the RoF doesn't matter, but the total time is time in flight plus the entry and exit animations
    # For the nidhogg this is 3.24s
    targetList = actionTargetList(proto, action, tactics)
    if targetList == "":
        targetList = "objects"

    if attackTime is None:
        items = [actionName, rechargeRate(proto, action, chargeType, tech) +":", "Moves to the target, hitting", actionDamageFlagNames(action), targetList, f"within a {width:0.3g}m radius for approximately", actionDamageFull(proto, action, hideRof=True, hideArea=True, hideRange=True, ignoreActive=tech is not None)]
    else:
        items = [actionName, rechargeRate(proto, action, chargeType, tech) +":", "Hits", actionDamageFlagNames(action), targetList, f"in a {width:0.3g}x{distance:0.3g}m area for approximately", actionDamageFull(proto, action, damageMultiplier=attackTime, hideRof=True, hideArea=True, hideRange=True, ignoreActive=tech is not None)]

    if findFromActionOrTactics(action, tactics, "throw", 0, int):
        items.append("Targets in range at the end of the attack are launched into the air.")
    return f"{' '.join(items)}"

def handleDistanceModifyAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    maxSpeed = findAndFetchText(proto, "maxvelocity", 0.0, float)
    minSpeed = findAndFetchText(action, "minrate", 0.0, float) * maxSpeed
    speedDelta = maxSpeed - minSpeed
    maxRange = findAndFetchText(action, "maxrange", 0.0, float)
    minRange = findAndFetchText(action, "minrange", 0.0, float)
    rangeDelta = maxRange-minRange

    speedPerRange = speedDelta/rangeDelta

    return f"Once more than {minRange:0.3g}m from the Town Center it was spawned around, it starts to lose {10*speedPerRange:0.3g} speed per 10m travelled. Once it is more than {maxRange:0.3g}m away, its speed drops to the minimum of {minSpeed:0.3g}."


def handleChargeStructure(charged: ET.Element, ignoreConditionText=False):
    "This specifically handles the <charge> structure common to several action types like StackControl and ChargedModify."
    activationType = findAndFetchText(charged, "activationtype", None, str)
    ignoreDuration = findAndFetchText(charged, "duration", 1.0, float) < 2.0
    ignoreCooldown = findAndFetchText(charged, "cooldown", 1.0, float) < 2.0
    if activationType == "TerrainType":
        conditionText = "On " + findAndFetchText(charged, "terraintype", "unknown terrain change") + ": "
    elif activationType == "KillEnemy":
        conditionText = "On enemy kill: "
    elif activationType == "AfterAction":
        conditionText = "After usage: "
    elif activationType is None:
        conditionText = ""
    else:
        common.warn_unhandled(f"Charge structure has unknown activationtype {activationType}")
        conditionText = f"{activationType}:"
    
    if ignoreConditionText:
        conditionText = ""
    
    effectsList = []
    modifyElems = charged.findall("chargedmodify")
    for modifyElem in modifyElems:
        applyType = modifyElem.attrib['applytype']
        modifyType = modifyElem.attrib['modifytype']
        if applyType == "Multiply":
            applyTypeText = "multiplies {modifyType} by {amount}"
        elif applyType == "Add":
            applyTypeText = "adds {amount} to {modifyType}"
        elif applyType == "Set":
            applyTypeText = "sets {modifyType} to {amount}"
        else:
            common.warn_unhandled(f"Charge structure using unknown applytype {applyType}")
            continue
        amount = float(modifyElem.text)
        formatPercentage = False
        if modifyType == "Damage":
            modifyTypeText = "Damage"
        elif modifyType == "VisualScale":
            modifyTypeText = "Model Size"
            formatPercentage = True
        elif modifyType == "Speed":
            modifyTypeText = "Movement Speed"
        elif modifyType == "ROF":
            modifyTypeText = "Attack Interval"
        elif modifyType == "LifeSteal":
            modifyTypeText = "Lifesteal"
            formatPercentage = True
        elif modifyType == "ArmorSpecific":
            modifyTypeText = f"{modifyElem.attrib['param']} Vulnerability"
            if applyType != "Add":
                common.warn_unhandled(f"Charge structure on ArmorSpecific with unsupported applytype {applyType}")
                continue
            formatPercentage = True
            if amount > 0.0:
                applyTypeText = "reduces {modifyType} by {amount}"
            else:
                applyTypeText = "increases {modifyType} by {amount}"
                amount *= -1.0
        else:
            common.warn_unhandled(f"Charge structure using unknown modifytype {modifyType}")
            modifyTypeText = modifyType
        if formatPercentage:
            amountText = f"{100.0*amount:0.3g}%"
        else:
            amountText = f"{amount:0.3g}"
        if not ignoreDuration:
            applyTypeText += f" for {findAndFetchText(charged, "duration", 1.0, float):0.3g}s"
        if not ignoreCooldown:
            applyTypeText += f" ({findAndFetchText(charged, "cooldown", 1.0, float):0.3g}s cooldown)"
        thisEffect = conditionText + applyTypeText.format(amount=amountText, modifyType=modifyTypeText)
        thisEffect = thisEffect.strip()
        if len(thisEffect) > 0:
            effectsList.append(thisEffect)

    return effectsList

def handleStackControlAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    for search in (action, tactics):
        stackcontrolElem = search.find("stackcontrol")
        if stackcontrolElem is not None:
            break
    addActions = [findActionByName(proto, elem.text) for elem in stackcontrolElem.findall("stackaddaction")]
    removeActions = [findActionByName(proto, elem.text) for elem in stackcontrolElem.findall("stacksubaction")]
    stackMax = findAndFetchText(stackcontrolElem, "stackmax", None, int)
    
    addingActions = common.commaSeparatedList([getActionDisplayName(proto, actionName) for actionName in addActions])

    components = []
    components.append(f"Every usage of {addingActions} adds 1 stack.")
    if len(removeActions) > 0:
        components.append(f"Every usage of {common.commaSeparatedList([getActionDisplayName(proto, actionName) for actionName in removeActions])} requires and consumes 1 stack.")

    effectsList = []
    for actionElem in addActions:
        tacticsElem = actionTactics(proto, actionElem)
        chargedElems = actionElem.findall("charged")
        if tacticsElem is not None:
            chargedElems += tacticsElem.findall("charged")
        for charged in chargedElems:
            effectsList += handleChargeStructure(charged, ignoreConditionText=True)
            
    if len(effectsList) > 0:
        components.append(f"Each stack {common.commaSeparatedList(effectsList)}. Successive multiplications are applied on top of the previous stacked value, resulting in exponential growth.")

    if stackMax is not None:
        components.append(f"Max {stackMax} stacks, at which point {addingActions} cannot be used.")
    
    return " ".join(components)

def handleChargedModifyAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    chargedElems = action.findall("charged")
    if tactics is not None:
        chargedElems += tactics.findall("charged")
    effectsList = []
    for chargeElem in chargedElems:
        effectsList += handleChargeStructure(chargeElem)
    if len(effectsList) == 0:
        return ""
    return (". ".join(effectsList)) + "."


MODIFY_TYPE_DISPLAY = {
    "Armor":"Damage Vulnerability",
    "MaxHP":"Max Hitpoints",
    "Speed":"Movement Speed",
    "BuildRate":"Build Speed",
    "MilitaryTrainingCost":"Military Unit Cost",
    "ROF":"Attack Interval",
}

def getAllowForbidTargetTypes(action: ET.Element, tactics: ET.Element) -> Tuple[List[str], List[str]]:
    allowedTargetTypes = [x.text for x in findAllFromActionOrTactics(action, tactics, "modifyabstracttype")+findAllFromActionOrTactics(action, tactics, "modifyunittype")]
    forbidTargetTypes = [x.text for x in findAllFromActionOrTactics(action, tactics, "forbidabstracttype")+findAllFromActionOrTactics(action, tactics, "forbidunittype")]
    return (allowedTargetTypes, forbidTargetTypes)


def handleAutoRangedModifyAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None, isInfection=False):
    modifyType = findFromActionOrTactics(action, tactics, "modifytype", None)
    if modifyType is None:
        return ""
    
    # Silence god-specific effects, since they probably shouldn't be noted everywhere
    if tech is None:
        modifyCiv = findFromActionOrTactics(action, tactics, "modifyciv", None)
        if modifyCiv is not None:
            return ""

    components = []
    lateComponents = []
    if len(actionName):
        components.append(f"{actionName}:")

    range = findFromActionOrTactics(action, tactics, "maxrange", None, float)
    
    if isInfection:
        infectionRange = findFromActionOrTactics(action, tactics, "infectionrange", None, float)
        if infectionRange is not None:
            range = infectionRange

    if range is None:
        return ""

    restrictempowered = findFromActionOrTactics(action, tactics, "restrictifempowered", None, int)
    restrictempowertype = findFromActionOrTactics(action, tactics, "restrictempowertype", None, str)
    if restrictempowertype is not None:
        restrictProto = protoFromName(restrictempowertype)
        if restrictProto is not None:
            empowerer = common.getObjectDisplayName()
        else:
            empowerer = common.getDisplayNameForProtoOrClass(restrictempowertype) # KeyError if a missing unit class
        components.append(f"If empowered by a {empowerer},") 
    elif restrictempowered:
        components.append(f"If empowered, ")
    

    modifyrangeuselos = findFromActionOrTactics(action, tactics, "modifyrangeuselos", None, int)
    if modifyrangeuselos is not None and modifyrangeuselos > 0:
        components.append(f"Projects an aura over its LOS which")
    else:
        components.append(f"Projects a {range:0.3g}m aura which")
    
    if len(components) > 1:
        components[-1] = "p" + components[-1][1:]

    modifyTargetLimit = findFromActionOrTactics(action, tactics, "modifytargetlimit", None, int)
    skipStacking = False

    if modifyType == "HealRate":
        damageType = findFromActionOrTactics(action, tactics, "modifydamagetype", "Divine")
        damageAmount = findFromActionOrTactics(action, tactics, "modifyamount", None, float)
        if damageAmount < 0.0:
            components.append(f"deals {icon.damageTypeIcon(damageType)} {damageAmount*-1:0.3g}")
            components.append(actionDamageBonus(action))
            components.append("per second to")
        elif damageAmount > 0.0:
            components.append(f"heals {damageAmount:0.3g} hitpoints per second to")
            slowHealMultiplier = findFromActionOrTactics(action, tactics, "slowhealmultiplier", 1.0, float)
            if modifyTargetLimit is not None:
                lateComponents.append(f"Heals up to {modifyTargetLimit} target{'s' if modifyTargetLimit > 1 else ''} at once.")
            if slowHealMultiplier != 1.0:
                lateComponents.append(f"Targets that have moved or been involved in combat in the last 3 seconds are healed at {slowHealMultiplier*100:0.3g}% speed.")
    elif modifyType in ("Damage", "Armor", "MaxHP", "Speed", "BuildRate", "MilitaryTrainingCost", "ROF"):
        multiplier = findFromActionOrTactics(action, tactics, "modifymultiplier", None, float)
        if multiplier is None:
            common.warn_data(f"RangedModify on {proto.attrib['name']} is missing modifymultiplier, ignored")
            return ""
        modifyTypeName = MODIFY_TYPE_DISPLAY.get(modifyType, modifyType)
        if modifyType in ("Armor"):
            multiplier = 1.0 + (1.0-multiplier)
        if multiplier > 1.0:
            components.append(f"increases {modifyTypeName} by {100*(multiplier-1.0):0.3g}% for")
        elif multiplier < 1.0:
            components.append(f"decreases {modifyTypeName} by {-100*(multiplier-1.0):0.3g}% for")
    elif modifyType == "RevealUI":
        components.append("allows you to check the actions/garrison of")
        skipStacking = True
    elif modifyType == "AuraEmpower":
        components.append(f"{handleEmpowerAction(proto, action, tactics, '', chargeType)} Affects")
    elif modifyType == "ArmorSpecific":
        multiplier = findFromActionOrTactics(action, tactics, "modifyamount", None, float)
        armorType = findFromActionOrTactics(action, tactics, "modifydamagetype", None, str)
        if multiplier > 1.0:
            components.append(f"decreases {armorType} vulnerability by {100*(multiplier-1.0):0.3g}% for")
        elif multiplier < 1.0:
            components.append(f"increases {armorType} vulnerability by {-100*(multiplier-1.0):0.3g}% for")
    elif modifyType in ["GatherRateMultiplier", "GatherRate"]:
        multiplier = findFromActionOrTactics(action, tactics, "modifymultiplier", None, float)
        components.append(f"increases gather rate of {{targets}} by {(multiplier-1.0)*100:0.3g}%.")
    elif modifyType in ["ResourceGatherRate"]:
        multiplier = findFromActionOrTactics(action, tactics, "modifyamount", None, float)
        components.append(f"increases gather rate of {{targets}} by {multiplier*100:0.3g}%.")
    elif modifyType == "DamageByTargetType":
        victimTargetType = common.getDisplayNameForProtoOrClassPlural(findFromActionOrTactics(action, tactics, "modifydamagetargettype", None))
        multiplier = findFromActionOrTactics(action, tactics, "modifyamount", None, float)
        components.append(f"multiplies the damage of {{targets}} against {victimTargetType} by {multiplier:0.3g}x.")
    elif modifyType == "PopCapBonus":
        # Remove "projects a X m aura that..."
        components = components[:-1]
        amount = findFromActionOrTactics(action, tactics, "modifyamount", None, int)
        targetLimit = findFromActionOrTactics(action, tactics, "modifytargetlimit", None, int)
        components.append(f"Increases population cap by {amount} for each of {{targets}}")
        if targetLimit is not None:
            components.append(f"(max {targetLimit})")
        components.append(f"within {range:0.3g}m.")
        skipStacking = True
    else:
        common.warn_unhandled(f"Unknown AutoRangedModify type {modifyType} for {proto.attrib['name']}")
        return ""

    playerRelation = ["your"]

    if findFromActionOrTactics(action, tactics, "modifyciv", ""):
        playerRelation = [findFromActionOrTactics(action, tactics, "modifyciv", "") +"'s"]
    elif findFromActionOrTactics(action, tactics, "targetenemy", ""):
        playerRelation = ["enemy"]
    elif findFromActionOrTactics(action, tactics, "targetenemyincludenature", ""):
        playerRelation = ["nature", "enemy"]
    elif findFromActionOrTactics(action, tactics, "targetnonally", ""):
        playerRelation = ["non-allied"]
    elif findFromActionOrTactics(action, tactics, "includeally", ""):
        playerRelation = ["your", "allied'"]

    # This is a huge assumption about how infection works
    if isInfection:
        playerRelation = [entry.replace("enemy", "friendly") for entry in playerRelation]

    if findFromActionOrTactics(action, tactics, "modifyself", 0, int) > 0:
        playerRelation.insert(0, "itself")
    elif isInfection and findFromActionOrTactics(action, tactics, "modifyselfifinfection", 0, int):
        playerRelation.insert(0, "itself")

    
    targetListComponents = []
    targetListComponents.append(common.commaSeparatedList(playerRelation))

    if findFromActionOrTactics(action, tactics, "targetunbuilt", ""):
        targetListComponents.append("unfinished")

    allowedTargetTypes, forbidTargetTypes = getAllowForbidTargetTypes(action, tactics)
    if findFromActionOrTactics(action, tactics, "modifyflyingunits", 0, int) == 0:
        forbidTargetTypes.append("AbstractFlyingUnit")
    targetListComponents.append(targetListToString(allowedTargetTypes, forbidTargetTypes))

    targetText = " ".join(targetListComponents)

    doneReplacement = False
    for i, component in enumerate(components):
        if "{targets}" in component:
            components[i] = component.replace("{targets}", targetText)
            doneReplacement = True
    if not doneReplacement:
        components.append(targetText)
        components[-1] += "."

    if isInfection:
        components.append("A unit can only have one infection at a time.")

    components += lateComponents

    
    if not skipStacking:
        if findFromActionOrTactics(action, tactics, "nostack", 0, int) == 0:
            stacklimit = findFromActionOrTactics(action, tactics, "modifystacklimit", 0, int)
            if stacklimit > 0:
                components.append(f"Stacks with itself up to {stacklimit} times.")
            else:
                components.append("Stacking.")
        else:
            components.append("Does not stack.")

    if findFromActionOrTactics(action, tactics, "suspendbyattack", 0, int) > 0:
        components.append("Deactivated when attacking.")

    if not isInfection and findFromActionOrTactics(action, tactics, "infectionchance") is not None:
        infectionProbability = findFromActionOrTactics(action, tactics, "infectionchance", 0.0, float) * findFromActionOrTactics(action, tactics, "infectionrof", 0.0, float) * 1.0/1000.0
        infectionDuration = findFromActionOrTactics(action, tactics, "infectionduration", 0.0, float)/1000.0
        if infectionProbability > 0.0 and infectionDuration > 0.0:
            infectionComponent = f"Has a {100*infectionProbability:0.3g}% chance per second to infect for {infectionDuration:0.3g}s: {handleAutoRangedModifyAction(proto, action, tactics, "", isInfection=True)}"
            components.append(infectionComponent)

    components = [component.strip() for component in components if len(component.strip()) > 0]
    joined = " ".join(components)
    if not joined.endswith("."):
        joined += "."

    if isInfection:
        protoName = proto.attrib['name']
        override = unitdescription.unitDescriptionOverrides.get(protoName, None)
        protoNameToLookup = override.infectionEffectParent or protoName
        if override is not None:
            if override.generaliseInfectionEffects:
                if protoNameToLookup not in UNIT_INFECTION_TEXT or joined == UNIT_INFECTION_TEXT[protoNameToLookup]:
                    UNIT_INFECTION_TEXT[protoName] = joined
                    joined = "See below."


    return joined

GATHER_ICONS: Dict[str, Union[str, None]] = {
    "WoodResource":icon.resourceIcon("wood"),
    "GoldResource":icon.resourceIcon("gold"),
    "Herdable":icon.generalIcon(r"resources\nature\animals\land\goat_icon.png"),
    "Huntable":icon.generalIcon(r"resources\nature\animals\land\deer_icon.png"),
    "NonConvertableHerdable":icon.generalIcon(r"resources\nature\animals\land\chicken_icon.png"),
    "BerryBush":icon.generalIcon(r"resources\nature\berry_bush_icon.png"),
    "AbstractFarm":icon.generalIcon(r"resources\shared\static_color\buildings\farm_icon.png"),
    "FishResource":icon.generalIcon(r"resources\nature\animals\naval\fish_icon.png"),
    "Temple":None,
    "AbstractTemple":None,
    "Taproot":None,
    "Resource":None,
    "HerdableMagnet":None,
}

# Peach blossom rates are expected to be the same as the villager's base rate for these standard targets
PEACH_BLOSSOM_ALT_TARGETS = {
    "Food":"Huntable",
    "Wood":"WoodResource",
    "Gold":"GoldResource",
}

def handleGatherAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rateElems = action.findall("rate")
    items = []
    for index, rateElem in enumerate(rateElems):
        target = rateElem.attrib['type']
        rate = float(rateElem.text)
        thisIcon = GATHER_ICONS.get(target, None)
        if target not in GATHER_ICONS:
            # Peach blossom spring: only notable if different rate to base hunt/wood/gold
            if target == "ThePeachBlossomSpring":
                targetRes = rateElem.attrib['resource']
                standardTarget = PEACH_BLOSSOM_ALT_TARGETS[targetRes] # will KeyError on undefined resource
                standardRate = findAndFetchText(action, f"rate[@type='{standardTarget}']", None, float)
                if rate != standardRate:
                    #raise ValueError(f"Peach blossom spring for {targetRes} on {proto.attrib['name']} doesn't match standard target {standardTarget} rate: {rate} vs standard {standardRate}")
                    common.warn_data(f"Mismatched Peach blossom spring for {targetRes} on {proto.attrib['name']} doesn't match standard target {standardTarget} rate: {rate} vs standard {standardRate}")
                    items.append(f"{targetRes} (from Peach Blossom): {rate}")
            elif target == "AbstractShrineJapanese":
                mikoBaseRate = findAndFetchText(findActionByName("Miko", "GatherShrine"), "rate[@type='AbstractShrineJapanese']", 0.0, float)
                thisMultiplier = rate/mikoBaseRate
                if thisMultiplier == 1.0:
                    items.append(f"Shrine Favor: {rate:0.3g} plus contribution from resources in range")
                else:
                    items.append(f"Shrine Favor: {rate:0.3g} plus {thisMultiplier:0.3g}x displayed contribution from resources in range")
            else:
                common.warn_unhandled(f"Unknown gather action target on {proto.attrib['name']}: {target}")
                return ""
        
        if thisIcon is None:
            continue
        items.append(f"{thisIcon} {rate:0.3g}")

    if len(items) == 0:
        return ""
    
    itemsPerLine = 5
    linePrefix = f"\\n   {icon.BULLET_POINT_ALT}"
    numLines = math.ceil(len(items)/itemsPerLine)
    
    out = "Gather rates:"
    for lineIndex in range(0, numLines):
        out += linePrefix + " ".join(items[lineIndex*itemsPerLine:lineIndex*itemsPerLine + itemsPerLine])
            
    return out


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
    "Gather":handleGatherAction,
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
    "IdleStatBonusVFX":handleIdleStatBonusAction,
    "Spawn":handleSpawnAction,
    "LinearAreaAttack":handleLinearAreaAttackAction,
    "AutoRangedAttach":handleAutoRangedAttachAction,
    "DistanceModify":handleDistanceModifyAction,
    "StackControl":handleStackControlAction,
    "ChargedModify":handleChargedModifyAction,
    "Rampage":handleRampageAction,
    "ReleaseSkyLantern":handleReleaseSkyLanternAction,
    "Convert":handleConvertAction,
    "Trail":handleTrailAction,
    "SpawnAssistUnit":handleSpawnAssistUnitAction,
    "AreaRestrict":handleAreaRestrictAction,
    "Maul":handleMaulAction,
    "Bolster":handleBolsterAction,
    "AreaMutate":handleAreaMutateAction,
    
    "JumpAttack":simpleActionHandler("Leaps over obstacles on the way to the target."),
    "Attack":simpleActionHandler(),
    "RangedAttack":simpleActionHandler(),
    "ChainAttack":simpleActionHandler(),
    "AutoBoost":simpleActionHandler(),
    "TeleportAttack":simpleActionHandler("Teleports to the target. May be used manually without a target to bypass obstacles such as walls."),
    "ReflectAttack":handleReflectAttackAction,
    "Inline":handleInlineAction,
    "Abduct":handleAbductAction,
    "ConditionalTransform":handleConditionalTransformAction,
    "Lure":handleLureAction,
}

def actionDamageFlagNames(action: ET.Element):
    flags = action.find("damageflags")
    if flags is None:
        actionType = common.findAndFetchText(action, "type", None, str)
        if action.find("damagearea") is not None and actionType != "Rampage":
            split = ["Enemy", "Self", "Ally", "Nature"]
        else:
            return ""
    else:
        split = set(flags.text.split("|"))

    if "Nature" in split:
        split.remove("Nature")
    if "Enemy" in split and "Self" in split and "Ally" in split:
        return "all players'"
    if "Self" in split and "Ally" in split:
        split.remove("Self")
        split.remove("Ally")
        split.add("your and allied")
    return common.commaSeparatedList(list(split)).lower()

def selfDestructActionDamage(proto: Union[str, ET.Element]):
    action = findActionByName(proto, "SelfDestructAttack")
    if action is not None:
        damageOnly = actionDamageOnly(proto, action)
        if damageOnly == "":
            return ""
        return f"{damageOnly} {actionDamageBonus(action)} to {actionDamageFlagNames(action)} objects within {actionArea(action)}"
    return ""

def getCommonAbilitiesNodeForPowerName(powerName: str) -> Union[None, ET.Element]:
    abilityInfo = globals.dataCollection["abilities_combined"].find(f"power[@name='{powerName}']")
    if abilityInfo is None:
        # The game apparently uses case insensitive matching here - but lowercasing everything will cause issues the moment it doesn't somewhere!
        for power in globals.dataCollection["abilities_combined"]:
            if power.attrib["name"].lower() == powerName.lower():
                abilityInfo = power
                break
    return abilityInfo

def getCivAbilitiesNode(proto: Union[ET.Element, str], action: Union[ET.Element, str], forceAbilityLink: Union[str, None]=None):
    """Returns the [civ].abilities <power> XML element corresponding to a given protounit's action, or None if one wasn't found.
    
    If forceAbilityLink is provided, ignores the above and instead return a <power name=forceAbilityLink> element, or None if nonexistent."""
    if isinstance(proto, str):
        proto = common.protoFromName(proto)
    if isinstance(action, str):
        action = findActionByName(proto, action)
    tactics = actionTactics(proto, action)
    actionInternalName = findFromActionOrTactics(action, tactics, "name", None)
    actionAnimName = findFromActionOrTactics(action, tactics, "anim", None, str)
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
                abilityInfo = getCommonAbilitiesNodeForPowerName(abilityNode.text)
                if abilityInfo is None:
                    common.warn_data(f"{proto.attrib['name']}'s {common.findAndFetchText(action, "name", "???", str)} has an abilities.xml entry but couldn't find a corresponding civ.abilities")
                    continue
                unitAction = findAndFetchText(abilityInfo, "unitaction", None)
                if unitAction == actionInternalName or (actionAnimName is not None and unitAction == actionAnimName):
                    break
                abilityInfo = None
    return abilityInfo

def getActionDisplayName(proto: Union[ET.Element, str], action: Union[ET.Element, str], forceAbilityLink: Union[str, None]=None, nameNonChargeActions=False):
    if isinstance(proto, str):
        proto = common.protoFromName(proto)
    if isinstance(action, str):
        actionObj = findActionByName(proto, action)
    actionName = ""
    actionInternalName = findAndFetchText(action, "name", None)
    unitOverride = unitdescription.unitDescriptionOverrides.get(proto.attrib['name'], None)
    if unitOverride is not None:
        override = unitOverride.actionNameOverrides.get(actionInternalName, None)
        if override is not None:
            return override

    abilityInfo = getCivAbilitiesNode(proto, action, forceAbilityLink)

    if abilityInfo is not None:
        actionName = common.getObjectDisplayName(abilityInfo)
        if actionName is None:
            common.warn(f"No name for charge action {actionInternalName} -> on {proto.get('name')}")
            actionName = actionInternalName
    if len(actionName) == 0 and nameNonChargeActions:
        actionName = ACTION_TYPE_NAMES.get(actionInternalName, actionInternalName)

    return actionName


def describeAction(proto: Union[str, ET.Element], action: Union[str, ET.Element], chargeType: ActionChargeType=ActionChargeType.NONE, nameOverride: Union[str, None] = None, forceAbilityLink: Union[str, None] = None, overrideText: Union[str, None]=None, tech: Union[ET.Element, None]=None):
    if isinstance(proto, str):
        proto = common.protoFromName(proto)
    if isinstance(action, str):
        action = findActionByName(proto, action)
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
    #if chargeType != ActionChargeType.NONE:
    if abilityInfo is None and chargeType != ActionChargeType.NONE:
        print(f"Info: No abilities.xml entry found for {proto.attrib['name']} but it has a charge action {actionInternalName}")
    if nameOverride is not None:
        actionName = nameOverride
    else:
        # Name: charged actions
        # and Non charged actions which are associated with an ability
        # ... but that aren't passive (needs to have an anim or unitaction entry)
        # Naming passives redundantly repeats the ability name in the tooltip which is pointless
        fetchName = chargeType != ActionChargeType.NONE
        if abilityInfo is not None:
            if abilityInfo.find("anim") is not None or abilityInfo.find("unitaction") is not None:
                fetchName = True
        if fetchName:
            actionName = getActionDisplayName(proto, action, forceAbilityLink, nameNonChargeActions=True)
        
    result = ""
    handler = ACTION_TYPE_HANDLERS.get(actionInternalName, ACTION_TYPE_HANDLERS.get(actionInternalType, None))
    if handler is None:
        common.warn_unhandled(f"No handler for action: internal type={actionInternalType}; action name={actionInternalName}; display name={actionName}; on {proto.get('name')}")
        #result = f"Unknown: {actionName} - {actionInternalName} - {actionInternalType}"
    else:
        result = handler(proto, action, actionTactics(proto, action), actionName, chargeType, tech)
        result = common.collapseSpaces(result)
        result = result.replace("..", ".")
        result = result.replace(" :", ":")
        if overrideText is not None:
            result = overrideText
        if abilityInfo is not None and proto.attrib["name"] not in common.PROTOS_TO_IGNORE_FOR_ABILITY_TOOLTIPS:
            resultForAbility = result[:]
            # If the description starts with the ability name, don't repeat it in the ability version of the tooltip
            if resultForAbility.startswith(actionName):
                resultForAbility = resultForAbility[len(actionName):].strip()
                if resultForAbility.startswith(":"):
                    resultForAbility = resultForAbility[1:].strip()
            common.addToGlobalAbilityStrings(proto, abilityInfo, resultForAbility)
        
        
    return result

#@functools.cache
def getAnimFileSectionsForProtoAction(proto: Union[str, ET.Element], action: Union[str, ET.Element]) -> List[ET.Element]:
    proto = common.protoFromName(proto)
    action = findActionByName(proto, action)
    tactics = actionTactics(proto, action)
    targetActionName = findFromActionOrTactics(action, tactics, "anim", None)
    if targetActionName is None:
        targetActionName = findFromActionOrTactics(action, tactics, "name", None)
    if targetActionName is None:
        print(f"Unable to find target action name for {proto.attrib['name']} action {action} with type {findFromActionOrTactics(action, tactics, "type", None)}")
        return None
    animFile = proto.find("animfile")
    if animFile is None:
        print(f"Unable to find target animfile for {proto.attrib['name']}")
        return None
    animFile = animFile.text

    animFileSection = globals.dataCollection["simdata.xml"].findall(f"animxml[@file='{animFile}']")
    if len(animFileSection) != 1:
        common.warn_unhandled(f"Found {len(animFileSection)} animfile sections for {proto.attrib['name']}'s {targetActionName}, expected exactly 1")
        return None
    
    animMatches = animFileSection[0].findall(f"animations/animinfo[name='{targetActionName}']")
    if len(animMatches) < 1:
        #print(f"Unable to get any anim match for {proto.attrib['name']}'s {targetActionName}")
        return None
    return animMatches

def getActionAttackCount(proto: Union[str, ET.Element], action: Union[str, ET.Element]):
    "Return the number of times a given action makes attack tag attempts in its animation data."
    proto = common.protoFromName(proto)
    action = findActionByName(proto, action)
    tactics = actionTactics(proto, action)
    animMatches = getAnimFileSectionsForProtoAction(proto, action)
    if animMatches is None:
        return 1
        
    versionCounts = []
    for animMatch in animMatches:
        versions = animMatch.findall("versions/version")
        for version in versions:
            versionCounts.append(len(version.findall("tags/tag[type='Attack']")))

    if len(versionCounts) == 0:
        common.warn_data(f"Found no attack tags for {proto.attrib['name']}'s {findFromActionOrTactics(action, tactics, 'name')}")
        return 1

    versionCounts = list(set(versionCounts))
    if len(versionCounts) != 1:
        targetActionName = findFromActionOrTactics(action, tactics, "anim", None)
        if targetActionName is None:
            targetActionName = findFromActionOrTactics(action, tactics, "name", None)
        common.warn_data(f"Warning: {proto.attrib['name']}'s {targetActionName} appears to have variable number of attacks: {versionCounts}")
    return max(1, int(sum(versionCounts)/len(versionCounts)))

@dataclasses.dataclass
class AnimationAttackPositionInfo:
    # The "natural" length of this animation, not including any rof tags of actions that call it
    length: float = 0.0
    # The position(s) in seconds at which attack(s) are made, if any
    attackPositions: List[float] = dataclasses.field(default_factory=list)


def getActionAttackPointTimesInAnimation(proto: Union[str, ET.Element], action: Union[str, ET.Element]) -> List[AnimationAttackPositionInfo]:
    """For a given proto/action, returns the time(s) in the animation at which attacks are made assuming the animation is played at its "natural" speed (and not changed by rof on the action itself).
    Returns one AnimationAttackPositionInfo instance per animation found, these may or may not be functional duplicates of each other.
    May return an empty list if no animations were found."""

    animMatches = getAnimFileSectionsForProtoAction(proto, action)
    if animMatches is None:
        return []

    out = []

    for animMatch in animMatches:
        versions = animMatch.findall("versions/version")
        for version in versions:
            length = common.findAndFetchText(version, "duration", None, float)
            if length is None:
                continue
            # Pretty basic testing says that the attack tag is already the percentage, need to convert to actual time
            attackPositions = [length*float(elem.text) for elem in version.findall("tags/tag[type='Attack']/position")]
            out.append(AnimationAttackPositionInfo(length=length, attackPositions=attackPositions))
    
    return out