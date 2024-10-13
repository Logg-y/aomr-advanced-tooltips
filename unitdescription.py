import globals
from xml.etree import ElementTree as ET
from typing import Union, Dict, List, Callable, Any, Tuple
import dataclasses
import common
from common import protoFromName, findAndFetchText
import icon
import action
import math
import os
import tech

# This also decides the order in which things appear in the list
NOTABLE_UNIT_CLASSES = ("Hero", "AbstractInfantry", "AbstractArcher", "AbstractCavalry", "AbstractSiegeWeapon", "AbstractVillager", "AbstractArcherShip", "AbstractSiegeShip", 
                        "AbstractCloseCombatShip", "MythUnit", "HeroShadowUpgraded", "HumanSoldier", "Ship", "Building", "CavalryLineUpgraded", "InfantryLineUpgraded", "ArcherLineUpgraded", 
                        "Huntable", "FoodDropsite", "WoodDropsite", "GoldDropsite", "LogicalTypeBuildingEmpoweredForLOS", "LogicalTypeArchaicMythUnit", "LogicalTypeClassicalMythUnit", "LogicalTypeHeroicMythUnit",
                        "LogicalTypeAffectedByCeaseFireBuildingSlow")

# Key : [list of unit classes that are hidden if a unit has this class]
# Stating both "ship" and "archer ship" is a bit pointless.
UNIT_CLASS_SUPPRESSION = {
"AbstractArcherShip":["Ship"],
"AbstractCloseCombatShip":["Ship"],
"AbstractSiegeShip":["Ship"],
"LogicalTypeArchaicMythUnit":["MythUnit"],
"LogicalTypeClassicalMythUnit":["MythUnit"],
"LogicalTypeHeroicMythUnit":["MythUnit"],
"LogicalTypeMythicMythUnit":["MythUnit"],
}

# These all get unworkably long.
BANNED_STRINGS = (
"STR_UNIT_ANIMAL_OF_SET_LR",
"STR_ABILITY_EMPOWER_LR",
"STR_ABILITY_HEAL_LR",
"STR_ABILITY_GULLINBURSTI_LR",
)

# Ignore these units, typically because they share rollover text string ids and that makes generating tooltips for them squash something more important
IGNORE_UNITS = (
"TriremeWrecked",
"HopliteSPC",
"AutomatonSPC",
"HippeusHorse",
"HippeusCinematic",
"ValkyrieHorse",
"TentSPC",
"SkyPassageSPC",
"TownCenterAbandoned",
"ArcticWolfSPC",
"CrownedCraneSPC",
"DeerSPC",
"Guardian",
"GuardianTNA",
"OxCartBuilding",
"PegasusWingedMessenger",
"PegasusBridleOfPegasus",
"SerpentPredator",
"SummoningTreeProp",
"ChickenEvil",
"TrojanHorseBuilding",
"TamariskTreeDead",
#"GullinburstiArchaic",
#"GullinburstiClassical",
#"GullinburstiHeroic",
#"GullinburstiMythic",
"PlentyVaultKOTH",
"KastorWithStaff",
"WallConnector",
"PhoenixFromEgg",
"TartarianGatePlacement",
)


UNIT_CLASSES_COLOUR = lambda s: "<color=0.8,0.8,0.8>" + s + "</color>"
UNIT_ABILITY_SOURCE_COLOUR = lambda s: "<color=0.8,0.8,0.8>" + s + "</color>"



def defaultIncludeVanillaDescription(proto: ET.Element):
    if proto.find("./unittype[.='Building']") is not None:
        return True
    if proto.find("./protoaction") is None:
        return True
    return False


def killrewardText(proto: Union[str, ET.Element]):
    proto = protoFromName(proto)
    killrewards = proto.findall("killreward")
    killRewardStrings = []
    text = ""
    for reward in killrewards:
        killRewardStrings.append(f"{icon.resourceIcon(reward.attrib['resourcetype'])} {float(reward.text):0.3g}")
    if len(killRewardStrings) > 0:
        text = f"Gives {' '.join(killRewardStrings)} to the killer when slain. Gives the resources to enemies if deleted."
    return text

def spawnText(proto: Union[str, ET.Element]):
    proto = protoFromName(proto)
    spawns = proto.findall("spawn")
    spawnstrings = []
    for spawn in spawns:
        if spawn.attrib['type'] == "dead":
            targetProto = protoFromName(spawn.text)
            if targetProto.find("./flag[.='NotDeathTracked']") is not None:
                continue
            count = int(spawn.attrib["count"])
            if count == 1:
                spawnstrings.append(f"On death, spawns a {common.getObjectDisplayName(targetProto)}.")
            else:
                spawnstrings.append(f"On death, spawns {count}x {common.getObjectDisplayName(targetProto)}.")
    return " ".join(spawnstrings)

def dependentUnitsTextList(proto: Union[str, ET.Element]) -> List[str]:
    dependentUnits = proto.findall("dependentunit")
    dependentsByType = {}
    for dependent in dependentUnits:
        dependentProto = protoFromName(dependent.text)
        if len(dependentProto.findall("protoaction")) > 0:
            dependentsByType[dependentProto] = dependentsByType.get(dependentProto, 0) + 1
    
    items = []
    for dependentProto, count in dependentsByType.items():
        items.append(f"Has {count}x {common.getObjectDisplayName(dependentProto)} attached to it:")
        items += UnitDescription().describeActions(dependentProto)
    return items

def directionalarmorText(proto: Union[str, ET.Element]):
    proto = protoFromName(proto)
    directionalNode = proto.find("directionalarmor")
    if directionalNode is not None:
        return f"Takes {float(directionalNode.attrib['value']):0.3g}x damage if attacked from within {math.degrees(float(directionalNode.attrib['angle'])):0.3g}° of its facing direction."
    return ""


def veterancyDamagePoints(proto: Union[str, ET.Element]):
    if isinstance(proto, str):
        proto = protoFromName(proto)
    ranks = proto.find("veterancyranks")
    if ranks is None:
        return ""
    dmgs = [totaldamageNode.text for totaldamageNode in ranks.findall(".//*totaldamage")]
    return "/".join(dmgs)

def veterancyDamageTargets(proto: Union[str, ET.Element]):
    if isinstance(proto, str):
        proto = protoFromName(proto)
    bonus = proto.find("veterancybonus")
    if bonus is None:
        return ""
    includeTypes = bonus.find("includetypes")
    if includeTypes is None:
        return ""
    unitClasses = [x.text for x in includeTypes]
    return action.targetListToString(unitClasses, "or")

VETERANCY_MODIFY_NAMES = {
    "MaxHP": "Max HP",
    "NumProjectiles": "Projectile Count",
    "VisualScale": "Visual Scale",
    "Damage": "Damage"
}

VETERANCY_MODIFY_RELATIVITY = {
    "MaxHP": "multiply",
    "Damage": "multiply",
    "NumProjectiles": "increase",
    "VisualScale": "increase"
}

