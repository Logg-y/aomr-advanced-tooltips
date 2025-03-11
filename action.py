import enum
import common
from common import findAndFetchText, protoFromName
import icon
import globals
from xml.etree import ElementTree as ET
from typing import Union, Dict, List, Callable, Any, Type
import math
import copy
import re
import unitdescription

class ActionChargeType(enum.Enum):
    NONE = 0
    REGULAR = 1
    AUX = 2

STANDARD_SNARE = {"rate":0.85, "duration":2.0}

# Writing out identical infection text for each action creates a lot of redundant text
# It makes much more sense to do it once per unit, and then list it at the end...
UNIT_INFECTION_TEXT = {}


SUPPRESS_TARGET_TYPES = (
    "All",
    "LogicalTypeHandUnitsAttack",
    # The guardians mess up SoO's heal action.
    "GuardianSleeping",
    "GuardianSleepingTNA",
    "Football",
    # Also a valid heal action target
    "TitanGateSPC",
    "MonumentToVillagersSPC",
    "MonumentToPriestsSPC",
    "MonumentToPharaohsSPC",
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
    if action is not None:
        results += action.findall(query)
    if tactics is not None:
        results += tactics.findall(query)
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
        
def actionDamageOnly(proto: ET.Element, action: ET.Element, isDPS=False, hideRof=False, hideNumProjectiles=False, damageMultiplier=1.0):
    damages = []
    # If showing number of projectiles, don't multiply up damage - else it'll suggest you're shooting 6 projectiles each at 6x damage or whatever.
    mult = damageMultiplier * actionDamageMultiplier(proto, action, isDPS=isDPS, ignoreNumProjectiles=not hideNumProjectiles)

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
    if not isDPS:
        if not hideRof:
            damages.append(actionRof(action))
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
        print(f"Warning: {proto.attrib['name']}'s action {getActionName(proto, action, nameNonChargeActions=True)} has projectile count mismatch: data reports {simdataAttackCount} (simdata.simjson attack count) with {numProjectilesFromData} each (proto numprojectiles), but {displayedNumProjectiles} from UI")
    if not format:
        return numProjectiles
    if numProjectiles == 1:
        return ""
    numProjectiles = int(numProjectiles)
    return f"{icon.iconNumProjectiles()} x{numProjectiles}"

def actionRof(action: ET.Element):
    rof = findAndFetchText(action, "rof", 1.0, float)
    return f"{icon.iconRof()} {rof:0.3g}"


def actionDamageMultiplier(proto: ET.Element, action: ET.Element, isDPS=True, ignoreNumProjectiles=False):
    rof = findAndFetchText(action, "rof", 1.0, float)
    if not isDPS:
        rof = 1.0
    if ignoreNumProjectiles:
        numProjectiles = 1
    else:
        numProjectiles = actionNumProjectiles(proto, action, format=False)
    
    rof /= numProjectiles
    return 1.0/rof
    

def actionDamageFull(protoUnit: ET.Element, action: ET.Element, isDPS=False, hideArea=False, damageMultiplier=1.0, hideRof=False, hideRange=False, ignoreActive=False, hideDamageBonuses=False):
    # Scorpion man special attack has displayed num projectiles but no actual projectiles
    # I think it makes 3 little attacks and this is how the developers opted to represent that
    # but it'd be much less confusing to multiply these out for the tooltip
    hideNumProjectiles = False
    numProjectiles = actionNumProjectiles(protoUnit, action, format=False)
    hasProjectile = findAndFetchText(action, "projectile", None) is not None
    if not hasProjectile or isDPS:
        hideNumProjectiles = True
    components = [actionDamageOnly(protoUnit, action, isDPS, hideRof=hideRof, damageMultiplier=damageMultiplier, hideNumProjectiles=hideNumProjectiles)]
    if not hideArea:
        components.append(actionArea(action, True))
    if not hideDamageBonuses:
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

def onhiteffectTargetString(onhiteffect: ET.Element, hitword="hit", default="targets", additionalHitTargets: Union[str, None, List[str]]=None):
    targetElems = onhiteffect.findall("target")
    targetTypes = []
    ignoreTypes = []
    if additionalHitTargets is not None:
        if isinstance(additionalHitTargets, str):
            targetTypes.append(additionalHitTargets)
        else:
            targetTypes += additionalHitTargets
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

def actionDamageOverTime(proto: ET.Element, action: ET.Element, isDPS=False, damageMultiplier=1.0):
    dots = action.findall("onhiteffect[@type='DamageOverTime']")
    dur = None
    targetType = None
    damages = ""
    prob = None
    mult = damageMultiplier * actionDamageMultiplier(proto, action, isDPS=isDPS)
    for dot in dots:
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
    }

    simpleModifyTypeFormatAmounts = {
        "LifeSteal": lambda amt: f"{amt*100:0.3g}%"
    }

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
        armorMods = []
        armorModsFinal = []
        otherEffects = []
        needMentionDecay = False
        for child in effectGroup:
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
            if child.attrib["type"] == "ArmorSpecific":
                if amountInitial > 1.0:
                    armorMods.append(f"{icon.armorTypeIcon(child.attrib['dmgtype'].lower())} -{(amountInitial-1)*100:0.3g}%")
                else:
                    armorMods.append(f"{icon.armorTypeIcon(child.attrib['dmgtype'].lower())} +{(amountInitial-1)*-100:0.3g}%")
                if amountFinal is not None:
                    if amountFinal > 1.0:
                        armorModsFinal.append(f"{icon.armorTypeIcon(child.attrib['dmgtype'].lower())} -{(amountFinal-1)*100:0.3g}%")
                    else:
                        armorModsFinal.append(f"{icon.armorTypeIcon(child.attrib['dmgtype'].lower())} +{(amountFinal-1)*-100:0.3g}%")
            elif child.attrib["type"] == "ForcedTarget":
                text = f"forces victims to attack the user"
                otherEffects.append(text)
            elif child.attrib["type"] == "Chaos":
                otherEffects.append(f"victims become uncontrollable and attack anything nearby")
            elif child.attrib["type"] in simpleModifyTypeToDisplayStrings:
                displayString = simpleModifyTypeToDisplayStrings[child.attrib['type']]
                applyType = child.attrib.get("applytype", "multiply").lower()
                amountFormatter = simpleModifyTypeFormatAmounts.get(child.attrib['type'], lambda amt: f"{amt:0.3g}")

                if applyType == "multiply":
                    text = f"{amountFormatter(amountInitial)}x {displayString}"
                    if amountFinal is not None and amountFinal != 1.0:
                        text += f" (decays to {amountFormatter(amountFinal)}x over the duration)"
                    if amountFinal == 1.0:
                        needMentionDecay = True
                    
                    
                elif applyType == "add":
                    text = f"{'+' if amountInitial > 0 else '-'}{amountFormatter(amountInitial)} {displayString}"
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
        if len(armorMods):
            thisItem += f" Modifies damage vulnerabilities by {' '.join(armorMods)}."
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

