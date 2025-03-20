import globals
import common
from common import findGodPowerByName
import tech
import action
from xml.etree import ElementTree as ET
import dataclasses
from typing import Dict, List, Union, Callable
import icon
import copy
import math
import unitdescription

IGNORE_POWERS = (
    "TempestSPC",
    "LightningStormSPC",
    "CheatMeteor",
    "WalkingWoodsSingleTarget",
    "WalkingBerryBushes",
    "CeaseFire3Minutes",
    )

@dataclasses.dataclass
class GodPowerParams:
    # Text lines for the power description
    text: Union[str, List[str]] = ""
    
    # Overrides for recharge time and cost text
    overrideRecharge: Union[str, None] = None
    overrideCost: Union[str, None] = None


godPowerProcessingParams: Dict[str, GodPowerParams] = {}

def getTechEffectHandlerResponseForGodPowerEffect(godpower: ET.Element, effect: ET.Element) -> Union[None, tech.EffectHandlerResponse]:
    # This is a little bit dirty...
    # Some god powers use effect definitions that are VERY like data tech effects, except they need a little bit of fixing up to match
    effect = copy.deepcopy(effect)
    effect.attrib['subtype'] = effect.attrib['type']
    effect.attrib['type'] = "Data"
    # And then the tech describing code can handle them without issue
    response = tech.processEffect(godpower, effect)
    return response

def describeGodPowerEffectsLikeDataTech(godpower: ET.Element) -> List[str]:
    responses = [getTechEffectHandlerResponseForGodPowerEffect(godpower, effect) for effect in godpower.findall("effect")]
    responses = [response for response in responses if response is not None]
    tech.combineHandlerResponses(responses)
    return [response.toString() for response in responses]

def protoGodPowerDamage(proto: str, actionName: str, damageMultiplier: float=1.0, damageOnly=False, hideDamageBonuses=False) -> str:
    protoElem = common.protoFromName(proto)
    actionElem = action.findActionByName(protoElem, actionName)
    if damageOnly:
        return action.actionDamageOnly(protoElem, actionElem, hideRof=True, damageMultiplier=damageMultiplier)
    return action.actionDamageFull(protoElem, actionElem, hideRof=True, hideRange=True, ignoreActive=True, damageMultiplier=damageMultiplier, hideDamageBonuses=hideDamageBonuses)

def processGodPower(godpower: ET.Element) -> Union[None, str]:
    powerName = godpower.attrib['name']
    if powerName in IGNORE_POWERS:
        return None
    params = godPowerProcessingParams.get(powerName, None)
    if params is None:
        print(f"Warning: No godpower params for {powerName}, returning vanilla text")
        return None
    topLineItems = ["Recast:"]
    rechargeString = params.overrideRecharge
    if rechargeString is None and powerName in globals.godPowerRecharges:
        rechargeString = f"{globals.godPowerRecharges[powerName]:0.3g}"
    if rechargeString is not None and len(rechargeString):
        topLineItems.append(f"{icon.iconTime()} {rechargeString}")
    costString = params.overrideCost
    if costString is None:
        costString = f"{common.findAndFetchText(godpower, 'cost', 0.0, float):0.3g} + {common.findAndFetchText(godpower, 'repeatcost', 0.0, float):0.3g} each recast"
    if costString:
        topLineItems.append(f"{icon.resourceIcon('favor')} {costString}")
    if len(topLineItems) > 1:
        items = [" ".join(topLineItems)]

    replacements = {}
    radiusValue = common.findAndFetchText(godpower, "radius", 0.0, float)
    rangeIndicator = godpower.find("rangeindicator")
    rangeIndicatorSize = 0.0 if rangeIndicator is None else float(rangeIndicator.attrib.get('range', 0.0))
    radiusParts = []
    radiusPartsLate = []
    if rangeIndicatorSize > 0.0 and radiusValue > 0.0 and abs(rangeIndicatorSize - radiusValue) > 1.0:
        radiusPartsLate.append(f"Targeting cursor has a radius of {rangeIndicatorSize}m.")
    radiusParts.append(f"Radius: {radiusValue:0.3g}m")
    revealLos = godpower.find("reveallos")
    if revealLos is not None and 'radius' in revealLos.attrib:
        revealedRadius = float(revealLos.attrib['radius'])
        replacements['los'] = f"Grants {revealedRadius:0.3g}m line of sight."
        if radiusValue == revealedRadius:
            radiusParts.append("grants line of sight")
        else:
            radiusPartsLate.append(replacements['los'])
        

    powerBlocker = godpower.find("powerblocker")
    if powerBlocker is not None:
        powerBlockerRadius = float(powerBlocker.text)
        replacements['powerblocker'] = f"Blocks other god powers within {powerBlockerRadius:0.3g}m."
        if powerBlockerRadius == radiusValue:
            radiusParts.append("blocks other god powers")
        else:
            radiusPartsLate.append(replacements['powerblocker'])
    
    replacements["radius"] = f"{', '.join(radiusParts)}."
    if len(radiusPartsLate):
        replacements["radius"] += " " + " ".join(radiusPartsLate)

    replacements["duration"] = f"Lasts {common.findAndFetchText(godpower, 'activetime', 0.0, float) + common.findAndFetchText(godpower, 'builduptime', 0.0, float):0.3g} seconds."

    playerRelation = godpower.find("powerplayerrelation")
    if playerRelation is None:
        playerRelation = ""
        playerRelationPossessive = ""
    elif playerRelation.text in ("Enemy", "EnemyNotMotherNature"):
        playerRelationPossessive = "enemy "
        playerRelation = "enemies"
    elif playerRelation.text in ("Player"):
        playerRelationPossessive = "your "
        playerRelation = "you"
    elif playerRelation.text in ("All", "Any"):
        playerRelationPossessive = "all players' "
        playerRelation = "all players"
    elif playerRelation.text in ("Ally"):
        playerRelationPossessive = "your or your allies' "
        playerRelation = "you and your allies"
    else:
        print(f"Warning: {powerName} has unhandled powerplayerrelation {playerRelation}")
        playerRelation = ""
    replacements['playerrelation'] = playerRelation.strip()
    replacements['playerrelationpos'] = playerRelationPossessive.strip()
    
    # Some powers exclude things pointlessly that were never in the targeted unit types to begin with
    # eg farms already lack the "affected by earthquake" flag, don't need to exclude them again
    usePlacementTargetType = False
    attackTargets = [elem.text for elem in godpower.findall("abstractattacktargettype")]
    if len(attackTargets) == 0:
        usePlacementTargetType = True
        attackTargets = [elem.text for elem in godpower.findall("abstractplacementtargettype")]
    attackTargetsExpandedTypes = []
    for target in attackTargets:
        if target not in globals.protosByUnitType:
            attackTargetsExpandedTypes.append(target)
        else:
            attackTargetsExpandedTypes += globals.protosByUnitType[target]
    replacements["attacktargets"] = common.commaSeparatedList(common.getListOfDisplayNamesForProtoOrClass(attackTargets, plural=True))
    if usePlacementTargetType:
        restrictedTargets = [elem.text for elem in godpower.findall("explicitlyrestrictedplacementtargettype")]
    else:
        restrictedTargets = [elem.text for elem in godpower.findall("explicitlyrestrictedattacktargettype")]
    restrictedTargetsRevised = []
    for target in restrictedTargets:
        targetWouldBeHit = False
        if target in attackTargetsExpandedTypes:
            targetWouldBeHit = True
        elif target in globals.protosByUnitType:
            # Exclude if no members of this unit type are in the list of valid targets
            for abstractTypeMember in globals.protosByUnitType[target]:
                if abstractTypeMember in attackTargetsExpandedTypes:
                    targetWouldBeHit = True
                    break
        if targetWouldBeHit:
            restrictedTargetsRevised.append(target)
            
    if restrictedTargetsRevised:
        replacements["attacktargets"] += f", except {common.commaSeparatedList(common.getListOfDisplayNamesForProtoOrClass(restrictedTargetsRevised, plural=True))}"

    if isinstance(params.text, list):
        items += [line.format(**replacements) for line in params.text]
    else:
        items.append(params.text.format(**replacements))

    if godpower.find("exclusive") is not None:
        items.append(f"Only one instance of {common.getObjectDisplayName(godpower)} can be active at a time.")
    activelistvisibility = common.findAndFetchText(godpower, "activelistvisibility", None, str)
    if activelistvisibility == "AlliesOnly":
        items.append(f"Enemies are not notified when you use this power.")
    elif activelistvisibility == "None":
        items.append(f"No other players are not notified when you use this power.")
    
    return "\\n".join(items)