def veterancyEffects(proto: Union[str, ET.Element]):
    if isinstance(proto, str):
        proto = protoFromName(proto)
    bonus = proto.find("veterancybonus")
    if bonus is None:
        return ""
    ranks = bonus.findall("rank")
    if len(ranks) == 0:
        return ""
    modifyTargets = {modifyNode.attrib['modifytype'] for modifyNode in bonus.findall("./*veterancymodify")}
    textByTarget = []
    for target in modifyTargets:
        valuesByRank = []
        relativity = VETERANCY_MODIFY_RELATIVITY[target]
        for rank in ranks:
            targetNode = rank.find(f"./*[@modifytype='{target}']")
            if targetNode is None:
                if len(valuesByRank) == 0:
                    valuesByRank.append("1" if relativity == "multiply" else "0")
                else:
                    valuesByRank.append(valuesByRank[-1])
            else:
                valuesByRank.append(f"{float(targetNode.text):0.3g}")
        textByTarget.append(f"{relativity} {VETERANCY_MODIFY_NAMES.get(target, target)} by {'/'.join(valuesByRank)}")
    if len(textByTarget) == 0:
        return ""
    if len(textByTarget) == 1:
        return textByTarget[0]
    separated = ", ".join(textByTarget[:-1])
    separated += " and " + textByTarget[-1]
    return separated

def veterancyText(proto: Union[str, ET.Element], rankName="rank", ignoreExperienceUnitFlag=False):
    proto = protoFromName(proto)
    if not ignoreExperienceUnitFlag and proto.find("./flag[.='ExperienceUnit']") is None:
        return ""
    damagePoints = veterancyDamagePoints(proto)
    if damagePoints != "":
        return f"Gains additional {rankName}s after dealing a total of {damagePoints} damage to {veterancyDamageTargets(proto)}. Additional {rankName}s {veterancyEffects(proto)}."
    return ""



NON_ACTION_OBSERVATIONS = {
    "killreward":killrewardText,
    "spawns":spawnText,
    "dependentunits":dependentUnitsTextList,
    "directionalarmor":directionalarmorText,
    "veterancy":veterancyText,
    "other":lambda dummy, x="": x,
}

def checkProtoFlag(proto: ET.Element, name: str, flag: str):
    return proto.find(f"{name}/[.='{flag}']") is not None

GOD_POWER_FLAG_PREDICTIONS: Dict[str, Tuple[str, Callable[[ET.Element], bool]]] = {
    "Bolt":("LogicalTypeValidBoltTarget", lambda x: checkProtoFlag(x, "unittype", "Unit")),
    "Traitor":("LogicalTypeValidTraitorTarget", lambda x: checkProtoFlag(x, "unittype", "Unit")),
    "Spy":("LogicalTypeValidSpyTarget", lambda x: checkProtoFlag(x, "unittype", "Unit")),
    "Shockwave":("LogicalTypeValidShockwaveTarget", lambda x: checkProtoFlag(x, "unittype", "Unit") and not checkProtoFlag(x, "flag", "FlyingUnit")),
    "Earthquake":("LogicalTypeEarthquakeAttack", lambda x: not checkProtoFlag(x, "flag", "FlyingUnit") and not checkProtoFlag(x, "flag", "Invulnerable")),
    "Frost":("LogicalTypeValidFrostTarget", lambda x: checkProtoFlag(x, "unittype", "Unit") and not checkProtoFlag(x, "flag", "FlyingUnit")),
    "Tornado":("LogicalTypeValidTornadoAttack", lambda x: not checkProtoFlag(x, "flag", "Invulnerable")),
    "Restoration":("LogicalTypeAffectedByRestoration", lambda x: (checkProtoFlag(x, "unittype", "Building") or checkProtoFlag(x, 'unittype', 'LogicalTypeHealed')) and not checkProtoFlag(x, "flag", "Invulnerable")),
    "Shifting Sands":("LogicalTypeValidShiftingSandsTarget", lambda x: checkProtoFlag(x, "unittype", "Unit") and (checkProtoFlag(x, 'movementtype', 'land') or checkProtoFlag(x, 'movementtype', 'air'))),
}

# Label if true, Label if false, prediction, actual
UNIT_CLASS_PREDICTIONS: Tuple[Tuple[str, str, Callable[[ET.Element], bool], Callable[[ET.Element], bool]]] = (
    # Any air/water movement types or non-units that can enter transports are noteworthy
    # Technically, Sentinels and Water Carnivora have LogicalTypeGarrisonInShips but can't actually board :(
    ("Transportable", "Untransportable", lambda x: checkProtoFlag(x, "unittype", "Unit") and checkProtoFlag(x, 'movementtype', 'land'), lambda x: checkProtoFlag(x, 'unittype', 'LogicalTypeGarrisonInShips') and findAndFetchText(x, "maxvelocity", 0.0, float) > 0.0),
    # Any nonunit that can be healed, or unit that can't be healed is noteworthy
    ("Healable", "Unhealable", lambda x: checkProtoFlag(x, "unittype", "Unit"), lambda x: checkProtoFlag(x, 'unittype', 'LogicalTypeHealed') and not checkProtoFlag(x, 'unittype', 'Building')),

    ("Targeted by Meteor", "Not Targeted by Meteor", lambda x: not checkProtoFlag(x, "flag", "FlyingUnit") and not checkProtoFlag(x, "flag", "Invulnerable"), lambda x: checkProtoFlag(x, "unittype", "LogicalTypeValidMeteorTarget")),
)

# (nodename, nice looking label, datatype)
HISTORY_STRING_TAGS: Tuple[Tuple[str, str, type]] = (
    #("sizeclass", "Size Class", int),
    ("weightclass", "Weight Class", int),
    #("formationorder", "Formation Order", int),
)