def actionOnHitNonDoTEffects(proto: ET.Element, action: ET.Element, ignoreActive=False, filterOnHitTypes=None):
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
                print(f"Warning: {proto.attrib['name']} attempts to apply infection action of type {infectionActionType}, no handling for this")
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
                    print(f"Warning: Mixed onhit effect probability nodes for {proto.attrib['name']}")
                elif probValue is None:
                    probValue = thisProb
        if probValue is not None:
            probText = f"{probValue:0.3g}% chance: "
        if onhitType == "Throw":
            onhitGroups = groupUpNearIdenticalElements(nodes, "targetunittype")
            for group in onhitGroups:
                additionalTargets = [elem.attrib['targetunittype'] for elem in group[1:] if 'targetunittype' in elem]
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
                additionalTargets = [elem.attrib['targetunittype'] for elem in group[1:] if 'targetunittype' in elem]
                targetTypeString = onhiteffectTargetString(group[0], additionalHitTargets=additionalTargets)
                dur = float(group[0].attrib['duration'])
                text = f"{probText}Stuns {targetTypeString} for {dur:0.3g} {'second' if dur == 1.0 else 'seconds'}."
            items.append(text)
        elif onhitType == "Pull":
            onhitGroups = groupUpNearIdenticalElements(nodes, "targetunittype")
            for group in onhitGroups:
                additionalTargets = [elem.attrib['targetunittype'] for elem in group[1:] if 'targetunittype' in elem]
                targetTypeString = onhiteffectTargetString(group[0], additionalHitTargets=additionalTargets)
                text = f"{probText}Pulls {targetTypeString} slightly closer."
            items.append(text)
        elif onhitType in ("StatModify", "SelfModify", "Boost"):
            onhitGroups = groupUpNearIdenticalElements(nodes, "targetunittype")
            for group in onhitGroups:
                additionalTargets = [elem.attrib['targetunittype'] for elem in group[1:] if 'targetunittype' in elem]
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
        notes.append(f"Beam attack strikes up to {int(bounces.text)-1} additional targets.")
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