def findGodPowerRecharges():
    techtree = globals.dataCollection["techtree.xml"]
    for techElem in techtree:
        grantPowers = techElem.findall("effects/effect[@subtype='GodPower']")
        for granted in grantPowers:
            if "cooldown" in granted.attrib:
                powerName = granted.attrib['power']
                globals.godPowerRecharges[powerName] = float(granted.attrib['cooldown'])


# There's a bug that is making the damage interval of certain powers 50ms longer than the data would have you believe
DAMAGE_INTERVAL_BUG_AMOUNT = 0.05

def generateGodPowerDescriptions():
    proto = globals.dataCollection["proto.xml"]
    techtree = globals.dataCollection["techtree.xml"]
    findGodPowerRecharges()

    bolt = findGodPowerByName("Bolt")
    godPowerProcessingParams["Bolt"] = GodPowerParams(f"Damages a single unit: {protoGodPowerDamage(bolt.find('strikeproto').text, 'HandAttack')}")

    sentinel = findGodPowerByName("Sentinel")
    sentinelCreateUnit = sentinel.find("createunit")
    sentinelItems = [f"Creates {sentinelCreateUnit.attrib['quantity']} Sentinels in a {sentinelCreateUnit.attrib['minradius']}-{sentinelCreateUnit.attrib['maxradius']}m circle around {{playerrelationpos}} Town Center, Citadel Center, or Fortress-like building. Can be rotated (mouse wheel) before placing.", unitdescription.describeUnit("Sentinel")]
    godPowerProcessingParams["Sentinel"] = GodPowerParams(sentinelItems)

    lure = findGodPowerByName("Lure")
    lureAttractedTargets = common.commaSeparatedList(common.getListOfDisplayNamesForProtoOrClass([elem.text for elem in lure.findall("attracttype")], plural=False), "or")
    lureSpawns = common.getDisplayNameForProtoOrClass(lure.find('spawnproto').text) + "s"
    lureItems = [f"Creates a Lure, functioning as a Food dropsite, and several {lureSpawns}. Every {common.findAndFetchText(lure, 'attractrate', 0.0, float):0.3g} seconds, tries to attract one {lureAttractedTargets} between {common.findAndFetchText(lure, 'minrange', 0.0, float):0.3g} and {common.findAndFetchText(lure, 'maxrange', 0.0, float):0.3g}m away. Once its food limit has been reached, the Lure remains as a Food dropsite."]
    lureItems += [f" {icon.BULLET_POINT} {common.AGE_LABELS[index]}: Attracts {icon.resourceIcon('food')} {ageinfo.attrib['maxfood']}, {ageinfo.attrib['numspawns']} {lureSpawns}" for index, ageinfo in enumerate(lure.findall("ageinfo"))]
    godPowerProcessingParams["Lure"] = GodPowerParams(lureItems)

    restoration = findGodPowerByName("Restoration")
    restorationItems = [f"Heals affected units for {{playerrelation}} in the area for {common.findAndFetchText(restoration, 'healspeed', None, float):0.3g} hitpoints per second. Non idle targets are healed at {common.findAndFetchText(restoration, 'slowhealmultiplier', None, float):0.3g}x rate.", "{radius}", "{duration}"]
    godPowerProcessingParams["Restoration"] = GodPowerParams(restorationItems)

    ceasefire = findGodPowerByName("CeaseFire")
    ceasefireItems = [f"Prevents combat actions between players. Hunting is unaffected. Slows construction of most fortifications.", *describeGodPowerEffectsLikeDataTech(ceasefire),  "{duration}"]
    godPowerProcessingParams["CeaseFire"] = GodPowerParams(ceasefireItems)

    pestilence = findGodPowerByName("Pestilence")
    pestilenceItemms = [f"Affects {{playerrelationpos}} {{attacktargets}}, preventing them from shooting arrows and increasing the time they take to train units by {common.findAndFetchText(pestilence, 'trainratepenalty', 1.0, float)-1:0.0%}.", "{radius}", "{duration}"]
    godPowerProcessingParams["Pestilence"] = GodPowerParams(pestilenceItemms)

    bronze = findGodPowerByName("Bronze")
    def bronzeArmorItemVulnList(elem):
        typesByValue = {}
        for armorType in elem.findall("armortype"):
            delta = -1*float(armorType.attrib['vulnerabilitypercentdelta'])
            if delta not in typesByValue:
                typesByValue[delta] = []
            typesByValue[delta].append(armorType.text)
        vulnStrings = common.commaSeparatedList([f"{common.commaSeparatedList(types)} Vulnerability by {100*delta:0.3g}%" for delta, types in typesByValue.items()])
        return f"Reduces {vulnStrings}"
    bronzeArmorItems = [f" {icon.BULLET_POINT} {common.getDisplayNameForProtoOrClass(elem.find('abstracttype').text, plural=True)}: {bronzeArmorItemVulnList(elem)}." for elem in bronze.findall("armor")]
    bronzeItems = [f"Temporarily increases the armor of friendly units in the area at the time of casting.", *bronzeArmorItems, "{radius}", "{duration}"]
    godPowerProcessingParams["Bronze"] = GodPowerParams(bronzeItems)

    curse = findGodPowerByName("Curse")
    curseItems = [f"Turns up to {common.findAndFetchText(curse, 'maxresources', 0.0, float):0.3g} resources of enemy units into Pigs. {icon.resourceIcon('favor')} 1 counts for 10 total resources. Damaged units still count their whole cost. The pigs are created with {icon.resourceIcon('food')} 50 plus the total resource cost of the transformed unit, without multiplying up Favor.", "Affects {playerrelationpos} {attacktargets}.", "{radius}"]
    godPowerProcessingParams["Curse"] = GodPowerParams(curseItems)

    underworld = findGodPowerByName("UnderworldPassage")
    underworldItems = [f"Place two ends of an Underworld Passage. Friendly units entering one side are instantly transported to the other. Lasts until destroyed."]
    godPowerProcessingParams["UnderworldPassage"] = GodPowerParams(underworldItems)

    plenty = findGodPowerByName("PlentyVault")
    plentyItems = [f"Place an indestructible Plenty Vault which generates resources for whoever controls it. It can be captured by nearby units.", action.describeAction("PlentyVault", action.findActionByName("PlentyVault", "AutoGather"))]
    godPowerProcessingParams["PlentyVault"] = GodPowerParams(plentyItems)

    lightningstorm = findGodPowerByName("LightningStorm")
    lightningstormItems = [f"Summon a Lightning Storm. Lightning strikes inflict {protoGodPowerDamage(lightningstorm.find('strikeproto').text, 'HandAttack', damageOnly=True)}", "Affects {playerrelationpos} {attacktargets}, but will always prefer targeting units if there are any in the area.", "Takes about 7-8 seconds for lightning strike rate to increase. Average number of strikes: about 45.", "Preferentially targets objects closest to the southeast edge of the map.", "{radius}", "{duration}"]
    godPowerProcessingParams["LightningStorm"] = GodPowerParams(lightningstormItems)

    earthquake = findGodPowerByName("Earthquake")
    # Despite what attackInterval gets specified, the real value is actually 50ms larger than the power claims
    earthquakeAttackInterval = common.findAndFetchText(earthquake, "attackinterval", 0.0, float) + DAMAGE_INTERVAL_BUG_AMOUNT
    earthquakeAllyDamage = f"{common.findAndFetchText(earthquake, 'allydamageratio', 0.0, float)*100:0.3g}%"
    earthquakeDamageAreas = ("epicenter", "middle", "outer")
    earthquakeDamageProto = earthquake.find('attackproto').text
    earthquakeDamageMultiplier = math.ceil(common.findAndFetchText(earthquake, "activetime", 0.0, float)/earthquakeAttackInterval)
    earthquakeDamageAreaItems = [f" {icon.BULLET_POINT} Objects within {common.findAndFetchText(earthquake, zone + 'zoneradius', 0.0, float):0.3g}m: {protoGodPowerDamage(earthquakeDamageProto, 'HandAttack', damageMultiplier=earthquakeDamageMultiplier*common.findAndFetchText(earthquake, zone + 'zonedamageratio', 0.0, float))}" for zone in earthquakeDamageAreas]
    earthquakeItems = [f"Summon an Earthquake with {len(earthquakeDamageAreas)} bands of damage output. Friendly objects take only {earthquakeAllyDamage} damage." + " Affects {playerrelationpos} {attacktargets}.", *earthquakeDamageAreaItems, "{radius}", "{duration}"]
    godPowerProcessingParams["Earthquake"] = GodPowerParams(earthquakeItems)

    rain = findGodPowerByName("Rain")
    rainEffect = rain.find("effect")
    rainMyResponse = getTechEffectHandlerResponseForGodPowerEffect(rain, rainEffect)
    rainOtherEffect = copy.copy(rainEffect)
    rainOtherEffect.attrib['amount'] = rainOtherEffect.attrib['altamount']
    rainOtherResponse = getTechEffectHandlerResponseForGodPowerEffect(rain, rainOtherEffect)
    rainItems = ["Grants {playerrelation} increased farming rate.", f"{rainMyResponse.toString()}", "{duration}"]
    godPowerProcessingParams["Rain"] = GodPowerParams(rainItems)

    prosperity = findGodPowerByName("Prosperity")
    prosperityItems = ["Grants {playerrelation} the following effects:", *describeGodPowerEffectsLikeDataTech(prosperity), "{duration}"]
    godPowerProcessingParams["Prosperity"] = GodPowerParams(prosperityItems)

    vision = findGodPowerByName("Vision")
    # Piggybacking off the unit descriptions discusses idleness which is a bit confusing
    visionRevealerProto = common.protoFromName("VisionRevealer")
    visionInitialLOS = common.findAndFetchText(visionRevealerProto, "los", 0.0, float)
    visionRevealerAction = action.findActionByName(visionRevealerProto, "AutoLOS")
    visionRevealerGrowthRate = float(visionRevealerAction.find("modifyamount").text)
    visionRevealerGrowthMax = float(visionRevealerAction.find("modifyratecap").text)
    visionMaxLOS = visionInitialLOS + visionRevealerGrowthMax
    visionTimeToMax = visionRevealerGrowthMax/visionRevealerGrowthRate
    visionCursorDifference = visionMaxLOS - float(vision.find("rangeindicator").attrib['range'])
    visionMaybeBuggedCursor = []
    if visionCursorDifference > 0.1:
        visionMaybeBuggedCursor.append(f"Cursor preview is {visionCursorDifference:0.3g}m smaller than the maximum reveal radius!")
    visionItems = [f"Reveals any area of the map. Has an initial LOS of {visionInitialLOS:0.3g}m, increasing to {visionMaxLOS:0.3g}m over {visionTimeToMax:0.3g} seconds.", *visionMaybeBuggedCursor, "{duration}"]
    godPowerProcessingParams["Vision"] = GodPowerParams(visionItems)

    eclipse = findGodPowerByName("Eclipse")
    eclipseItems = ["Grants {playerrelation} the following effects:", *describeGodPowerEffectsLikeDataTech(eclipse), "{duration}"]
    godPowerProcessingParams["Eclipse"] = GodPowerParams(eclipseItems)

    shiftingsands = findGodPowerByName("ShiftingSands")
    shiftingSandsTime = common.findAndFetchText(shiftingsands, "activetime", 0.0, float)
    shiftingsandsItems = [f"Select two locations. After {shiftingSandsTime:0.3g} seconds, all of {{playerrelationpos}} affected units are teleported from the first location to the second.", "{radius}"]
    godPowerProcessingParams["ShiftingSands"] = GodPowerParams(shiftingsandsItems)

    plagueofserpents = findGodPowerByName("PlagueOfSerpents")
    plagueofserpentsDuration = common.findAndFetchText(plagueofserpents, "activetime", 0.0, float)
    plagueofserpentsDistance = float(plagueofserpents.find("createunit").attrib['maxradius'])
    plagueofserpentsQuantity = sum([int(elem.attrib['quantity']) for elem in plagueofserpents.findall("createunit")])

    plagueofserpentsItems = [f"Summons {plagueofserpentsQuantity} uncontrollable Serpents up to {plagueofserpentsDistance:0.3g}m away from the targeted location over {plagueofserpentsDuration:0.3g} seconds. Sea Snakes are spawned on water terrain instead. The Serpents persist until killed."]
    plagueofserpentsItems += ["<tth>Serpent:", unitdescription.describeUnit("Serpent"), "<tth>Sea Snake:", unitdescription.describeUnit("SeaSnake")]
    godPowerProcessingParams["PlagueOfSerpents"] = GodPowerParams(plagueofserpentsItems)

    locustswarm = findGodPowerByName("LocustSwarm")
    locustswarmQuantity = int(locustswarm.find("swarmcount").text)
    locustswarmSpeed = float(common.protoFromName("LocustSwarm").find("maxvelocity").text)
    locustswarmMultiplier = 1.0/float(locustswarm.find("damageinterval").text)
    locustswarmDamageBonus = float(action.findActionByName("LocustSwarm", "HandAttack").find("damagebonus").text)
    locustswarmRadius = common.findAndFetchText(locustswarm, "swarmradius", 0.0, float)
    locustswarmItems = [f"Summons {locustswarmQuantity} swarms of locusts that move at {locustswarmSpeed:0.3g} m/s in your chosen direction, with some slight randomness to their paths. The swarms continuously damage all players' {{attacktargets}} within {locustswarmRadius:0.3g}m: each second, they deal {protoGodPowerDamage('LocustSwarm', 'HandAttack', locustswarmMultiplier)}", "Locust Swarms are considered Heroic age Myth Units and benefit from the Mythic Age damage increase, and other effects such as Eclipse.", "{duration}"]
    godPowerProcessingParams["LocustSwarm"] = GodPowerParams(locustswarmItems)

    ancestors = findGodPowerByName("Ancestors")
    ancestorsMaxDelay = max(map(lambda x: float(x.attrib['delay']), ancestors.findall("createunit")))
    ancestorsDistance = float(ancestors.find("createunit").attrib['maxradius'])
    ancestorsQuantity = len(ancestors.findall("createunit"))

    ancestorsItems = [f"Summons {ancestorsQuantity} controllable Minions up to {ancestorsDistance:0.3g}m away from the targeted location over {ancestorsMaxDelay:0.3g} seconds. Lost Ships are spawned on water terrain instead. When the power ends, any surviving spawned units are killed.", "Minions are Heroic Age myth units and are upgraded upon reaching the Mythic Age.", "{duration}"]
    ancestorsItems += ["<tth>Minion:", unitdescription.describeUnit("Minion")]
    #ancestorsItems += ["<tth>Lost Ship:", unitdescription.describeUnit("LostShip")]
    godPowerProcessingParams["Ancestors"] = GodPowerParams(ancestorsItems)

    citadel = findGodPowerByName("Citadel")
    citadelPopDifference = common.findAndFetchText(common.protoFromName("CitadelCenter"), "populationcapaddition", 0.0, float) - common.findAndFetchText(common.protoFromName("TownCenter"), "populationcapaddition", 0.0, float)
    #citadelItems = ["Converts a Town Center owned by {playerrelation} to a Citadel Center." + f"The Citadel is harder to destroy and supports {citadelPopDifference:0.3g} more population. This does not change the target's percentage hitpoints."]
    citadelItems = ["Converts a Town Center owned by {playerrelation} to a Citadel Center.", unitdescription.describeUnit("CitadelCenter")]
    
    godPowerProcessingParams["Citadel"] = GodPowerParams(citadelItems)

    sonofosiris = findGodPowerByName("SonOfOsiris")
    sonofosirisItems = ["Transforms one of {playerrelationpos} Pharoahs into a powerful Son of Osiris. Does not heal the Pharoah in the process, and his new form cannot be healed. Does not prevent the Pharaoh from respawning.", unitdescription.describeUnit("SonOfOsiris")]
    godPowerProcessingParams["SonOfOsiris"] = GodPowerParams(sonofosirisItems)

    meteor = findGodPowerByName("Meteor")
    meteorCount = common.findAndFetchText(meteor, "numberofstrikes", 0, int)
    meteorItems = [f"Summons a shower of {meteorCount} meteors. Each inflicts {protoGodPowerDamage('Meteor', 'HandAttack')} The first meteor always hits the centre of the targeted area. Meteors are drawn towards both clumps of valid targets and the centre point.", "Friendly targets take only 10% damage.", "{radius}"]
    godPowerProcessingParams["Meteor"] = GodPowerParams(meteorItems)

    tornado = findGodPowerByName("Tornado")
    # Like earthquake, it seems to have +50ms on each attack interval
    # Seems to be forced max damage between 0 and 5m of the tornado, and then linear falloff to 15m - so 5 and 5.1m has a big sudden drop as you go from zero falloff to 2/3 damage
    # This is a pain to measure due to collison radii affecting the damage values
    tornadoMultiplier = 1/(common.findAndFetchText(tornado, "damageinterval", 0.0, float) + DAMAGE_INTERVAL_BUG_AMOUNT)
    tornadoItems = ["Creates a Tornado that damages {playerrelationpos} objects. It always moves in an anticlockwise spiral. Every second, it inflicts " + f"{protoGodPowerDamage('Tornado', 'HandAttack', tornadoMultiplier)} Targets within 5m of the centre of the vortex take full damage, those between 5 and 15m are damaged with normal linear distance falloff.", "{powerblocker}", "{duration}"]
    godPowerProcessingParams["Tornado"] = GodPowerParams(tornadoItems)

    dwarvenmine = findGodPowerByName("DwarvenMine")
    dwarvenmineItems = [f"Creates a gold mine. The amount of Gold in the mine and the gather rate increases in later Ages."]
    dwarvenmineItems += [f" {icon.BULLET_POINT} {common.AGE_LABELS[index]}: {icon.resourceIcon('gold')} {round(float(ageinfo.attrib['goldamount']))}, gather rate +{float(ageinfo.attrib['gatherratemultiplier'])-1:0.0%}" for index, ageinfo in enumerate(dwarvenmine.findall("ageadjustment"))]
    godPowerProcessingParams["DwarvenMine"] = GodPowerParams(dwarvenmineItems)

    spy = findGodPowerByName("Spy")
    spyItems = [f"Attaches an eye to an {{playerrelationpos}} unit. The eye can only be seen by you and your allies, and has {float(common.protoFromName(spy.find('spyprotounit').text).find('los').text):0.3g} LOS. It lasts until the targeted unit is killed."]
    godPowerProcessingParams["Spy"] = GodPowerParams(spyItems)

    greathunt = findGodPowerByName("GreatHunt")
    greathuntItems = [f"If there are no huntable animals in the area targeted, spawns Elk with half the maximum new Food value for the current age.", "Otherwise, produces new huntable animals containing up to 2x the amount of Food contained within all the animals affected. Wastage and rounding issues are avoided by creating slightly larger versions of animals which may contain up to double the normal amount of Food.", "Maximum new Food by age:"]
    greathuntItems += [f" {icon.BULLET_POINT} {common.AGE_LABELS[index]}: {icon.resourceIcon('food')} {round(float(ageinfo.text))}" for index, ageinfo in enumerate(greathunt.findall("maxfood"))]
    godPowerProcessingParams["GreatHunt"] = GodPowerParams(greathuntItems)

    gullinbursti = findGodPowerByName("Gullinbursti")
    gullinburstiItems = [f"Summons Gullinbursti near your or an ally's Town or Citadel Center. Its combat stats and lifespan improve in later Ages."]
    gullinburstiProtos = [common.protoFromName(f"Gullinbursti{age}") for age in ("Archaic", "Classical", "Heroic", "Mythic")]
    gullinburstiBirthAttacks = [(boar, action.findActionByName(boar, "BirthAttack")) for boar in gullinburstiProtos]
    gullinburstiBirthAttacksDescriptions = list(set([action.actionDamageFull(boar, act) for boar, act in gullinburstiBirthAttacks]))
    if len(gullinburstiBirthAttacksDescriptions) == 1:
        gullinburstiItems.append(f"Creates an explosion affecting enemies when spawned: {gullinburstiBirthAttacksDescriptions[0]}")
    else:
        gullinburstiItems.append(f"Creates an explosion damaging nearby enemies when spawned.")
    gullinburstiDistanceLimitings = [(boar, action.findActionByName(boar, "DistanceLimiting")) for boar in gullinburstiProtos]
    gullinburstiDistanceLimitingDescriptions = list(set([action.describeAction(boar, act) for boar, act in gullinburstiDistanceLimitings]))
    if len(gullinburstiDistanceLimitingDescriptions) == 1:
        gullinburstiItems.append(gullinburstiDistanceLimitingDescriptions[0])
    else:
        raise ValueError("Gullinbursti DistanceLimiting don't match any more, need to rewrite handling for it")
    gullinburstiItems.append(unitdescription.describeUnit("GullinburstiArchaic"))
    godPowerProcessingParams["Gullinbursti"] = GodPowerParams(gullinburstiItems)

    forestfire = findGodPowerByName("ForestFire")
    if forestfire.find("fasteststriketime").text != forestfire.find("sloweststriketime").text:
        raise ValueError("Forest fire fasteststriketime != sloweststriketime, I have no idea what happens now")
    # Another +50ms bug likely
    forestfireDamageInterval = float(forestfire.find("fasteststriketime").text) + 0.05
    forestfireDamageMult = 1/forestfireDamageInterval
    # I can't get ForestFireEmbers to do any damage at all
    # Damage area of ForestFire's attack is governed by the .godpower data, not by the proto data
    forestfireItems = [f"Starts a Forest Fire on a targeted tree. The fire spreads slowly to other trees within {float(forestfire.find('treesearchradius').text):0.3g}m. Each tree burns for {float(forestfire.find('burnlength').text):0.3g} seconds, damaging {{playerrelationpos}} {{attacktargets}} within {float(forestfire.find('damagesearchradius').text):0.3g}m with no falloff for {protoGodPowerDamage('ForestFire', 'HandAttack', forestfireDamageMult, damageOnly=True)} per second.", f"While burning, each tree grants you {float(common.protoFromName('ForestFire').find('los').text):0.3g} LOS. Any trees still burning at the end of the duration immediately stop applying damage.", "The damage of this power increases by 20% in the Heroic and Mythic ages.", "{duration}"]
    godPowerProcessingParams["ForestFire"] = GodPowerParams(forestfireItems)

    healingspring = findGodPowerByName("HealingSpring")
    healingspringItems = [unitdescription.describeUnit("HealingSpring")]
    godPowerProcessingParams["HealingSpring"] = GodPowerParams(healingspringItems)

    undermine = findGodPowerByName("Undermine")
    # The interval is slightly variable, but the average seems to be 50ms longer
    undermineInterval = float(undermine.find("attackintervalseconds").text) + 0.05
    undermineDamageMult = 1.0/undermineInterval
    undermineItems = [f"Creates a moving wave of instability, damaging {{playerrelationpos}} Buildings while they are within {float(undermine.find('damageradius').text):0.3g}m of the wave: Damage does not depend on distance to the wave. Average DPS: {protoGodPowerDamage('UndermineDamage', 'HandAttack', undermineDamageMult)} Destroys Walls and Towers instantly.", "{duration}"]
    godPowerProcessingParams["Undermine"] = GodPowerParams(undermineItems)

    asgardianbastion = findGodPowerByName("AsgardianBastion")
    asgardianbastionBuildPoints = float(common.protoFromName("AsgardianHillFort").find("buildpoints").text)
    asgardianbastionBuildPointRatio = asgardianbastionBuildPoints/float(common.protoFromName("HillFort").find("buildpoints").text)
    asgardianbastionItems = [f"Places an unbuilt Asgardian Hill Fort that begins with half hitpoints. It slowly builds itself over {asgardianbastionBuildPoints:0.3g} seconds. Its construction can be sped up by normal builders. Its self-building speed doubles in the Heroic Age, and doubles again (to 4x the original) in the Mythic Age. Counts as a Hill Fort for advancing to the Mythic Age.", unitdescription.describeUnit("AsgardianHillFort")]
    godPowerProcessingParams["AsgardianBastion"] = GodPowerParams(asgardianbastionItems)

    frost = findGodPowerByName("Frost")
    frostItems = [f"Freezes {{playerrelationpos}} units. The freeze effect takes {float(frost.find('freezeexpansiontime').text):0.3g} seconds to spread over the entire area. Frozen units have all vulnerabilities reduced by {-1*float(frost.find('armoramount').text):0.0%}, including against Divine damage.", "{radius}", "{duration}"]
    godPowerProcessingParams["Frost"] = GodPowerParams(frostItems)

    flamingweapons = findGodPowerByName("FlamingWeapons")
    flamingweaponsItems = ["Grants {playerrelation} the following effects:", *describeGodPowerEffectsLikeDataTech(flamingweapons), "{duration}"]
    godPowerProcessingParams["FlamingWeapons"] = GodPowerParams(flamingweaponsItems)

    walkingwoods = findGodPowerByName("WalkingWoods")
    walkingwoodsItems = [f"Converts up to {float(walkingwoods.find('convertusingminmax').attrib['minswapamount']):0.3g} Trees in the targeted area into Walking Trees. These are fully under your control and last until killed.", "{radius}", unitdescription.describeUnit("WalkingWoodsCypress")]
    godPowerProcessingParams["WalkingWoods"] = GodPowerParams(walkingwoodsItems)

    tempest = findGodPowerByName("Tempest")
    tempestItems = [f"Summons a storm of ice that affects {{playerrelationpos}} {{attacktargets}}. Each shard inflicts {protoGodPowerDamage(tempest.find('strikeproto').text, 'HandAttack')} Shards appear to strike targets in the area completely at random. Expected number of shards: about 140.", "{radius}", "{duration}"]
    godPowerProcessingParams["Tempest"] = GodPowerParams(tempestItems)

    ragnarok = findGodPowerByName("Ragnarok")
    ragnarokItems = [f"Converts all of your Gatherers and Dwarves into Heroes of Ragnarok. Any resources they are carrying are added to your stockpile.", unitdescription.describeUnit("HeroOfRagnarok")]
    godPowerProcessingParams["Ragnarok"] = GodPowerParams(ragnarokItems)

    fimbulwinter = findGodPowerByName("Fimbulwinter")
    fimbulwinterMainPack = int(fimbulwinter.find("packsize").text)
    fimbulwinterExtraMainPacks = int(fimbulwinter.find("numextramainpackspawns").text)
    fimbulwinterMiniPack = int(fimbulwinter.find("minipacksize").text)
    fimbulwinterSoftCap = int(fimbulwinter.find("wolfcountsoftcap").text)
    fimbulwinterHardCap = int(fimbulwinter.find("wolfcounthardcap").text)
    # Seemingly:
    # 1) Targets all non-friendly TCs with main packs (down to 2 per pack once soft cap)
    # 2) Spawns extra 5 main packs on random TCs (skip if soft cap reached)
    # 3) Dumps 2 wolves on VCs (skip if soft cap reached)
    fimbulwinterItems = [f"Spawns Fimbulwinter Wolves all over the map.  At the end of the duration, any surviving wolves die.", f"First, spawns {fimbulwinterMainPack} Fimbulwinter Wolves on every Settlement that isn't controlled by you or your allies, starting with unowned settlements. Once {fimbulwinterSoftCap} total wolves are spawned, the pack size is reduced to {fimbulwinterMiniPack}. No more than {fimbulwinterHardCap} wolves can be spawned under any circumstances.", f"If {fimbulwinterSoftCap:0.3g} or fewer wolves have been spawned at this point, picks {fimbulwinterExtraMainPacks} non-friendly settlement{'s' if fimbulwinterExtraMainPacks > 1 else ''} at random, and spawns an additional {fimbulwinterMainPack} wolves around {'them' if fimbulwinterExtraMainPacks > 1 else 'it'}.", f"If less than {fimbulwinterSoftCap:0.3g} total wolves have been spawned, spawns an additional {fimbulwinterMiniPack} wolves around enemy Village Centers until {fimbulwinterSoftCap:0.3g} total wolves are spawned or all Village Centers have been targeted.", f"Wolf packs wander up to {float(fimbulwinter.find('maxpackwanderdistance').text):0.3g}m from their target, seeking out things to attack.", "{duration}", unitdescription.describeUnit("FimbulwinterWolf")]
    godPowerProcessingParams["Fimbulwinter"] = GodPowerParams(fimbulwinterItems)

    nidhogg = findGodPowerByName("Nidhogg")
    nidhoggItems = [f"Summons Nidhogg at a location of your choice.", unitdescription.describeUnit("Nidhogg")]
    godPowerProcessingParams["Nidhogg"] = GodPowerParams(nidhoggItems)

    inferno = findGodPowerByName("Inferno")
    infernoDamageInterval = (float(inferno.find("stampede").attrib['attackinterval'])/1000) + DAMAGE_INTERVAL_BUG_AMOUNT
    infernoItems = [f"Summons the great flaming wolf Fenrir, who appears after 1.5 seconds, runs in the direction of your choice for 4.3 seconds, and then explodes.", f"Being near Fenrir as he moves damages enemy units only. DPS: {protoGodPowerDamage('Fenrir', 'HandAttack', 1/infernoDamageInterval)}", f"Fenrir's explosion affects both friends and foes, and inflicts {protoGodPowerDamage('Fenrir', 'SelfDestructAttack')}", f"All players have {float(common.protoFromName('Fenrir').find('los').text):0.3g} LOS around Fenrir, which persists for {float(common.protoFromName('RevealerToAllLifespan').find('lifespan').text):0.3g} seconds after he explodes."]
    godPowerProcessingParams["Inferno"] = GodPowerParams(infernoItems)

    deconstruction = findGodPowerByName("Deconstruction")
    deconstructionRate = 1/float(deconstruction.find("timefactor").text)
    deconstructionItems = [f"Reverses the construction of {{playerrelationpos}} {{attacktargets}}. The resource cost of the building is refunded immediately. Buildings are unbuilt at {deconstructionRate} Build Points a second (Greek/Norse build at 1BP/second). Dropsites can still be used to deposit resources while they are being deconstructed."]
    godPowerProcessingParams["Deconstruction"] = GodPowerParams(deconstructionItems)

    shockwave = findGodPowerByName("Shockwave")
    shockwaveItems = [f"Sends {{playerrelationpos}} units flying {float(shockwave.find('minthrowdistance').text):0.3g}-{float(shockwave.find('maxthrowdistance').text):0.3g}m, and stuns them for {float(shockwave.find('stunlength').text):0.3g} second upon landing. Units flying through the air cannot be attacked.", "{radius}"]
    godPowerProcessingParams["Shockwave"] = GodPowerParams(shockwaveItems)

    gaiaforest = findGodPowerByName("GaiaForest")
    gaiaforestTree = common.protoFromName('TreeGaia')
    gaiaforestAvoidList = []
    for item in gaiaforest.findall("placementrestriction"):
        gaiaforestAvoidList += common.getListOfDisplayNamesForProtoOrClass(item.text, plural=True)
    gaiaforestAvoidDistance = float(gaiaforest.find("placementrestriction").attrib['radius'])
    gaiaforestItems = [f"Creates {float(gaiaforest.find('totalnumberoftrees').text):0.3g} trees in the targeted area. These trees contain {icon.resourceIcon('wood')} {round(float(gaiaforestTree.find('initialresource').text))} and are gathered {100*(float(gaiaforestTree.find('gatherratemultiplier').text)-1.0):0.3g}% faster. Cannot spawn trees within {gaiaforestAvoidDistance:0.3g}m of {common.commaSeparatedList(list(set(gaiaforestAvoidList)), 'or')}."]
    godPowerProcessingParams["GaiaForest"] = GodPowerParams(gaiaforestItems)

    carnivora = findGodPowerByName("Carnivora")
    carnivoraItems = [f"Spawns an aggressive immobile plant on land or water that persists until killed.", "<tth>Land:", unitdescription.describeUnit("Carnivora")]
    #carnivoraItems += ["<tth>Water:", unitdescription.describeUnit("WaterCarnivora")]
    godPowerProcessingParams["Carnivora"] = GodPowerParams(carnivoraItems)

    valor = findGodPowerByName("Valor")
    valorItems = ["Instantly converts one of {playerrelationpos} units into its Hero form, and fully heals it in the process."]
    godPowerProcessingParams["Valor"] = GodPowerParams(valorItems)

    spiderlair = findGodPowerByName("SpiderLair")
    spiderlairHatchTime = float(spiderlair.find("hatchtime").text)
    spiderlairHatchTimeText = f"{spiderlairHatchTime+float(spiderlair.find('hatchintervalmin').text):0.3g}-{spiderlairHatchTime+float(spiderlair.find('hatchintervalmax').text):0.3g}"
    spiderlairItems = [f"Spawns {int(spiderlair.find('numbertocreate').text)} Spider Eggs in a line, with {float(spiderlair.find('separationdistance').text):0.3g}m between them. Eggs are visible and attackable for {spiderlairHatchTimeText} seconds. After this time they sink into the ground and are invisible to enemies.", f"When {{playerrelationpos}} {{attacktargets}} come within {float(spiderlair.find('spiderattackrange').text):0.3g}m of a spider, the spider becomes barely visible for {float(spiderlair.find('warntime').text):0.3g} seconds, in which time the victim can move away. If they do not, the hatched spider kills them. Each spider can kill one victim this way.", f"Dormant spider eggs provide you with {float(common.protoFromName('Spider').find('los').text):0.3g} LOS until hatched."]
    godPowerProcessingParams["SpiderLair"] = GodPowerParams(spiderlairItems)

    traitor = findGodPowerByName("Traitor")
    traitorItems = ["Instantly converts one enemy unit. The unit uses your upgrades instead of what it had originally. The converted unit has any special attacks recharged and ready for immediate usage. Units with veterancy bonuses (eg Hydras) lose them when converted."]
    godPowerProcessingParams["Traitor"] = GodPowerParams(traitorItems)

    chaos = findGodPowerByName("Chaos")
    chaosDurationBase = float(chaos.find("uniteffecttimeseconds").text)
    chaosDurationShared = float(chaos.find("sharedeffecttimeseconds").text)
    chaosItems = [f"Makes one or more targets become uncontrollable and attack anything nearby, including their allies. Affects {{playerrelationpos}} {{attacktargets}}. The duration of the effect depends on the number of targets hit: it lasts {chaosDurationBase:0.3g} + ({chaosDurationShared:0.3g}/number of affected units) seconds.", "{radius}"]
    godPowerProcessingParams["Chaos"] = GodPowerParams(chaosItems)

    hesperidestree = findGodPowerByName("HesperidesTree")
    hesperidestreeNumInstantDryads = [elem.text for elem in hesperidestree.findall("createunit")].count("Dryad")
    hesperidestreeItems = [f"Places a Hesperides Tree, which allows the production of Dryads for whoever controls it. Spawns {hesperidestreeNumInstantDryads} Dryads when placed. Hesperides Trees cannot be destroyed, but are captured when the owner has no units nearby."]
    hesperidestreeItems += [f"Each Hesperides Tree owned by a player allows them to produce a maximum of 5 Dryads at a time. {action.describeAction(common.protoFromName('HesperidesTree'), action.findActionByName('HesperidesTree', 'AreaHeal'))}"]
    #hesperidestreeItems += ["<tth>Hesperides Tree:", unitdescription.describeUnit("HesperidesTree")]
    hesperidestreeItems += ["<tth>Dryads:", unitdescription.describeUnit("Dryad")]
    godPowerProcessingParams["HesperidesTree"] = GodPowerParams(hesperidestreeItems)

    vortex = findGodPowerByName("Vortex")
    vortexItems = [f"Teleports all {{playerrelationpos}} {{attacktargets}} to a location of your choice. Garrisoned units are not affected."]
    godPowerProcessingParams["Vortex"] = GodPowerParams(vortexItems)

    tartariangate = findGodPowerByName("TartarianGate")
    tartariangateSpawns = float(tartariangate.find("maxnumspawns").text)
    tartariangateItems = [f"Allows you to place a Tartarian Gate. It can be placed overlapping most building types, and will instantly destroy them. Produces {tartariangateSpawns:0.3g} Tartarian Spawn that are hostile to all, and are rapidly replaced by the gate if killed. The gate itself remains under your control until destroyed. It benefits from building hitpoint upgrades, and can be manually deleted. While active, all players have {float(common.protoFromName('RevealerToAll').find('los').text):0.3g} LOS around the gate."]
    #tartariangateItems += ["<tth>Tartarian Spawn:", unitdescription.describeUnit("TartarianSpawn")]
    godPowerProcessingParams["TartarianGate"] = GodPowerParams(tartariangateItems)

    implode = findGodPowerByName("Implode")
    # damageintervalseconds - interval for the sphere's handattack, not +50ms bugged
    # 1 unit suck = 627 vs migdol
    # 2 unit suck = 684

    # So the explosion buffing is probably just
    #     <poweraccumulationincrement>0.1</poweraccumulationincrement>
    #     <maximumaccumulatedpower>1.0</maximumaccumulatedpower>
    # 60 hoplites in
    # 12 took 100 dmg
    # 13 took 50 dmg
    # 35 died
    implodeUnitSuckRate = 1/((float(implode.find("unitimplodetimedelaymin").text)+float(implode.find("unitimplodetimedelaymax").text))/2)
    # It sucks units with the same positional bias as lightning storm
    implodeItems = [f"Creates a floating sphere that begins to suck in all players' {{attacktargets}} within {float(implode.find('pullradius').text):0.3g}m. Prevents garrisoning in the area of effect. The sphere soon begins to suck up about {implodeUnitSuckRate:0.3g} units per second.  Units designated to be pulled are connected to the sphere with a blue ray: if the units are able to get {float(implode.find('unitescaperadius').text):0.3g}m from the sphere before being pulled in, they escape unharmed. Preferentially pulls units closest to the southeast edge of the map first."]
    implodeItems += [f"Units that are sucked up by the sphere take {protoGodPowerDamage('ImplodeSphere', 'HandAttack', damageOnly=True)} when they reach the sphere, and again every {float(implode.find('damageintervalseconds').text):0.3g} second until the sphere explodes."]
    implodeItems += [f"The sphere explosion inflicts {protoGodPowerDamage('ImplodeShockwave', 'HandAttack', damageOnly=True)} This damage strikes all objects within {float(implode.find('exploderadius').text):0.3g}m and has no damage falloff. Units sucked into the sphere are not hit by this. The explosion damage is increased by {100*float(implode.find('poweraccumulationincrement').text):0.3g}% per unit sucked into the sphere, to a maximum damage bonus of {100*float(implode.find('maximumaccumulatedpower').text):0.3g}%."]
    implodeItems += [f"Friendly objects take only 10% damage from both sources.", "{powerblocker}", "{los}"]
    godPowerProcessingParams["Implode"] = GodPowerParams(implodeItems)

    peachblossomItems = [unitdescription.describeUnit("ThePeachBlossomSpring")]
    godPowerProcessingParams["ThePeachBlossomSpring"] = GodPowerParams(peachblossomItems)

    creation = findGodPowerByName("Creation")
    creationBaseQuantity = int(creation.find("createunit").attrib['quantity'])
    creationProto = creation.find("createunit").text
    creationItems = [f"Summons Clay Peasants. The quantity produced depends on age. At the end of the power, any surviving Clay Peasants die and resources they are holding are lost."]
    creationItems += [f" {icon.BULLET_POINT} {common.AGE_LABELS[0]}: {creationBaseQuantity}"]
    creationItems += [f" {icon.BULLET_POINT} {common.AGE_LABELS[index+1]}: {int(elem.attrib['quantityaddon'])+creationBaseQuantity}" for index, elem in enumerate(creation.findall("ageadjustment"))]
    creationItems += ["{duration}"]
    creationItems += ["<tth>Clay Peasant:", unitdescription.describeUnit(creationProto)]
    godPowerProcessingParams["Creation"] = GodPowerParams(creationItems)

    prosperousseeds = findGodPowerByName("ProsperousSeeds")
    prosperousseedsItems = [f"Replaces up to {common.findAndFetchText(prosperousseeds, 'numbertotransform', 0, float):0.3g} Farms with Shennong's Farms.", "{radius}"]
    prosperousseedsItems += [unitdescription.describeUnit("FarmShennong")]
    godPowerProcessingParams["ProsperousSeeds"] = GodPowerParams(prosperousseedsItems)

    lightningweapons = findGodPowerByName("LightningWeapons")
    lightningweaponsItems = ["Grants {playerrelation} the following effects:", *describeGodPowerEffectsLikeDataTech(lightningweapons), "{duration}"]
    godPowerProcessingParams["LightningWeapons"] = GodPowerParams(lightningweaponsItems)

    earthwall = findGodPowerByName("EarthWall")
    earthwallSegments = common.findAndFetchText(earthwall, "wallsegmentcount", 0, int)
    earthwallDamagePercent = float(earthwall.find("damagetiers/damagetier").text)
    earthwallSegmentsToDestroyEntirely = 1/earthwallDamagePercent
    earthwallBuildPoints = common.findAndFetchText(common.protoFromName("EarthWall"), "buildpoints", 0.0, float)
    earthwallBuildRate = common.findAndFetchText(common.protoFromName("EarthWall"), "autobuildrate", 1.0, float)
    earthwallPercentHealth = 100.0 * common.findAndFetchText(common.protoFromName("EarthWall"), "initialhitpoints", 1.0, float) / common.findAndFetchText(common.protoFromName("EarthWall"), "maxhitpoints", 1.0, float)
    earthwallBuildTime = earthwallBuildPoints/earthwallBuildRate
    earthwallItems = [f"Creates a ring of {earthwallSegments} Earth Wall segments around the targeted friendly building. They start at {earthwallPercentHealth:0.3g}% hitpoints, and build up to full strength over {earthwallBuildTime:0.3g} seconds. These segments all function like gates.", "{radius}"]
    earthwallItems += [unitdescription.describeUnit("EarthWall")]
    godPowerProcessingParams["EarthWall"] = GodPowerParams(earthwallItems)

    vanish = findGodPowerByName("Vanish")
    vanishItems = [f"All {{playerrelationpos}} {{attacktargets}} in the targeted area at the time of casting become invisible. When each individual unit attacks or performs another hostile action, its invisibility ends for that unit only. Damaging trails left behind units like Nezha and Fei are disabled while invisible, but auras are not.", "{duration}", "{radius}"]
    godPowerProcessingParams["Vanish"] = GodPowerParams(vanishItems)

    forestprotection = findGodPowerByName("ForestProtection")
    forestprotectionInterval = common.findAndFetchText(forestprotection, "staytime", 1.0, float)
    forestprotectionRootTime = common.findAndFetchText(forestprotection, "rootedtime", 1.0, float)
    forestprotectionDamageHero = float(forestprotection.find("rooteddamage[.='Hero']").attrib['damage'])
    forestprotectionDamageUnit = float(forestprotection.find("rooteddamage[.='Unit']").attrib['damage'])
    forestprotectionHeroMultiplier = forestprotectionDamageHero/forestprotectionDamageUnit
    forestprotectionHeal = common.findAndFetchText(forestprotection, "rootedheal", 1.0, float)
    forestprotectionSlowHeal = common.findAndFetchText(forestprotection, "slowhealmultiplier", 1.0, float)
    forestprotectionItems = [f"Causes one of {{playerrelationpos}} Buildings to produce a defensive aura until it is destroyed. Every {forestprotectionInterval:0.3g} seconds, enemy {{attacktargets}} in the area take {icon.damageTypeIcon('divine')} {forestprotectionDamageUnit:0.3g} ({icon.iconUnitClass('Hero')} x{forestprotectionHeroMultiplier:0.3g}) and become unable to move for {forestprotectionRootTime} seconds. Friendly units in the area of effect are healed {forestprotectionHeal:0.3g} hitpoints per second. Targets that have moved or been involved in combat in the last 3 seconds are healed at {100*forestprotectionSlowHeal:0.3g}% speed."]
    forestprotectionItems += ["{radius}"]
    godPowerProcessingParams["ForestProtection"] = GodPowerParams(forestprotectionItems)

    droughtland = findGodPowerByName("DroughtLand")
    droughtlandDamageProportion = float(droughtland.find("initialdamage").attrib['fraction'])
    droughtlandDamageTarget = droughtland.find("initialdamage").text
    droughtlandAllyRatio = common.findAndFetchText(droughtland, "allydamageratio", 0.0, float)
    droughtlandCreep = globals.dataCollection['terrain_unit_effects.xml'].find("terrainuniteffect[@name='DroughtCreepEffect']")
    droughtlandHpModification = float(droughtlandCreep.find("effect[@type='maxHP']").attrib['amount'])

    if droughtlandAllyRatio != 0.0:
        raise ValueError("DroughtLand friendly fires now")

    droughtlandItems = [f"Enemy {common.getDisplayNameForProtoOrClass(droughtlandDamageTarget, True)} in the targeted area immediately lose {100*droughtlandDamageProportion:0.3g}% of their current hitpoints. For the duration of the power, their maximum hitpoints is lowered by {100*droughtlandHpModification:0.3g}%. Friendly buildlings in the area are completely unaffected."]
    droughtlandItems += ["{radius}", "{duration}"]
    godPowerProcessingParams["DroughtLand"] = GodPowerParams(droughtlandItems)

    venombeast = findGodPowerByName("VenomBeast")
    venombeastBaseQuantity = int(venombeast.find("createunit").attrib['quantity'])
    venombeastProto = venombeast.find("createunit").text
    venombeastItems = [f"Summons Fei. The quantity produced depends on age. At the end of the power, any surviving Fei die."]
    venombeastItems += [f" {icon.BULLET_POINT} {common.AGE_LABELS[index+1]}: {int(elem.attrib['quantityaddon'])+venombeastBaseQuantity}" for index, elem in enumerate(venombeast.findall("ageadjustment")) if index > 0]
    venombeastItems += ["{duration}"]
    venombeastItems += ["<tth>Fei:", unitdescription.describeUnit(venombeastProto)]
    godPowerProcessingParams["VenomBeast"] = GodPowerParams(venombeastItems)

    # AreaAttack seems to be used when it hits ground and has distance falloff
    # In any case (?) is a fire field created?

    # Strike count seems to be ~255, which gets hit by the accuracy
    blazingprairie = findGodPowerByName("BlazingPrairie")
    blazingprairieAccuracy = common.findAndFetchText(blazingprairie, "accuracy", 0.0, float)
    blazingprairieStrike = blazingprairie.find("strikeproto").text
    blazingprairieAreaAttack = blazingprairie.find("areaattackaction").text
    blazingprairieFireArea = blazingprairie.find("groundimpactvfxproto").text
    blazingprairieItems = [f"Summons a storm of about 255 fireballs. Each fireball has a {100*blazingprairieAccuracy:0.3g}% chance to hit random {{playerrelationpos}} {{attacktargets}}. The remainder strike a random location, but are more likely to land towards the centre. Aimed strikes inflict {protoGodPowerDamage(blazingprairieStrike, 'HandAttack')} Random unaimed fireballs damage anything close enough to them (with damage falloff): {protoGodPowerDamage(blazingprairieStrike, blazingprairieAreaAttack)} All fireballs leave lingering fire: {action.actionDamageOverTimeArea(blazingprairieFireArea)}", "{radius}", "{duration}"]
    godPowerProcessingParams["BlazingPrairie"] = GodPowerParams(blazingprairieItems)
    
    greatflood = findGodPowerByName("GreatFlood")
    greatfloodInitialVelocity = common.findAndFetchText(greatflood, "initialvelocity", 0.0, float)
    greatfloodFinalVelocity = common.findAndFetchText(greatflood, "finalvelocity", 0.0, float)
    greatfloodRampTime = common.findAndFetchText(greatflood, "ramptime", 0.0, float)
    # Assuming: linear speedup over ramp time
    # I didn't bother to test this though, but the point that it goes WAY FURTHER than the cursor suggests
    greatfloodAccel = (greatfloodFinalVelocity-greatfloodInitialVelocity)/greatfloodRampTime
    greatfloodSpeedupDisplacement = 0.5*greatfloodAccel*greatfloodRampTime*greatfloodRampTime
    greatfloodRemainingTime = common.findAndFetchText(greatflood, "activetime", 0.0, float) - greatfloodRampTime
    greatfloodRemainingDisplacement = greatfloodRemainingTime*greatfloodFinalVelocity
    greatfloodDistance = greatfloodSpeedupDisplacement+greatfloodRemainingDisplacement
    # Friendly fire multiplier of 0.1 seems to be hardcoded
    greatfloodProto = greatflood.find("waveprotounit").text
    greatfloodInitialAction = greatflood.find("initialattackname").text
    # Not bugged for +0.05ms
    greatfloodInterval = common.findAndFetchText(greatflood, "attackinterval", 1.0, float)
    greatfloodDPS = protoGodPowerDamage(greatfloodProto, "HandAttack", damageMultiplier=1.0/greatfloodInterval)
    greatfloodItems = [f"Summons a gigantic wave that travels in your chosen direction. On initial contact, hits {{playerrelationpos}} {{attacktargets}} for {protoGodPowerDamage(greatfloodProto, greatfloodInitialAction)} Objects remaining in contact with the wave suffer damage per second: {greatfloodDPS} Affected Units (except Titans) are swept along with the wave as it travels.", "Friendly targets take 10% damage from both sources, but are not swept away.", f"The wave speeds up to {greatfloodFinalVelocity:0.3g} m/s over {greatfloodRampTime:0.3g}s as it travels {greatfloodDistance:0.3g}m before dissipating.", "{duration}"]
    godPowerProcessingParams["GreatFlood"] = GodPowerParams(greatfloodItems)

    yinglong = findGodPowerByName("YinglongsWrath")
    yinglongItems = [f"Summons Yinglong at a location of your choice.", unitdescription.describeUnit("YingLong")]
    godPowerProcessingParams["YinglongsWrath"] = GodPowerParams(yinglongItems)


    titangate = findGodPowerByName("TitanGate")
    titangateRecharge = "{:0.3g}".format(float(techtree.find("tech[@name='WonderAgeTitan']/effects/effect[@subtype='PowerROF']").attrib['amount']))
    titangateCost= "{:0.3g}".format(float(techtree.find("tech[@name='WonderAgeTitan']/effects/effect[@subtype='PowerCost']").attrib['amount']))
    titangateItems = [f"Places a Titan Gate at 50% hitpoints. When fully built, unleashes a Titan.", "Can only be recast if you have a Wonder."]
    godPowerProcessingParams["TitanGate"] = GodPowerParams(titangateItems, overrideRecharge=titangateRecharge, overrideCost=titangateCost)


    godpowers = globals.dataCollection["god_powers_combined"]

    stringIdsByOverwriters = {}
    for godpower in godpowers:
        strid = common.findAndFetchText(godpower, "rolloverid", None)
        if strid is not None:
            value = processGodPower(godpower)

            if value is not None:
                if strid not in stringIdsByOverwriters:
                    stringIdsByOverwriters[strid] = {}
                if value not in stringIdsByOverwriters[strid].values():
                    stringIdsByOverwriters[strid][godpower] = value

    common.handleSharedStringIDConflicts(stringIdsByOverwriters)