@dataclasses.dataclass
class UnitDescription:
    # Additional unit classes, added to the end of the normal ones
    additionalClasses: List[str] = dataclasses.field(default_factory=list)
    # If true, additionalClasses instead completely replaces the automatically found ones
    overrideClasses: bool = False
    # Whether or not to hide the stats line (LOS, speed, EHP...)
    hideStats: bool = False

    # Additional text, added as a bullet point of its own at the end.
    additionalText: str = ""

    # A list of action names to hide.
    ignoreActions: List[str] = dataclasses.field(default_factory=list)
    # A list of action names to show, even if they aren't enabled by default
    showActionsIfDisabled: List[str] = dataclasses.field(default_factory=list)
    # A dict of ActionName:Text that goes before the action's normal text.
    preActionInfoText: Dict[str, str] = dataclasses.field(default_factory=dict)
    # A dict of ActionName:Text that goes after the action's normal text.
    postActionInfoText: Dict[str, str] = dataclasses.field(default_factory=dict)
    # A dict of ActionName:Text that replaces the action's normal text
    overrideActionInfoText: Dict[str, str] = dataclasses.field(default_factory=dict)
    # Overrides names of charge actions. Not very useful any more, as the vast majority of charge actions have a named ability to copy from
    chargeActionNames: Dict[str, str] = dataclasses.field(default_factory=dict)
    # A dict of ActionName:AbilityName. Will cause the given ability's tooltip to inherit whatever text is generated for the action.
    # This is needed only for abilities that are fundamentally tied to an action but don't specify the action in the game data, eg SelfDestructAttacks.
    linkActionsToAbilities: Dict[str, str] = dataclasses.field(default_factory=dict)
    
    # Whether or not to copy the default game one-liner description for a unit or not, or a function(protounit ET node) -> bool that decides that.
    includeVanillaDescription: Union[bool, Callable[[ET.Element], bool]] = defaultIncludeVanillaDescription
    # Forcibly override the base description of a unit from the vanilla one.
    overrideDescription: Union[str, None] = None

    # A dict of NON_ACTION_OBSERVATIONS:ability names. The relevant text describing the ability will be mirrored to the named ability's tooltip.
    passiveAbilityLink: Dict[str, str] = dataclasses.field(default_factory=dict)
    # Additional positional arguments for NON_ACTION_OBSERVATION handlers.
    nonActionObservationArgs: Dict[str, List[Any]] = dataclasses.field(default_factory=dict)
    # Override NON_ACTION_OBSERVATION text.
    overrideNonActionObservations: Dict[str, str] = dataclasses.field(default_factory=dict)
    # Hide non action observations
    hideNonActionObservations: bool = False

    # Additional text for the history file.
    historyText: str = ""

    def notableGodPowerFlags(self, protoUnit):
        affectedBy = []
        immuneTo = []
        for flag, pair in GOD_POWER_FLAG_PREDICTIONS.items():
            logicalType, predictor = pair
            hasLogicalType = checkProtoFlag(protoUnit, "unittype", logicalType)
            predictorResult = predictor(protoUnit)
            if predictorResult != hasLogicalType:
                if hasLogicalType:
                    affectedBy.append(flag)
                else:
                    immuneTo.append(flag)

        return affectedBy, immuneTo

    def unitClasses(self, protoUnit: ET.Element) -> str:
        unittypes = protoUnit.findall("unittype")
        if self.overrideClasses:
            orderedTypes = self.additionalClasses
        else:
            matchedTypes = []
            affectedBy, immuneTo = self.notableGodPowerFlags(protoUnit)
            for thisType in unittypes:
                if thisType.text in NOTABLE_UNIT_CLASSES:
                    matchedTypes.append(thisType.text)
            for thisType in matchedTypes[:]:
                for suppressType in UNIT_CLASS_SUPPRESSION.get(thisType, []):
                    if suppressType in matchedTypes:
                        matchedTypes.remove(suppressType)
            orderedTypes = []
            for thisType in NOTABLE_UNIT_CLASSES:
                if thisType in matchedTypes:
                    orderedTypes.append(common.UNIT_CLASS_LABELS[thisType])
            if action.findActionByName(protoUnit, "Pickup"):
                orderedTypes.append("Carries Relics")
            if checkProtoFlag(protoUnit, "flag", "KnockoutDeath"):
                orderedTypes.append("Knocked Out on Death")
            if checkProtoFlag(protoUnit, "flag", "Invulnerable"):
                orderedTypes.append("Invulnerable")
            if checkProtoFlag(protoUnit, "flag", "FlyingUnit"):
                orderedTypes.append("Flying")
            if checkProtoFlag(protoUnit, "flag", "NotCommandable"):
                orderedTypes.append("Uncontrollable")
            if checkProtoFlag(protoUnit, "flag", "NotRepairable") and not checkProtoFlag(protoUnit, "flag", "Invulnerable"):
                orderedTypes.append("Unrepairable")
            if checkProtoFlag(protoUnit, "unittype", "Building") and not checkProtoFlag(protoUnit, "unittype", "LogicalTypeTartarianGateValidOverlapPlacement"):
                immuneTo.append("Deconstruction")
            if checkProtoFlag(protoUnit, "unittype", "Building") and not checkProtoFlag(protoUnit, "unittype", "LogicalTypeBuildingThatCanBeEmpowered") and not checkProtoFlag(protoUnit, "unittype", "LogicalTypeBuildingEmpoweredForLOS"):
                orderedTypes.append("Unempowerable")
            
            if not checkProtoFlag(protoUnit, "unittype", "LogicalTypeFreezableMythUnit") and checkProtoFlag(protoUnit, "unittype", "MythUnit") and "Flying" not in orderedTypes:
                if not checkProtoFlag(protoUnit, "unittype", 'LogicalTypeValidFrostTarget'):
                    orderedTypes.append("Immune to Freeze/Petrify")

            for affected, unaffected, predictor, tester in UNIT_CLASS_PREDICTIONS:
                if predictor(protoUnit) != tester(protoUnit):
                    if tester(protoUnit):
                        orderedTypes.append(affected)
                    else:
                        orderedTypes.append(unaffected)

            if len(immuneTo) > 0:
                orderedTypes.append(f"Immune to {'/'.join(immuneTo)}")
            if len(affectedBy) > 0:
                orderedTypes.append(f"Affected by {'/'.join(affectedBy)}")
            if protoUnit.find("unittype[.='Unit']") is not None and protoUnit.find("unittype[.='LogicalTypeConvertsHerds']") is None:
                orderedTypes.append("Cannot convert Herdables")
            

            orderedTypes += self.additionalClasses
        unitClassesString = ""
        if len(orderedTypes) > 0:
            unitClassesString = UNIT_CLASSES_COLOUR("[" + (", ".join(orderedTypes)) + "] ")
        return unitClassesString
    def unitStats(self, protoUnit: ET.Element):
        if self.hideStats:
            return ""
        unitStatsString = ""
        velocity = findAndFetchText(protoUnit, "maxvelocity", 0.0, float)
        if velocity > 0.0:
            unitStatsString += f" {icon.iconSpeed()} {float(velocity):0.3g}"

        losNode = protoUnit.find("los")
        if losNode is not None:
            unitStatsString += f" {icon.iconLos()} {float(losNode.text):0.3g}"

        realHP = findAndFetchText(protoUnit, "maxhitpoints", 0.0, float)
        isInvulnerable = protoUnit.find("flag/[.='Invulnerable']") is not None
        if not isInvulnerable and realHP > 0.0:
            ehpString = f" Effective HP:"
            for dmgType in ("Hack", "Pierce", "Crush"):
                armorNode = protoUnit.find(f"armor[@type='{dmgType}']")
                if armorNode is not None:
                    armor = float(armorNode.attrib['value'])
                    if armor < 0.99:
                        vuln = 1.0 - armor
                        ehp = realHP/vuln
                        ehpString += f" {icon.armorTypeIcon(dmgType)} {float(ehp):0.0f}" 
            if len(ehpString) > 20:
                unitStatsString += ehpString
        
        if unitStatsString.endswith(","):
            unitStatsString = unitStatsString[:-1]
        
        return unitStatsString
    def describeActions(self, protoUnit: ET.Element) -> List[str]:
        descriptionsByActionName = {}
        protoName = protoUnit.attrib.get("name")
        actions = protoUnit.findall("protoaction")
        protoActionNames = {x.find("name").text for x in actions}
        tacticsFile = action.actionTactics(protoUnit, None)
        if tacticsFile is not None:
            actions += [x for x in tacticsFile.findall("action") if findAndFetchText(x, 'name', 'Unknown') not in protoActionNames]
        actionChargeTypes = {}
        for chargeType in action.ActionChargeType:
            actionChargeTypes[chargeType] = []
        for actionNode in actions:
            actionType = findAndFetchText(actionNode, "name", None)
            if actionType is None:
                raise ValueError(f"Bad action on {protoName}")
            if actionType in self.ignoreActions:
                continue
            active = findAndFetchText(actionNode, "active", 1, int)
            tactics = action.actionTactics(protoUnit, actionNode)
            chargeType = action.tacticsGetChargeType(tactics)
            if chargeType != action.ActionChargeType.NONE:
                actionChargeTypes[chargeType].append(actionType)
            if tactics is not None and active:
                active = findAndFetchText(tactics, "active", 1, int)
            description = action.describeAction(protoUnit, actionNode, chargeType, self.chargeActionNames.get(actionType, None), self.linkActionsToAbilities.get(actionType, None), overrideText=self.overrideActionInfoText.get(actionType, None))
            if not active and actionType not in self.showActionsIfDisabled:
                continue
            components = [self.preActionInfoText.get(actionType, ""), description, self.postActionInfoText.get(actionType, "")]
            components = [x.strip() for x in components if len(x.strip())]
            thisDescription = " ".join(components)
            descriptionsByActionName[actionType] = thisDescription
        
        # If any charge actions share cooldowns, this is the time to make a note of it
        # And all the variables are here (actionChargeTypes, descriptionsByActionName) to do that and stick a few words on to say they share
        # But I don't think this applies to anything except mountain giant punting which is quietly hidden behind one icon ingame anyway

        descriptions = list(descriptionsByActionName.values())

        return descriptions
    
    def generalObservations(self, protoUnit):
        if self.hideNonActionObservations:
            return []
        protoName = protoUnit.attrib['name']
        generalObservations = []
        regenerationNode = protoUnit.find("unitregen")
        if regenerationNode is not None:
            regenRate = float(regenerationNode.text)
            if regenRate != 0.0:
                generalObservations.append(f"{'Regenerates' if regenRate > 0 else 'Loses'} {abs(regenRate):0.3g} hitpoints/second.")
        # Set priest conversion
        priestConversion = action.findActionByName("Priest", "Convert")
        matchingNode = priestConversion.find(f"./*[@type='{protoName}']")
        if matchingNode is not None:
            generalObservations.append(f"Set's Priests convert this in {float(matchingNode.text):0.3g}s.")

        # Population
        popcapaddition = findAndFetchText(protoUnit, "populationcapaddition", 0.0, float)
        if popcapaddition > 0.0:
            generalObservations.append(f"Supports {icon.iconPop()} {int(popcapaddition)}.")

        # Lifespan
        lifespan = findAndFetchText(protoUnit, "lifespan", 0.0, float)
        if lifespan > 0.0:
            generalObservations.append(f"Dies after {lifespan:0.3g} seconds.")

        # Garrison
        maxcontainedNode = protoUnit.find('maxcontained')
        if maxcontainedNode is not None:
            containedTypes = [x.text for x in protoUnit.findall("contain")]
            if "LogicalTypePickable" in containedTypes:
                containedTypes.remove("LogicalTypePickable")
            if len(containedTypes) > 0:
                notContainedTypes = [x.text for x in protoUnit.findall("notcontain")]
                if len(notContainedTypes) == 0:
                    generalObservations.append(f"Garrisons up to {float(maxcontainedNode.text):0.3g} {action.targetListToString(containedTypes)}.")
                else:
                    generalObservations.append(f"Garrisons up to {float(maxcontainedNode.text):0.3g} {action.targetListToString(containedTypes)}, but not {action.targetListToString(notContainedTypes)}.")

        # At the time of writing this weird case covers the Petsuchos only
        if protoUnit.find("unittype[.='LogicalTypeFreezableMythUnit']") is None and protoUnit.find("unittype[.='MythUnit']") is not None and protoUnit.find("unittype[.='LogicalTypeValidFrostTarget']") is not None:
            generalObservations.append("Unaffected by Frost Giant freeze and petrifying special attacks, but is affected by Frost.")


        # Look to see if we have a respawn tech
        # This deranged search string works but is VERY slow, it's just much faster to iterate over the techtree once instead of running this query for every unit
        #respawnTechNode = globals.dataCollection["techtree.xml"].find(f"./tech[flag='Volatile']/effects/effect[@unit='{protoName}'][@type='CreateUnit']/../../delay")
        respawnTechNode = globals.respawnTechs.get(protoName, None)
        if respawnTechNode is not None:
            delayNode = respawnTechNode.find("delay")
            if delayNode is not None:
                generalObservations.append(f"Respawns in {float(delayNode.text):0.3g}s.")

        partisanCount = findAndFetchText(protoUnit, "partisancount", None, int)
        if partisanCount is not None:
            generalObservations.append(f"Poseidon: spawns {partisanCount} {findAndFetchText(protoUnit, 'partisantype', None)} when destroyed.")

        # General stuff that can be tied to passive abilities
        for passiveAbilityKey, handler in NON_ACTION_OBSERVATIONS.items():
            returned = self.overrideNonActionObservations.get(passiveAbilityKey, None)
            if returned is None:
                returned = handler(protoUnit, *self.nonActionObservationArgs.get(passiveAbilityKey, []))
            if isinstance(returned, list):
                generalObservations += returned
            else:
                generalObservations.append(returned)
            if passiveAbilityKey in self.passiveAbilityLink:
                abilityName = self.passiveAbilityLink[passiveAbilityKey]
                if isinstance(returned, list):
                    returned = "\\n".join(returned)
                abilityNode = globals.dataCollection["abilities_combined"].find(f"power[@name='{abilityName}']")
                if abilityNode is None:
                    raise ValueError(f"{protoName} was passed {passiveAbilityKey} -> {abilityName} but no ability data named {abilityName} was found")
                common.addToGlobalAbilityStrings(protoUnit, abilityNode, returned)
        return generalObservations
    
    def writeHistoryString(self, protoUnit):
        protoName = protoUnit.attrib['name']

        items = []
        
        if self.historyText:
            items.append(self.historyText)

        for nodename, label, datatype in HISTORY_STRING_TAGS:
            node = findAndFetchText(protoUnit, nodename, None, datatype)
            if node is not None:
                items.append(f"{label}: {node:0.3g}")

        obstructionX = findAndFetchText(protoUnit, "obstructionradiusx", None, float)
        obstructionZ = findAndFetchText(protoUnit, "obstructionradiusz", None, float)
        if obstructionX is not None and obstructionZ is not None:
            items.append(f"Collision size: {2*obstructionX:0.3g}x{2*obstructionZ:0.3g}m")


        # Faster to work out if we have anything to write before doing file ops for the string id
        if len(items) == 0:
            return

        historyFile = os.path.join(globals.historyPath, "units", f"{protoName}.txt")
        if not os.path.isfile(historyFile):
            #print(f"Warning: {protoName} has no history file!")
            return
        # Most of these are utf16, WITH BOM unlike some other places in the game.
        # But not all...
        # Shoutouts to Gargarensis.txt and Regent.txt that are utf8
        for attempt in range(0, 2):
            encoding = "utf-16" if attempt == 0 else "utf-8"
            try:
                with open(historyFile, "r", encoding=encoding) as f:
                    strid = f.readlines()[0].strip()
            except UnicodeError: # utf16 stream does not start with BOM
                continue
            if strid in globals.dataCollection["string_table.txt"]:
                break
        if strid not in globals.dataCollection["string_table.txt"]:
            # These cases are PROBABLY on the devs, but my attempts at parsing the string table might need some help too
            print(f"Warning: {protoName}'s history file string id {strid} not found, couldn't write its entry")
            return
        
        globals.stringMap[strid] = f"\\n".join(items) + "\\n"*3 + "----------\\n" + globals.dataCollection["string_table.txt"][strid]

        
        

    def generate(self, protoUnit):
        unitClassesString = self.unitClasses(protoUnit)        
        unitStatsString = self.unitStats(protoUnit)
        actionDescriptions = self.describeActions(protoUnit)
        generalObservations = self.generalObservations(protoUnit)

        description = ""
        if self.overrideDescription:
            description = self.overrideDescription
        elif (callable(self.includeVanillaDescription) and self.includeVanillaDescription(protoUnit)) or (not callable(self.includeVanillaDescription) and self.includeVanillaDescription):
            strId = findAndFetchText(protoUnit, "rollovertextid", None)
            if strId is not None:
                description = globals.dataCollection["string_table.txt"].get(strId, "")
        
        components = [unitClassesString.strip(), unitStatsString.strip(), description, *actionDescriptions, *generalObservations, self.additionalText.strip()]
        components = [component for component in components if len(component) > 0]
        self.writeHistoryString(protoUnit)
        return f"\\n {icon.BULLET_POINT} ".join(components)
        