def actionTargetList(action: ET.Element, tactics: Union[None, ET.Element]):
    unitList = []
    disallowedList = []
    for root in action, tactics:
        if root is None:
            continue
        rates = root.findall("rate")
        unitList += filter(lambda elem: float(elem.text) > 0.0, rates)
        disallowedList += filter(lambda elem: float(elem.text) <= 0.0, rates)

    typeFromElem = lambda elem: elem.attrib['type']
    nonSuppressed = lambda target: target not in SUPPRESS_TARGET_TYPES

    unitListFiltered = list(filter(nonSuppressed, map(typeFromElem, unitList)))
    disallowedListFiltered = list(filter(nonSuppressed, map(typeFromElem, disallowedList)))
    # We have to stop suppressing the suppressible types if it would leave us with nothing
    if len(unitListFiltered) == 0 and len(disallowedListFiltered) > 0:
        unitListFiltered = (list(map(typeFromElem, unitList)))
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
        useDPS = chargeType == ActionChargeType.NONE and findFromActionOrTactics(action, tactics, "selfdestruct", 0, int) == 0
        items = [actionName, rechargeRate(proto, action, chargeType, tech), actionTargetTypeText(proto, action), additionalText, actionPreDamageInfoText(action), "DPS: " if useDPS else "", actionDamageFull(proto, action, isDPS=useDPS, ignoreActive=tech is not None)]
        for index in (1, 0):
            if len(items[index]):
                items[index] += ":"
                break
        items = [x for x in items if len(x) > 0]
        return f"{' '.join(items)}"
    return inner

def targetListToString(targetList: List[str], excludeTargets: List[str] = [], joiner="and"):
    if len(targetList) == 0 and len(excludeTargets) > 0:
        unitClassNames = common.getListOfDisplayNamesForProtoOrClass("All", plural=True)
    else:
        unitClassNames = common.getListOfDisplayNamesForProtoOrClass(targetList, plural=True)
    
    text = common.commaSeparatedList(unitClassNames, joiner)
    if len(excludeTargets) > 0:
        text += f" (except {common.commaSeparatedList(common.getListOfDisplayNamesForProtoOrClass(excludeTargets, plural=True), joiner)})"
    return text

def handleHealAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    rateNode = action.find("rate")
    healRate = f"{float(rateNode.text):0.3g}"
    slowHealMultiplier = findAndFetchText(action, "slowhealmultiplier", 1.0, float) * 100

    items = [actionName, rechargeRate(proto, action, chargeType, tech), "Heals", actionTargetList(action, tactics), f"{healRate} hitpoints/second.", actionRange(proto, action, True)]
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
    
    targetElems = action.findall("rate")
    rateItems = [f"{common.getDisplayNameForProtoOrClassPlural(elem.attrib['type'])} at {float(elem.text):0.3g} unit{'s' if float(elem.text) != 1.0 else ''}/s" for elem in targetElems]
    stem += f"Builds {common.commaSeparatedList(rateItems)}."
    if len(buildNodes) > 0 and len(buildNodes) <= 5:
        stem += f" Can build: {common.getDisplayNameForProtoOrClassPlural([node.text for node in buildNodes])}."
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
        return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Stuns targets for {duration:0.3g}s, creating a copy under your control next to them that lasts for the same duration. This copy inherits any upgrades on the original, and appears at full health with special attacks ready to use. {exclusive}{actionRange(proto, action, True)} {actionRof(action)}"

    print(f"Warning: Non charmedconvert convert on {proto.attrib['name']}, ignored")
    return ""

def handleTrailAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None):
    protoElem = action.find("trailprotounit")
    freq = float(protoElem.attrib['frequency'])
    targetProto = protoFromName(protoElem.text)
    targetActions = targetProto.findall("protoaction")
    if len(targetActions) != 1:
        print(f"Warning: Trail action for {proto.attrib['name']} has {targetActions} possible actions, unsure which to describe")
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
    
    return f"{actionName} {rechargeRate(proto, action, chargeType, tech)}: {actionTargetTypeText(proto, action)} Fires a projectile which bounces between targets, hitting up to {bounces:0.3g} different targets. Each successive target can be no further from {dist:0.3g}m from the last. Upon returning to the user, they are healed for the total damage dealt. {actionDamageFull(proto, action, hideArea=True, ignoreActive=tech is not None)}"

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
    targetunit = "other unit of the same type"
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
    text = f"Can transform into a {common.getObjectDisplayName(protoFromName(action.find('modifyprotoid').text))} (takes {findAndFetchText(action, 'modifyduration', 0.0, float)/1000.0:0.3g} seconds)."
    items = [actionName, text]
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
        print(f"Warning: Charge structure has unknown activationtype {activationType}")
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
            print(f"Warning: Charge structure using unknown applytype {applyType}")
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
        elif modifyType == "LifeSteal":
            modifyTypeText = "Lifesteal"
            formatPercentage = True
        elif modifyType == "ArmorSpecific":
            modifyTypeText = f"{modifyElem.attrib['param']} Vulnerability"
            if applyType != "Add":
                print(f"Warning: Charge structure on ArmorSpecific with unsupported applytype {applyType}")
                continue
            formatPercentage = True
            if amount > 0.0:
                applyTypeText = "reduces {modifyType} by {amount}"
            else:
                applyTypeText = "increases {modifyType} by {amount}"
                amount *= -1.0
        else:
            print(f"Warning: Charge structure using unknown modiftype {modifyType}")
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
    
    addingActions = common.commaSeparatedList([getActionName(proto, actionName) for actionName in addActions])

    components = []
    components.append(f"Every usage of {addingActions} adds 1 stack.")
    if len(removeActions) > 0:
        components.append(f"Every usage of {common.commaSeparatedList([getActionName(proto, actionName) for actionName in removeActions])} requires and consumes 1 stack.")

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
}