def oracleAutoGatherFavorHelper(protoName):
    actionElem = action.findActionByName(protoName, 'AutoGatherFavor')
    rate = findAndFetchText(actionElem, "rate", None, float)
    modifybase = findAndFetchText(actionElem, "modifybase", None, float)
    modifymultiplier = findAndFetchText(actionElem, "modifymultiplier", None, float)
    rateCap = findAndFetchText(actionElem, "modifyratecap", None, float)
    quadraticTerm = rate * modifymultiplier/modifybase
    valueAtMax = rate + quadraticTerm * rateCap * rateCap
    return f"Produces more based on the current idle LOS boost amount. Without upgrades, this reaches {icon.resourceIcon('favor')} {valueAtMax:0.3g} per second. Area overlapping with other Oracles does not count."

def oracleHistoryText(protoName):
    actionElem = action.findActionByName(protoName, 'AutoGatherFavor')
    rate = findAndFetchText(actionElem, "rate", None, float)
    modifybase = findAndFetchText(actionElem, "modifybase", None, float)
    modifymultiplier = findAndFetchText(actionElem, "modifymultiplier", None, float)
    quadraticTerm = rate * modifymultiplier/modifybase
    # This number is so small that python's g formatting can't save me
    numberOfPlaces = 0
    while numberOfPlaces < 10:
        formatPattern = "{:0." + str(numberOfPlaces) + "f}" 
        quadraticTermString = formatPattern.format(quadraticTerm)
        if float(quadraticTermString) == quadraticTerm:
            break
        numberOfPlaces += 1
    return f"Favor income rate per second: {rate} + {quadraticTermString}x(current idle LOS bonus)²\\nFlat LOS boosts (eg Pelt of Argus) do NOT affect this: this is entirely dependent on the amount of idle bonus."

        
def generateUnitDescriptions():
    proto = globals.dataCollection["proto.xml"]
    techtree = globals.dataCollection["techtree.xml"]

    for techElement in techtree:
        if techElement.find("[flag='Volatile']") is not None:
            create = techElement.find("effects/effect[@type='CreateUnit']")
            if create is not None:
                globals.respawnTechs[create.attrib['unit']] = techElement

    stringLiteralHelper = lambda s: f"\"{s}\""
    
    centaurSpecialDoTNeedsDamageBonuses = action.actionDamageBonus(action.findActionByName('Centaur', "ChargedRangedAttack")) != action.actionDamageBonus(action.findActionByName('CentaurAreaDamage', 'ProgressiveDamageLight'))

    TitanHandler = UnitDescription(ignoreActions=["TitanAttack"])

    WallHandler = UnitDescription(overrideDescription=f"Wall connectors have only {float(protoFromName('WallConnector').find('maxhitpoints').text)/float(protoFromName('WallMedium').find('maxhitpoints').text):0.3g}x the hitpoints of other wall segments.")

    SunRayRevealerText = f"Grants {icon.iconLos()} {float(protoFromName('SunRayRevealer').find('los').text):0.3g} around units hit by attacks for {float(protoFromName('SunRayRevealer').find('lifespan').text):0.3g} seconds."

    HideFlyingAttack = UnitDescription(ignoreActions=["RangedAttackFlying", "FlyingUnitAttack"])

    GullinburstiAges = ("Archaic", "Classical", "Heroic", "Mythic")
    gullinburstiHistory = "\\n".join([f"<tth>{age}:\\n" + UnitDescription(preActionInfoText={"BirthAttack":"Shockwave when spawned:"}).generate(protoFromName(f"Gullinbursti{age}")) for age in GullinburstiAges])
    GullinburstiHandler = UnitDescription(hideStats=True, ignoreActions=["HandAttack", "Gore", "DistanceLimiting", "BirthAttack"], historyText=gullinburstiHistory, hideNonActionObservations=True, additionalText="See history for age progression.")

    unitDescriptionOverrides = {
        # People new to the game seem to have a not great grasp of what units do what, so maybe I can help a little.
        # Greek
        "Hoplite":UnitDescription(preActionInfoText={"HandAttack":"Generalist infantry, especially good against cavalry."}),
        "Hypaspist":UnitDescription(preActionInfoText={"HandAttack":"Specialist infantry only good against other infantry."}),
        "Toxotes":UnitDescription(preActionInfoText={"RangedAttack":"Generalist archer, especially good against infantry."}),
        "Peltast":UnitDescription(preActionInfoText={"RangedAttack":"Specialist ranged unit only good against other ranged soldiers."}),
        "Hippeus":UnitDescription(preActionInfoText={"HandAttack":"Generalist cavalry, especially good against ranged soldiers."}),
        "Prodromos":UnitDescription(preActionInfoText={"HandAttack":"Specialist cavalry only good against other cavalry."}),
        "Militia":UnitDescription(preActionInfoText={"HandAttack":"Generalist infantry spawned from destroyed buildings of Poseidon. Good against cavalry."}),
        "Myrmidon":UnitDescription(preActionInfoText={"HandAttack":f"Generalist infantry that inflicts armor ignoring {icon.damageTypeIcon('divine')} Divine damage with attacks."}),
        "Hetairos":UnitDescription(preActionInfoText={"HandAttack":f"Generalist cavalry that inflict area damage."}),
        "Gastraphetoros":UnitDescription(preActionInfoText={"RangedAttack":f"Generalist archer with considerable bonus against buildings."}),
        "Pegasus":UnitDescription(additionalText=f"Pegasus from the Bridle of Pegasus respawn in {float(techtree.find('tech[@name=' + stringLiteralHelper('BridleOfPegasusRespawn') +']/delay').text):0.3g}s. Pegasus from Winged Messenger respawn in {float(techtree.find('tech[@name=' + stringLiteralHelper('WingedMessengerRespawn') +']/delay').text):0.3g}s."),
        "Hydra":UnitDescription(passiveAbilityLink={"veterancy":"AbilityHydra"}, nonActionObservationArgs={"veterancy":["head"]}),
        "Scylla":UnitDescription(passiveAbilityLink={"veterancy":"AbilityScylla"}, nonActionObservationArgs={"veterancy":["head"]}),
        "HadesShade":UnitDescription(additionalText=f"Has a {float(globals.dataCollection['major_gods.xml'].find('./civ[name=' + stringLiteralHelper('Hades') + ']/shades/chance').text)*100.0:0.3g}% to appear at the Temple from the deaths of human soldiers."),
        "PlentyVault":UnitDescription(overrideDescription="<tth>Regular Plenty Vault:", additionalText="<tth>King of the Hill:\\n" + icon.BULLET_POINT + " " + UnitDescription(overrideClasses=True, additionalClasses=[], includeVanillaDescription=False, hideStats=True).generate(protoFromName("PlentyVaultKOTH"))),
        "Centaur":UnitDescription(postActionInfoText={"ChargedRangedAttack":action.actionDamageOverTimeArea('CentaurAreaDamage', 'ProgressiveDamageLight', altDamageText=f"{action.actionDamageOverTimeDamageFromAction(action.findActionByName('CentaurAreaDamage', 'ProgressiveDamageLight'), centaurSpecialDoTNeedsDamageBonuses)} for the first {float(action.actionTactics('CentaurAreaDamage', 'ProgressiveDamageLight').find('modifyduration').text)/1000:0.3g} seconds, followed by {action.actionDamageOverTimeDamageFromAction(action.findActionByName('CentaurAreaDamage', 'ProgressiveDamageHigh'), centaurSpecialDoTNeedsDamageBonuses)} for the next {float(action.actionTactics('CentaurAreaDamage', 'ProgressiveDamageHigh').find('modifyduration').text)/1000:0.3g} seconds")}),
        "Chimera":UnitDescription(postActionInfoText={"ChargedRangedAttack":action.actionDamageOverTimeArea('ChimeraFireArea', parentAction=action.findActionByName('Chimera', "ChargedRangedAttack"))}),
        "Carcinos":UnitDescription(linkActionsToAbilities={"SelfDestructAttack":"AbilityCarcinos"}),
        "Colossus":UnitDescription(ignoreActions=["BuildingAttack"]),
        "Odysseus":HideFlyingAttack,
        "Chiron":HideFlyingAttack,
        "Hippolyta":HideFlyingAttack,
        # Egyptian
        "Spearman":UnitDescription(preActionInfoText={"HandAttack":"Fast semi-specialised infantry, mostly only good against cavalry."}),
        "Axeman":UnitDescription(preActionInfoText={"HandAttack":"Specialist infantry only good against other infantry."}),
        "Slinger":UnitDescription(preActionInfoText={"RangedAttack":"Specialist ranged unit only good against other ranged units."}),
        "ChariotArcher":UnitDescription(preActionInfoText={"RangedAttack":"Generalist ranged unit, especially good against infantry."}),
        "CamelRider":UnitDescription(preActionInfoText={"HandAttack":"Generalist cavalry unit, especially good against other cavalry."}),
        "WarElephant":UnitDescription(preActionInfoText={"HandAttack":"Very slow cavalry, good against whatever units or buildings it can reach."}),
        "Priest":UnitDescription(overrideDescription="Hero with a ranged attack that is good against myth units, but weak against other targets."),
        "Pharaoh":UnitDescription(preActionInfoText={"RangedAttack":"Hero with a ranged attack that is especially good against myth units."}),
        "PharaohNewKingdom":UnitDescription(preActionInfoText={"RangedAttack":"Hero with a ranged attack that is especially good against myth units."}),
        "Petsuchos":UnitDescription(passiveAbilityLink={"other":"AbilityPetsuchos"}, nonActionObservationArgs={"other":[SunRayRevealerText]}),
        "Phoenix":UnitDescription(ignoreActions=["FlyingUnitAttack"], overrideNonActionObservations={"spawns":f"Leaves an egg on death. After {float(action.actionTactics('PhoenixEgg', 'PhoenixRebirth').find('maintaintrainpoints').text):0.3g} seconds, it hatches back into a Phoenix."}, passiveAbilityLink={"spawns":"AbilityPhoenix"}),
        "PhoenixEgg":UnitDescription(linkActionsToAbilities={"PhoenixRebirth":"AbilityPhoenixEgg"}),
        "Scarab":UnitDescription(linkActionsToAbilities={"SelfDestructAttack":"AbilityScarab"}),
        # Norse
        "Berserk":UnitDescription(preActionInfoText={"HandAttack":"Generalist infantry. Can build."}, additionalText="Immune to Bolt while in the Archaic age."),
        "ThrowingAxeman":UnitDescription(preActionInfoText={"RangedAttack":"Specialist infantry only good against other infantry. Can build."}),
        "RaidingCavalry":UnitDescription(preActionInfoText={"HandAttack":"Generalist cavalry, especially good against archers."}),
        "Hirdman":UnitDescription(preActionInfoText={"HandAttack":"Specialist infantry only good against cavalry. Can build."}),
        "Huskarl":UnitDescription(preActionInfoText={"HandAttack":"Specialist infantry only good against ranged soldiers. Can build."}),
        "Jarl":UnitDescription(preActionInfoText={"HandAttack":"A slower, more expensive cavalry unit than the Raiding Cavalry that has considerably more hitpoints."}),
        "Hersir":UnitDescription(preActionInfoText={"HandAttack":"Hero infantry. Primarily good against myth units, but reasonably effective against other targets. Can build."}),
        "Godi":UnitDescription(preActionInfoText={"RangedAttack":"Hero ranged soldier. Primarily good against myth units, but moderately effective against other targets. Can build."}),
        "Nidhogg":UnitDescription(ignoreActions=["FlyingUnitAttack"], postActionInfoText={"RangedAttack":action.actionDamageOverTimeArea('VFXNidhoggScorchArea', parentAction=action.findActionByName("Nidhogg", "RangedAttack"))}),
        "Fafnir":UnitDescription(passiveAbilityLink={"killreward":"AbilityFafnirAndvarisCurse"}, linkActionsToAbilities={"BillowingSmog":"AbilityFafnirBillowingSmog"}),
        "RockGiant":UnitDescription(linkActionsToAbilities={"BuildingAttack":"AbilityRockGiantCavernousHunger"}),
        "HealingSpring":UnitDescription(linkActionsToAbilities=({"AreaHeal":"PassiveHealingSpring"})),
        "MountainGiant":UnitDescription(chargeActionNames={"DwarvenPunt":"Punt Dwarf"}),
        "GullinburstiArchaic":GullinburstiHandler,
        "GullinburstiClassical":GullinburstiHandler,
        "GullinburstiHeroic":GullinburstiHandler,
        "GullinburstiMythic":GullinburstiHandler,
        # Atlantean
        "Oracle":UnitDescription(overrideDescription="Scout, line of sight grows when standing still. Cannot attack.", postActionInfoText={"AutoGatherFavor":oracleAutoGatherFavorHelper("Oracle")}, historyText=oracleHistoryText("Oracle")),
        "OracleHero":UnitDescription(preActionInfoText={"HandAttack":"Hero scout, line of sight grows when standing still. Generates favor faster than normal Oracles. Good against myth units."}, postActionInfoText={"AutoGatherFavor":oracleAutoGatherFavorHelper("OracleHero")}, historyText=oracleHistoryText("OracleHero")),
        "Katapeltes":UnitDescription(preActionInfoText={"HandAttack":"Specialist infantry only good against cavalry."}),
        "KatapeltesHero":UnitDescription(preActionInfoText={"HandAttack":"Specialist infantry hero only good against cavalry and myth units."}),
        "Turma":UnitDescription(preActionInfoText={"RangedAttack":"Specialist mounted ranged soldier only good against other ranged soldiers, or making hit-and-run attacks."}),
        "TurmaHero":UnitDescription(preActionInfoText={"RangedAttack":"Specialist mounted ranged soldier hero only good against myth units, other ranged soldiers, and making hit-and-run attacks."}),
        "Murmillo":UnitDescription(preActionInfoText={"HandAttack":"Generalist infantry."}),
        "MurmilloHero":UnitDescription(preActionInfoText={"HandAttack":"Generalist infantry hero. Good against myth units."}),
        "Cheiroballista":UnitDescription(preActionInfoText={"RangedAttack":"Specialist ranged soldier, very effective against infantry and ships."}),
        "CheiroballistaHero":UnitDescription(preActionInfoText={"RangedAttack":"Specialist ranged soldier hero, very effective against myth units, infantry, and ships."}),
        "Contarius":UnitDescription(preActionInfoText={"HandAttack":"Generalist cavalry, especially good against ranged soldiers."}),
        "ContariusHero":UnitDescription(preActionInfoText={"HandAttack":"Generalist cavalry hero, especially good against ranged soldiers and myth units."}),
        "Arcus":UnitDescription(preActionInfoText={"RangedAttack":"Generalist archer, especially good against infantry."}),
        "ArcusHero":UnitDescription(preActionInfoText={"RangedAttack":"Generalist archer hero, especially good against myth units and infantry."}),
        "Destroyer":UnitDescription(preActionInfoText={"HandAttack":"Specialist infantry, good against buildings and for being extremely resistant to pierce attacks."}),
        "DestroyerHero":UnitDescription(preActionInfoText={"HandAttack":"Specialist infantry hero, good against myth units and buildings, and for being extremely resistant to pierce attacks."}),
        "Fanatic":UnitDescription(preActionInfoText={"HandAttack":"Semi-specialist infantry, good against cavalry and other infantry."}),
        "FanaticHero":UnitDescription(preActionInfoText={"HandAttack":"Semi-specialist infantry hero, good against myth units, cavalry and other infantry."}),
        "Argus":UnitDescription(postActionInfoText={"ChargedRangedAttack":action.actionDamageOverTimeArea('ArgusAcidBlobDamage', parentAction=action.findActionByName("Argus", "ChargedRangedAttack"), lateText=f"Explodes at the end of the duration, dealing {action.selfDestructActionDamage('ArgusAcidBlobDamage')}.")}),
        "Lampades":UnitDescription(linkActionsToAbilities={"SelfDestructAttack":"AbilityLampadesCausticity"}),
        "SiegeBireme":UnitDescription(linkActionsToAbilities={"FlameAttack":"PassiveSolarFlame"}),
        "Promethean":UnitDescription(passiveAbilityLink={"spawns":"AbilityPromethean"}),
        "Behemoth":UnitDescription(passiveAbilityLink={"directionalarmor":"AbilityBehemoth"}),
        # Common/Similar
        "SentryTower":UnitDescription(showActionsIfDisabled=["RangedAttack"]),
        "VillageCenter":UnitDescription(additionalText=f"Produces units {100.0-100*float(protoFromName('VillageCenter').find('trainingrate').text):0.3g}% slower than a Town Center. Research speed is unaffected."),
        "TitanCerberus":TitanHandler,
        "TitanYmir":TitanHandler,
        "TitanAtlantean":TitanHandler,
        "TitanBird":TitanHandler,
        "WallLong":WallHandler,
        "WallMedium":WallHandler,
        "WallShort":WallHandler,
        "Fortress":HideFlyingAttack,
        "MigdolStronghold":HideFlyingAttack,
        "HillFort":HideFlyingAttack,
        "AsgardianHillFort":HideFlyingAttack,
        "Palace":HideFlyingAttack,
        "Wonder":UnitDescription(overrideDescription=tech.processTech(techtree.find("tech[@name='WonderAgeGeneral']"))),
        # Campaign
            # Nothing atm
        
    }

    archaicAgeWeakenedUnits: Dict[str, ET.Element] = dict([(effect.find("target").text, effect) for effect in globals.dataCollection['techtree.xml'].find("tech[@name='ArchaicAgeWeakenUnits']/effects")])
    for unitName, effectElement in archaicAgeWeakenedUnits.items():
        override = unitDescriptionOverrides.get(unitName, UnitDescription())
        actionName = effectElement.attrib["action"]
        existingText = override.postActionInfoText.get(actionName, "")
        existingText += f" Deals {1.0-float(effectElement.attrib['amount']):0.0%} less damage in the Archaic Age."
        override.postActionInfoText[actionName] = existingText
        unitDescriptionOverrides[unitName] = override

    # Non action tied passives that we still want to write text for!
    nonActionPassiveAbilities = {}

    # Greek
    nonActionPassiveAbilities['PassiveSolarFlare'] = SunRayRevealerText

    # Egyptian

    # Norse
    fenrisWolf = protoFromName("FenrisWolfBrood")
    wolfboosts = []
    for actionNode in fenrisWolf.findall("protoaction"):
        tactics = action.actionTactics(fenrisWolf, actionNode)
        if tactics.find("type").text == "LikeBonus":
            wolfboosts.append(actionNode)
    nonActionPassiveAbilities['AbilityFenrisWolfBrood'] = "\\n".join([action.describeAction(fenrisWolf, x) for x in wolfboosts])

    # Atlantean
    nonActionPassiveAbilities['AbilityStymphalianBird'] = f"Attacks deal an additional {action.actionDamageOverTime(action.findActionByName('StymphalianBird', 'RangedAttack'))}."
    nonActionPassiveAbilities['PassivePetrifiedFrame'] = action.handleIdleStatBonusAction(protoFromName('Cheiroballista'), action.findActionByName('Cheiroballista', 'PetrificationBonus'), None, "")
    

    # Major god related

    nonActionPassiveAbilities['PassiveDivineShield'] = tech.processEffect(techtree.find("tech[@name='ArchaicAgeIsis']"), techtree.find("tech[@name='ArchaicAgeIsis']/effects/effect[@subtype='GodPowerBlockRadius']")).toString(skipAffectedObjects=True)

    monumentEmpowerAura = action.actionTactics('MonumentToVillagers', None).find("action[name='MonumentEmpowerAura']")
    nonActionPassiveAbilities['PassiveMandjet'] = action.handleAutoRangedModifyAction(protoFromName('MonumentToVillagers'), monumentEmpowerAura, monumentEmpowerAura, "")

    monumentCheapenAura = action.actionTactics('MonumentToVillagers', None).find("action[name='DevoteesMedium']")
    nonActionPassiveAbilities['PassiveDevotees'] = action.handleAutoRangedModifyAction(protoFromName('MonumentToVillagers'), monumentCheapenAura, monumentCheapenAura, "")

    temporalScaffoldingAction = action.actionTactics('Manor', None).find("action[name='TemporalScaffoldingSmall']")
    nonActionPassiveAbilities['PassiveTemporalScaffolding'] = action.handleAutoRangedModifyAction(protoFromName('Manor'), temporalScaffoldingAction, temporalScaffoldingAction, "")

    terrainCreep = globals.dataCollection['major_gods.xml'].find("civ[name='Gaia']/terraincreeps/terraincreep")
    healEffect = globals.dataCollection['terrain_unit_effects.xml'].find("terrainuniteffect[@name='GaiaCreepHealEffect']/effect")
    nonActionPassiveAbilities['PassiveLush'] = f"Grows up to a {float(terrainCreep.attrib['maxradius']):0.3g}m circle of lush at {float(terrainCreep.attrib['growthrate']):0.3g}m per second. Friendly objects on lush heal {float(healEffect.attrib['amount']):0.3g} per second."

    # Tech related

    nonActionPassiveAbilities['PassiveAnastrophe'] = action.describeAction(protoFromName("Pentekonter"), action.findActionByName("Pentekonter", "ChargedHandAttack"), chargeType=action.ActionChargeType.REGULAR, tech=techtree.find("tech[@name='Anastrophe']"))

    nonActionPassiveAbilities['PassiveFuneralBarge'] = tech.processTech(techtree.find("tech[@name='FuneralBarge']"), skipAffectedObjects=True)
    nonActionPassiveAbilities['PassiveDeathlyDonative'] = tech.processTech(techtree.find("tech[@name='FuneralRites']"), skipAffectedObjects=True)

    nonActionPassiveAbilities['PassiveHamask'] = tech.processTech(techtree.find("tech[@name='Hamask']"), skipAffectedObjects=True)
    nonActionPassiveAbilities['PassiveValhallasChosen'] = tech.processEffect(techtree.find("tech[@name='CallOfValhalla']"), techtree.find("tech[@name='CallOfValhalla']/effects/effect[@subtype='ResourceReturn']")).toString(skipAffectedObjects=True)
    nonActionPassiveAbilities['PassiveNaturesEyes'] = tech.processTech(techtree.find("tech[@name='EyesInTheForest']"), skipAffectedObjects=True)
    nonActionPassiveAbilities['PassiveViking'] = tech.processTech(techtree.find("tech[@name='Vikings']"), skipAffectedObjects=True)
    nonActionPassiveAbilities['PassiveSkadisBreath'] = tech.processTech(techtree.find("tech[@name='ArcticWinds']"), skipAffectedObjects=True)
    nonActionPassiveAbilities['PassiveSkaldicInspiration'] = tech.processTech(techtree.find("tech[@name='LongSerpent']"), skipAffectedObjects=True)

    nonActionPassiveAbilities['PassiveSerratedBlades'] = tech.processEffect(techtree.find("tech[@name='BiteOfTheShark']"), techtree.find("tech[@name='BiteOfTheShark']/effects/effect[@effecttype='DamageOverTime']")).toString(skipAffectedObjects=True)
    nonActionPassiveAbilities['PassiveBattleFrenzy'] = tech.processTech(techtree.find("tech[@name='DevoteesOfAtlas']"), skipAffectedObjects=True, lineJoin="\\n")
    

    

    for abilityName, tooltip in nonActionPassiveAbilities.items():
        abilityInfo = globals.dataCollection["abilities_combined"].find(f"power[@name='{abilityName}']")
        if abilityInfo is None:
            raise ValueError(f"Couldn't find civ.abilities entry for {abilityName}")
        displayNameStrId = findAndFetchText(abilityInfo, "rolloverid", None)
        globals.stringMap[displayNameStrId] = tooltip

    stringIdsByOverwriters: Dict[str, Dict[ET.Element, str]] = {}
    
    for unit in proto:
        if unit.attrib["name"] in IGNORE_UNITS:
            continue
        strid = unit.find("rollovertextid")
        if strid is None:
            continue
        strid = strid.text
        value = unitDescriptionOverrides.get(unit.attrib["name"], UnitDescription()).generate(unit)
        if value is not None:
            if strid not in stringIdsByOverwriters:
                stringIdsByOverwriters[strid] = {}
            if value not in stringIdsByOverwriters[strid].values():
                stringIdsByOverwriters[strid][unit] = value

    common.handleSharedStringIDConflicts(stringIdsByOverwriters)
    common.handleSharedStringIDConflicts(globals.unitAbilityDescriptions)

    # Add the tech source of abilities where applicable
    techsByEnabler = {}
    techInternalToDisplayName = {}
    techsWithMultipleEnablers = set()
    for techElement in techtree:
        effects = techElement.find("effects")
        displayName = common.getObjectDisplayName(techElement)
        if displayName.startswith("ArchaicAge"):
            displayName = displayName[10:]
        techInternalToDisplayName[techElement.attrib["name"]] = displayName
        if effects is not None:
            for effect in effects:
                if effect.attrib.get("type", "") == "TechStatus" and effect.attrib.get("status", "") == "obtainable":
                    enabledTech = effect.text
                    if enabledTech in techsByEnabler:
                        techsWithMultipleEnablers.add(enabledTech)
                    else:
                        techsByEnabler[enabledTech] = displayName
    # We do not want to pin a tech to an ability that something has without needing a tech
    abilitiesWithNoTechNode = set()
    for unitNode in globals.dataCollection["abilities"]["abilities.xml"]:
        for abilityNode in unitNode:
            techNode = abilityNode.find("tech")
            if techNode is None:
                abilityInfo = globals.dataCollection["abilities_combined"].find(f"power[@name='{abilityNode.text}']")
                if abilityInfo is not None and abilityInfo.attrib.get("type", "") == "GeneralEffect":
                    abilitiesWithNoTechNode.add(abilityNode.text)

    # For different sources of the same ability (eg lifesteal or "venomous" from Serpent Spear and Shaft of Plague) we need to not list techs as well
    abilityNameStringIdsWithMultipleReplacers = set()
    for unitNode in globals.dataCollection["abilities"]["abilities.xml"]:
        for abilityNode in unitNode:
            techNode = abilityNode.find("tech")
            abilityInfo = globals.dataCollection["abilities_combined"].find(f"power[@name='{abilityNode.text}']")
            if abilityInfo.attrib.get("type", "") == "GeneralEffect":
                if techNode is not None and abilityNode.text not in abilitiesWithNoTechNode:
                    techInternalName = techNode.text
                    if techInternalName in techsWithMultipleEnablers:
                        print(f"Ability {abilityNode.text} for {unitNode.tag} depends on {techInternalName} which has multiple enablers")
                        techInternalName = ""
                    enablerName = techsByEnabler.get(techInternalName, None)
                    techDisplayName = techInternalToDisplayName[techInternalName]
                    displayNameStrId = findAndFetchText(abilityInfo, "displaynameid", None)
                    if displayNameStrId is None:
                        print(f"Passive ability {abilityNode.text} has no display name string id?")
                    else:
                        brackets = UNIT_ABILITY_SOURCE_COLOUR(f"[{techDisplayName}, {enablerName}]")
                        if enablerName is None:
                            brackets = UNIT_ABILITY_SOURCE_COLOUR(f"[{techDisplayName}]")
                        replacement = globals.dataCollection["string_table.txt"][displayNameStrId].replace(" (Passive)", "") + f" {brackets}"
                        if displayNameStrId in globals.stringMap and globals.stringMap[displayNameStrId] != replacement:
                            abilityNameStringIdsWithMultipleReplacers.add(displayNameStrId)
                            #print(displayNameStrId, stringMap[displayNameStrId], replacement)
                        else:
                            globals.stringMap[displayNameStrId] = replacement
    for badStringId in abilityNameStringIdsWithMultipleReplacers:
        del globals.stringMap[badStringId]
        print(f"Ability name {badStringId} had multiple different attempted replacements, removing")
    for badStringId in BANNED_STRINGS:
        if badStringId in globals.stringMap:
            print(f"Remove entry for blacklisted string {badStringId} ({len(globals.stringMap[badStringId])} chars)")
            del globals.stringMap[badStringId]