def handleAutoRangedModifyAction(proto: ET.Element, action: ET.Element, tactics: Union[None, ET.Element], actionName: str, chargeType:ActionChargeType=ActionChargeType.NONE, tech: Union[None, ET.Element]=None, isInfection=False):
    modifyType = findFromActionOrTactics(action, tactics, "modifytype", None)
    if modifyType is None:
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
                lateComponents.append(f"Heals up to {modifyTargetLimit} targets at once.")
            if slowHealMultiplier < 1.0:
                lateComponents.append(f"Targets that have moved or been involved in combat in the last 3 seconds are healed at {slowHealMultiplier*100:0.3g}% speed.")
    elif modifyType in ("Damage", "Armor", "MaxHP", "Speed", "BuildRate", "MilitaryTrainingCost"):
        multiplier = findFromActionOrTactics(action, tactics, "modifymultiplier", None, float)
        modifyTypeName = MODIFY_TYPE_DISPLAY.get(modifyType, modifyType)
        if modifyType in ("Armor"):
            multiplier = 1.0 + (1.0-multiplier)
        if multiplier > 1.0:
            components.append(f"increases {modifyTypeName} by {100*(multiplier-1.0):0.3g}% for")
        elif multiplier < 1.0:
            components.append(f"decreases {modifyTypeName} by {-100*(multiplier-1.0):0.3g}% for")
    elif modifyType == "RevealUI":
        components.append("allows you to check the actions/garrison of")
    elif modifyType == "AuraEmpower":
        components.append(f"{handleEmpowerAction(proto, action, tactics, '', chargeType)} Affects")
    elif modifyType == "ArmorSpecific":
        multiplier = findFromActionOrTactics(action, tactics, "modifyamount", None, float)
        armorType = findFromActionOrTactics(action, tactics, "modifydamagetype", None, str)
        if multiplier > 1.0:
            components.append(f"decreases {armorType} vulnerability by {100*(multiplier-1.0):0.3g}% for")
        elif multiplier < 1.0:
            components.append(f"increases {armorType} vulnerability by {-100*(multiplier-1.0):0.3g}% for")
    elif modifyType == "GatherRateMultiplier":
        multiplier = findFromActionOrTactics(action, tactics, "modifymultiplier", None, float)
        components.append(f"increases gather rate by {(multiplier-1.0)*100:0.3g}%. Affects")
    else:
        print(f"Warning: Unknown AutoRangedModify type {modifyType} for {proto.attrib['name']}")
        return ""

    playerRelation = ["your"]

    if findFromActionOrTactics(action, tactics, "targetenemy", ""):
        playerRelation = ["enemy"]
    elif findFromActionOrTactics(action, tactics, "targetenemyincludenature", ""):
        playerRelation = ["nature", "enemy"]
    elif findFromActionOrTactics(action, tactics, "targetnonally", ""):
        playerRelation = ["non-allied"]
    elif findFromActionOrTactics(action, tactics, "includeally", ""):
        playerRelation = ["your", "your allies"]

    # This is a huge assumption about how infection works
    if isInfection:
        playerRelation = [entry.replace("enemy", "friendly") for entry in playerRelation]

    if findFromActionOrTactics(action, tactics, "modifyself", 0, int) > 0:
        playerRelation.insert(0, "itself")
    elif isInfection and findFromActionOrTactics(action, tactics, "modifyselfifinfection", 0, int):
        playerRelation.insert(0, "itself")

    components.append(common.commaSeparatedList(playerRelation))

    if findFromActionOrTactics(action, tactics, "targetunbuilt", ""):
        components.append("unfinished")

    allowedTargetTypes = [x.text for x in findAllFromActionOrTactics(action, tactics, "modifyabstracttype")]
    forbidTargetTypes = [x.text for x in findAllFromActionOrTactics(action, tactics, "forbidabstracttype")+findAllFromActionOrTactics(action, tactics, "forbidunittype")]
    components.append(targetListToString(allowedTargetTypes, forbidTargetTypes))

    components[-1] += "."

    if isInfection:
        components.append("A unit can only have one infection at a time.")

    components += lateComponents

    

    if findFromActionOrTactics(action, tactics, "nostack", 0, int) == 0:
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
                    print(f"Warning: mismatched Peach blossom spring for {targetRes} on {proto.attrib['name']} doesn't match standard target {standardTarget} rate: {rate} vs standard {standardRate}")
                    items.append(f"{targetRes} (from Peach Blossom): {rate}")

            else:
                raise ValueError(f"Unknown gather action target on {proto.attrib['name']}: {target}")
        
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
    
    "JumpAttack":simpleActionHandler("Leaps over obstacles on the way to the target."),
    "Attack":simpleActionHandler(),
    "ChainAttack":simpleActionHandler(),
    "AutoBoost":simpleActionHandler(),
    "TeleportAttack":simpleActionHandler("Teleports to the target. May be used manually without a target to bypass obstacles such as walls.")
}

def actionDamageFlagNames(action: ET.Element):
    flags = action.find("damageflags")
    if flags is None:
        return ""
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
        damageOnly = actionDamageOnly(proto, action, hideRof=True)
        if damageOnly == "":
            return ""
        return f"{damageOnly} {actionDamageBonus(action)} to {actionDamageFlagNames(action)} objects within {actionArea(action)}"
    return ""

def getCivAbilitiesNode(proto: Union[ET.Element, str], action: Union[ET.Element, str], forceAbilityLink: Union[str, None]=None):
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
                unitAction = findAndFetchText(abilityInfo, "unitaction", None)
                if unitAction == actionInternalName or (actionAnimName is not None and unitAction == actionAnimName):
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
    unitOverride = unitdescription.unitDescriptionOverrides.get(proto.attrib['name'], None)
    if unitOverride is not None:
        override = unitOverride.actionNameOverrides.get(actionInternalName, None)
        if override is not None:
            return override

    abilityInfo = getCivAbilitiesNode(proto, action, forceAbilityLink)

    if abilityInfo is not None:
        actionName = common.getObjectDisplayName(abilityInfo)
        if actionName is None:
            print(f"Warning: No name for charge action {actionInternalName} -> on {proto.get('name')}")
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
            actionName = getActionName(proto, action, forceAbilityLink, nameNonChargeActions=True)
        
    result = ""
    handler = ACTION_TYPE_HANDLERS.get(actionInternalName, ACTION_TYPE_HANDLERS.get(actionInternalType, None))
    if handler is None:
        print(f"Warning: No handler for action: internal type={actionInternalType}; action name={actionInternalName}; display name={actionName}; on {proto.get('name')}")
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

def getActionAttackCount(proto: Union[str, ET.Element], action: Union[str, ET.Element]):
    "Return the number of times a given action makes attack tag attempts in its animation data."
    proto = common.protoFromName(proto)
    action = findActionByName(proto, action)
    tactics = actionTactics(proto, action)
    targetActionName = findFromActionOrTactics(action, tactics, "anim", None)
    if targetActionName is None:
        targetActionName = findFromActionOrTactics(action, tactics, "name", None)
    if targetActionName is None:
        print(f"Unable to find target action name for {proto.attrib['name']} action {action} with type {findFromActionOrTactics(action, tactics, "type", None)}")
        return 1
    animFile = proto.find("animfile")
    if animFile is None:
        print(f"Unable to find target animfile for {proto.attrib['name']}")
        return 1
    animFile = animFile.text
    animFileSection = list(filter(lambda obj: obj['file'] == animFile, globals.dataCollection["simdata.simjson"]["animdata"]))
    if len(animFileSection) == 0:
        print(f"Unable to find simdata animfile section for {proto.attrib['name']}'s {targetActionName}")
        return 1
    
    animMatches = list(filter(lambda obj: obj['name'] == targetActionName, animFileSection[0]['animations']))
    if len(animMatches) < 1:
        #print(f"Unable to get any anim match for {proto.attrib['name']}'s {targetActionName}")
        return 1
        
    def countAttackTags(version):
        count = 0
        if "tags" not in version:
            return 0
            
        for tag in version["tags"]:
            if tag["type"] == "Attack":
                count += 1
        return count
    
    versionCounts = []
    for anim in animMatches:
        versionCounts += list(set(map(countAttackTags, anim["versions"])))
    versionCounts = list(set(versionCounts))
    if len(versionCounts) != 1:
        print(f"Warning: {proto.attrib['name']}'s {targetActionName} appears to have variable number of attacks: {versionCounts}")
    return max(1, int(sum(versionCounts)/len(versionCounts)))