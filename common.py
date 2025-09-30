import globals
from xml.etree import ElementTree as ET
from typing import Union, List, Dict, Callable, TypeVar, Iterable
import icon
import os
import re
import itertools
import dataclasses
import warnings
import functools

def commaSeparatedList(words: List[str], joiner="and"):
    if isinstance(words, str):
        raise ValueError(f"Blatant mistake: called on flat string: {words}")
    if len(words) == 0:
        return ""
    if len(words) == 1:
        return words[0]
    separated = ", ".join(words[:-1])
    separated += f" {joiner} " + words[-1]
    return separated


def protoFromName(protoName: Union[ET.Element, str]) -> Union[ET.Element, None]:
    if isinstance(protoName, ET.Element):
        return protoName
    return globals.dataCollection["proto.xml"].find(f"./*[@name='{protoName}']")

def techFromName(techName: Union[ET.Element, str]) -> Union[ET.Element, None]:
    if isinstance(techName, ET.Element):
        return techName
    return globals.dataCollection["techtree.xml"].find(f"./*[@name='{techName}']")

# Do not write charge ability descriptions for these units
# Their abilities share string ids with more common units but have different parameters
# And including both might be excessive. Will have to see how it comes out
PROTOS_TO_IGNORE_FOR_ABILITY_TOOLTIPS = (
    "Kamos",
    "FireKing",
    "Theris",
    "KingFolstag",
    "Gargarensis",
)

_OVERRIDE_DISPLAY_NAMES = {
    "MinionReincarnated":"Minion (Mummy)",
    "Minion":"Minion (Ancestors)",
    "HeroOfRagnarok":"Hero of Ragnarok (Gatherer)",
    "HeroOfRagnarokDwarf":"Hero of Ragnarok (Dwarf)",
    "ProjectileSatyrSpearSpecialAttack": "Satyr Piercing Throw Spear",
    "BerserkDamageBoost":"Invisible Berserk Damage Booster",
    "Settlement":"Settlement/Unfinished Town Center",
    "EyesOnForestRevealer":"Revealer",
    "SunRayRevealer":"Revealer",
    "SunRayGroundRevealer":"Revealer",
    "ChimeraFireArea":"Chimera Special Fire Area",
    "SonOfOsiris":"Son of Osiris", # No (Hero) suffix
    "Hersir":"Hersir",
    "Godi":"Godi",
    "Priest":"Priest",
    "Pharaoh":"Pharaoh",
    "PharaohNewKingdom":"Pharaoh (New Kingdom)",
    "MilitaryCampTrainingYard":"Military Camp with Training Yard",
    "MachineWorkshopTrainingYard":"Machine Workshop with Training Yard",
    "MilitaryCampTower":"Military Camp with Tower",
    "MachineWorkshopTower":"Machine Workshop with Tower",
    "QiongQiAir":"Qiongi (Flying)",
    "TitanKronos":"Kronos (Campaign)",
    "AOTGTitanKronos":"Kronos (Arena of the Gods)",
    "NezhaChild":"Nezha (Classical Age)",
    "NezhaYouth":"Nezha (Heroic Age)",
    "Nezha":"Nezha (Mythic Age)",
    "YanFeifeng":"Yan Feifeng (unmounted)",
    "YanFeifengRider":"Yan Feifeng (mounted)",

    # Parched Land (exploding fishing ship tech) is normally "A Thousand Li of Parched Land" which isn't very clear
    "AbilityFishingShipChinese":"Demolition",

    "AbilityTaotieDevour":"Eat", # Normally Fuel Consumption, makes the tooltip harder to understand
    "AbilityTaotieExpel":"Spit", # Normally Fuel Expulsion

    # These are for Amaterasu's Shrine resource inventory increase, need to distinguish the different mine sizes
    "MineGoldLarge":"Gold Mine (6000)",
    "MineGoldMedium":"Gold Mine (3000)",
    "MineGoldSmall":"Gold Mine (1500)",
}

_UNIT_CLASS_LABELS = {
    "Hero": "Hero",
    "AbstractInfantry":"Infantry",
    "AbstractCavalry":"Cavalry",
    "AbstractArcher":"Ranged Soldier",
    "AbstractSiegeWeapon":"Siege",
    "AbstractVillager":"Villager",
    "AbstractArcherShip":"Archer Ship",
    "AbstractCloseCombatShip":"Close Combat Ship",
    "AbstractSiegeShip":"Siege Ship",
    "CavalryLineUpgraded": "Cavalry Line Upgraded",
    "InfantryLineUpgraded": "Infantry Line Upgraded",
    "ArcherLineUpgraded": "Ranged Line Upgraded",
    "Building":"Building",
    "MythUnit":"Myth Unit",
    "HumanSoldier":"Human Soldier",
    "Huntable":"Huntable",
    "Ship": "Ship",
    "FoodDropsite": "Food Dropsite",
    "WoodDropsite": "Wood Dropsite",
    "GoldDropsite": "Gold Dropsite",
    "HeroShadowUpgraded":"Hero that upgrades with Age",
    "LogicalTypeBuildingEmpoweredForLOS": "Empowerment Boosts LOS",
    "LogicalTypeArchaicMythUnit":"Archaic Myth Unit",
    "LogicalTypeClassicalMythUnit":"Classical Myth Unit",
    "LogicalTypeHeroicMythUnit":"Heroic Myth Unit",
    "LogicalTypeFreezableMythUnit":"Freezable",
    "Unit":"Unit",
    "AbstractFishingShip":"Fishing Ship",
    "AbstractPharaoh":"Pharaoh",
    "LogicalTypeAffectedByCeaseFireBuildingSlow":"Construction slowed by Ceasefire",
    "Tree": "Tree",
    "AbstractTransportShip":"Transport Ship",
    "AbstractWarship":"Warship",
    "AbstractWarshipHero":"Warship Hero",
    "AbstractTitan":"Titan",
    "MilitaryUnit":"Military Unit",
    "LogicalTypeBuildingsNotWalls":"Building (except Walls)",
    "LogicalTypeMythUnitNotTitan":f"Myth Unit LOGICAL_TYPE_MYTH_UNIT_NOT_TITAN_EXCEPTION",
    "LogicalTypeShipNotHero":"Ship (except Heroes)",
    "LogicalTypeVillagerNotHero":"Villager (except Heroes)",
    "Favor":"Favor",
    "AbstractMonument":"Monument",
    "WoodResource":"Wood",
    "GoldResource":"Gold",
    "FishResource":"Fish",
    "Food":"Food",
    "Wood":"Wood",
    "Gold":"Gold",
    "AbstractFarm":"Farm",
    "Herdable":"Herdable",
    "NonConvertableHerdable":"Chicken-like",
    "LogicalTypeHealed":"Healable Unit",
    "AbstractHealer":"Healer",
    "AbstractTownCenter":"Town Center",
    "AbstractFortress":"Fortress-like Building",
    "LogicalTypeBuildingNotWonderOrTitan":"Building (except Wonder and Titan Gate)",
    "LogicalTypeRangedMythUnit":"Ranged Myth Unit",
    "LogicalTypeBuildingsThatShoot":"Building that Shoots",
    "AbstractEmpowerer":"Empowerer",
    "LogicalTypeAffectedByRestoration":"Affected by Restoration",
    "LogicalTypeValidBoltTarget":"Affected by Bolt",
    "LogicalTypeMilitaryProductionBuilding":"Military Production Building",
    "AbstractTower":"Tower",
    "LogicalTypeLandMilitary":"Land Military Unit",
    "NavalUnit":"Naval Units",
    "AbstractFlyingUnit":"Flying Unit",
    "LogicalTypeEarthquakeAttack":"object vulnerable to Earthquake",
    "LogicalTypeValidTornadoAttack":"object vulnerable to Tornado",
    "LogicalTypeValidShiftingSandsTarget":"object affected by Shifting Sands",
    "LogicalTypeValidMeteorTarget":"object targeted by Meteor",
    "LogicalTypeHandUnitsAttack":"object attackable in Melee",
    "LogicalTypeValidTraitorTarget":"object affected by Traitor",
    "LogicalTypeValidFrostTarget":"freezable Unit",
    "EconomicUnit":"Economic Unit",
    "WildCrops":"Berry Bush",
    "Herdable":"Herdable",
    "LogicalTypeValidShockwaveTarget":"object affected by Shockwave",
    "Resource":"Resource",
    "MajorHero":"Heroes with Build Limits",
    "MinorHero":"Heroes without Build Limits",
    "LegendHero":"Legends",
    "All":"All objects",
    "AbstractDwarf":"Dwarves",
    "AbstractNezha":"Nezha",
    "AbstractMilitaryCamp":"Military Camp",
    "LogicalTypeDivineImmunity":"targets with Divine Immunity",
    "LogicalTypeBuildingThatConvertsConvertibles":"Building that protect convertible structures",
    "AbstractAsura":"Asura and Fireballs",
    "AbstractSamurai":"Samurai",
    "LogicalTypeHealableHero":"Healable Hero",
    "LogicalTypeTrainableMythUnit":"Trainable Myth Unit",

    # Partial Lies
    "EconomicUpgraded":"Villager",
    "TradeUnit":"Caravan",
    "AbstractWall":"Wall",
    "AbstractSettlement":"Town Center",
    "LogicalTypeSunRayProjectile":"Projectile",
    "AbstractTemple":"Temple",
    "LogicalTypeAffectedBySunRay":"Greek Ranged Human Soldiers, Heroes, and Myth Units",
}



_UNIT_CLASS_LABELS_PLURAL = {
    "MilitaryUnit":"Military Units",
    "EconomicUnit":"Economic Units",
    "Unit":"Units",
    "Building":"Buildings",
    "AbstractSiegeWeapon":"Siege Weapons",
    "Huntable":"Huntables",
    "AbstractFlyingUnit":"Flying Units",
    "HumanSoldier":"Human Soldiers",
    "LogicalTypeMythUnitNotTitan":"Myth Units LOGICAL_TYPE_MYTH_UNIT_NOT_TITAN_EXCEPTION",
    "LogicalTypeVillagerNotHero":"Villagers (except Heroes)",
    "TradeUnit":"Caravans",
    "LogicalTypeMythUnitNotFlying":"non-flying Myth Units",
    "AnimalOfSet":"Animals of Set",
    "Hero":"Heroes",
    "NavalUnit":"Naval Units",
    "LogicalTypeNavalMilitary":"Naval Military Units",
    "LogicalTypeShipNotHero":"Non-hero Ships",
    "MythUnit":"Myth Units",
    "AbstractWall":"Walls",
    "AbstractTitan":"Titans",
    "AbstractCavalry":"Cavalry",
    "Ship":"Ships",
    "Resource":"Resources",
    "AbstractFishingShip":"Fishing Ships",
    "AbstractTransportShip":"Transport Ships",
    "AbstractWarship":"War Ships",
    "AbstractSettlement":"Settlements",
    "LogicalTypeMilitaryProductionBuilding":"Military Production Buildings",
    "AbstractTemple":"Temples",
    "Herdable":"Herdables",
    "AbstractFarm":"Farms",
    "AbstractFortress":"Fortress-like Buildings",
    "LogicalTypeValidFrostTarget":"Freezable Units",
    "LogicalTypeEarthquakeAttack":"objects vulnerable to Earthquake",
    "LogicalTypeValidTornadoAttack":"objects vulnerable to Tornado",
    "LogicalTypeValidShiftingSandsTarget":"objects affected by Shifting Sands",
    "LogicalTypeValidMeteorTarget":"objects targeted by Meteor",
    "LogicalTypeHandUnitsAttack":"objects attackable in Melee",
    "LogicalTypeValidTraitorTarget":"objects affected by Traitor",
    "LogicalTypeValidShockwaveTarget":"objects affected by Shockwave",
    "LogicalTypeValidSpyTarget":"valid Spy targets",
    "LogicalTypeAffectedByValor":"valid Valor targets",
    "LogicalTypeValidSentinelTarget":"valid Sentinel targets",
    "LogicalTypeTartarianGateValidOverlapPlacement":"Buildings overlappable by Tartarian Gate",
    "LogicalTypeLandMilitary":"Land Military Units",
    "AbstractTower":"Towers",
    "LogicalTypeAffectedByRestoration":"Affected by Restoration",
    "LogicalTypeValidBoltTarget":"Affected by Bolt",
    "NonConvertableHerdable":"Chicken-like",
    "Tree":"Trees",
    "Favor":"Favor",
    "WoodResource":"Wood",
    "Wood":"Wood",
    "GoldResource":"Gold",
    "Gold":"Gold",
    "FishResource":"Fish",
    "Food":"Food",
    "AbstractInfantry":"Infantry",
    "AbstractArcher":"Ranged Soldiers",
    "LogicalTypeBuildingsThatShoot":"Buildings that Shoot",
    "AbstractPharaoh":"Pharaohs",
    "LogicalTypeRangedUnitsAttack":"valid Ranged attack targets",
    "LogicalTypeBuildingsNotWalls":"Buildings (except Walls)",
    "AbstractVillager":"Villagers",
    "all":"all objects",
    "All":"all objects",
    "LogicalTypeDivineImmunity":"targets with Divine Immunity",
    "LogicalTypeBuildingThatConvertsConvertibles":"Buildings that protect convertible structures",
    "LogicalTypeHealableHero":"Healable Heroes",
    "LogicalTypeTrainableMythUnit":"Trainable Myth Units",


    # Partial lies for clarity:
    "LogicalTypeHealed":"Healable Units",
    "LogicalTypeGarrisonInShips":"Transportable Units",
    "LogicalTypeFreezableMythUnit":"nearly all land Myth Units",
    "LogicalTypeBuildingSmall":"Buildings (except Wonder and Titan Gate)",
    "LogicalTypeBuildingLarge":"Buildings (except Wonder and Titan Gate)",
    "LogicalTypeSeidrTarget":"Hersir, Godi, and Valkyries",
    
    
}

_PLURAL_UNIT_NAMES = {
    "Serpent":"Serpents",
    "Automaton":"Automatons",
    "UFO":"UFOs",
    "VillagerDwarf":"Dwarves",
    "Wonder":"Wonders",
    "TitanGate":"Titan Gates",
    "Nidhogg":"Nidhogg",
    "Football":"Footballs",
    "SiegeWorks":"Siege Works",
    "TownCenter":"Town Centers",
    "TownCenterAbandoned":"Town Centers", # partial lie
    "Settlement":"Settlements/Unfinished Town Centers",
    "CitadelCenter":"Citadel Centers",
    "VillageCenter":"Village Centers",
    "House":"Houses",
    "Granary":"Granaries",
    "Temple":"Temples",
    "Dock":"Docks",
    "Armory":"Armories",
    "DwarvenArmory":"DwarvenArmories",
    "Market":"Markets",
    "Farm":"Farms",
    "FarmShennong":"Shennong's Farms",
    "SentryTower":"Sentry Towers",
    "Storehouse":"Storehouses",
    "Chicken":"Chickens",
    "ChickenEvil":"Chickens", # they explode, but ingame they are still simply "chicken"
    "SeaSnake":"Sea Snakes",
    "Kuafu":"Kuafus",
    "PiXiu":"Pixius",
    "BerryBush":"Berry Bushes",
    "MirrorTower":"Mirror Towers",
    "Fortress":"Fortresses",
    "MigdolStronghold":"Migdol Strongholds",
    "Palace":"Palaces",
    "AsgardianHillFort":"Asgardian Hill Forts",
    "Baolei":"Baoleis",
    "Pharaoh":"Pharaohs",
    "PharaohNewKingdom":"New Kingdom Pharaohs",
    "Carnivora":"Carnivora",
    "Tent":"Tents",
    "Obelisk":"Obelisks",
    "Lighthouse":"Lighthouses",
    "OxCartBuilding":"Ox Carts",
    "VillagerNorse":"Gatherers",
    "VillagerAtlantean":"Citizens",
    "VillagerAtlanteanHero":"Hero Citizens",
    "Oracle":"Oracles",
    "OracleHero":"Hero Oracles",
    "MachineWorkshopTower":"Machine Workshops (with Tower)",
    "MilitaryCampTower":"Military Camps (with Tower)",
    "TentSPC":"Tents",
    "VillagerChinese":"Peasants",
    "HillFort":"Hill Forts",
    "TreeCherryShrine":"Cherry Trees",
    "WolfShrineOfTheHunt":"Wolves",


    # Named characters or one-of-a-kinds that don't make sense to pluralise where "regular" objects would
    "TitanKronos":"Kronos",
    "ChiYouBig":"Chiyou",
    "Gargarensis":"Gargarensis",
    "SonOfOsiris":"Son of Osiris", # opting to not pluralise
}


# Unwrap abstract types with this many members or fewer into a list of actual object names
AUTO_UNWRAP_ABSTRACT_TYPE_SIZE = 2

# Always unwrap these
ABSTRACT_TYPES_TO_UNWRAP = (
    "SiegeLineUpgraded",    # Engineers target that excludes cheiroballista
    "HeroInfantry",
    # It is very hard to give these types short meaningful labels that clearly tell you what they contain and aren't confusable with the literal "Town Center"
    "AbstractTownCenter",
    "AbstractSettlement",
    "NonConvertableHerdable", # is just chicken right now
    "LogicalTypeValidSentinelTarget",
    "AbstractSocketedTownCenter",
    "AbstractTowerBuildLimit",
    "AbstractHouseBuildLimit",
)

AGE_LABELS = (f"{icon.generalIcon('resources/shared/static_color/technologies/archaic_age_icon.png')} Archaic",
              f"{icon.generalIcon('resources/shared/static_color/technologies/classical_age_icon.png')} Classical",
              f"{icon.generalIcon('resources/shared/static_color/technologies/heroic_age_icon.png')} Heroic",
              f"{icon.generalIcon('resources/shared/static_color/technologies/mythic_age_icon.png')} Mythic",
              f"{icon.generalIcon('resources/shared/static_color/technologies/wonder_age_icon.png')} Wonder")



def _getDisplayNamesFromAbstractClass(abstract: str, plural=False) -> List[str]:
    "Return user-facing display names from a single passed abstract class. External use should go thorugh getDisplayNameForProtoOrClass instead."
    if abstract in globals.protosByUnitType:
        targetsList = globals.protosByUnitType[abstract]
        if abstract in ABSTRACT_TYPES_TO_UNWRAP or len(targetsList) <= AUTO_UNWRAP_ABSTRACT_TYPE_SIZE: 
            return sorted(list(dict.fromkeys(map(lambda x: getDisplayNameForProtoOrClass(x, plural=plural), targetsList))))
    if plural:
        if abstract not in _UNIT_CLASS_LABELS_PLURAL:
            warn_unhandled(f"No plural label for unit class {abstract}")
            return [abstract]
        return [_UNIT_CLASS_LABELS_PLURAL[abstract]] # KeyError means a label needs adding to the dictionary manually
    if abstract not in _UNIT_CLASS_LABELS:
        warn_unhandled(f"No singular label for unit class {abstract}")
        return [abstract]
    return [_UNIT_CLASS_LABELS[abstract]] # KeyError means a label needs adding to the dictionary manually

def getListOfDisplayNamesForProtoOrClass(protoOrAbstract: Union[str, ET.Element, Iterable[Union[str, ET.Element]]], plural=False) -> List[str]:
    "Return a not-yet-joined user-facing display name encompassing a Protounit, abstract type, or list of any combination of these."
    if not isinstance(protoOrAbstract, str) and not isinstance(protoOrAbstract, ET.Element):
        # Assumed: some iterable combination of the two
        workingList = []
        for item in protoOrAbstract:
            workingList += getListOfDisplayNamesForProtoOrClass(item, plural)
        return sorted(list(set(workingList)))
    proto = protoFromName(protoOrAbstract)
    if proto is not None:
        return [getObjectDisplayName(proto, plural)]
    return _getDisplayNamesFromAbstractClass(protoOrAbstract, plural)

def getDisplayNameForProtoOrClass(protoOrAbstract: Union[str, ET.Element, Iterable[Union[str, ET.Element]]], plural=False) -> str:
    "Return a user-facing display name encompassing a Protounit, abstract type, or list of any combination of these."
    return commaSeparatedList(getListOfDisplayNamesForProtoOrClass(protoOrAbstract, plural))

def getDisplayNameForProtoOrClassPlural(protoOrAbstract: Union[str, ET.Element, Iterable[Union[str, ET.Element]]]) -> str:
    return getDisplayNameForProtoOrClass(protoOrAbstract, True)

def getObjectDisplayName(object: ET.Element, plural: bool = False) -> str:
    internalObjectName = object.attrib.get("name", None)
    if plural:
        if internalObjectName in _PLURAL_UNIT_NAMES:
            return _PLURAL_UNIT_NAMES[internalObjectName]
        warn_unhandled(f"No plural defined for object {internalObjectName}, assuming singular")
        
    override = _OVERRIDE_DISPLAY_NAMES.get(object.attrib.get("name", None), None)
    if override is not None:
        return override
    displayNameIdNode = object.find("displaynameid")
    if displayNameIdNode is not None:
        retval = globals.dataCollection["string_table.txt"].get(displayNameIdNode.text, None)
        if retval is not None:
            return retval
    retval = object.attrib.get("name", None)
    if retval is not None:
        return retval
    return None


def findAndFetchText(root: ET.Element, query: str, default, convert=None):
    node = root.find(query)
    if node is not None:
        if convert is not None:
            return convert(node.text)
        return node.text
    return default



def addToGlobalAbilityStrings(proto: Union[str, ET.Element], abilityNode: ET.Element, value: str):
    proto = protoFromName(proto)
    strId = findAndFetchText(abilityNode, "rolloverid", None)
    if strId not in globals.unitAbilityDescriptions:
        globals.unitAbilityDescriptions[strId] = {}
    if not value in globals.unitAbilityDescriptions[strId].values():
        globals.unitAbilityDescriptions[strId][proto] = value

def handleSharedStringIDConflicts(userDict: Dict[str, Dict[ET.Element, str]]):
    for key, valueDict in userDict.items():
        if len(valueDict) == 1:
            globals.stringMap[key] = list(valueDict.values())[0]
        else:
            # Multiple units share this ability. Combine them all?
            displayNames = []
            protoNames = []
            protoList = list(valueDict.keys())
            for proto in protoList:
                if proto is None:
                    errdict = {k.attrib['name'] if k is not None else None: valueDict[k] for k in valueDict.keys()}
                    raise ValueError(f"Conflict for stringid {key}: some members have None set as a source (expected ET.Element): {errdict}")
                protoName = proto.attrib["name"]
                displayName = getObjectDisplayName(proto)
                if displayName is None:
                    displayName = protoName
                if displayName not in displayNames:
                    displayNames.append(displayName) 
                protoNames.append(protoName)
            workingSet = displayNames if len(displayNames) == len(protoList) else protoNames
            descriptions = []
            # If identical number of lines, we can compare line-by-line
            # and just write in the lines that are different, if there aren't too many of them
            lineLists = dict([(key, value.split("\\n")) for key, value in valueDict.items()])
            linesInDescriptions = set([len(x) for x in lineLists.values()])
            # This is a complete mess. There's got to be a better way but it's not coming to me right now
            lineByLine = False
            if len(linesInDescriptions) == 1:
                numLines = list(linesInDescriptions)[0]
                numDiffLines = 0
                rawLinesByProto: List[Union[str, Dict[ET.Element, str]]] = []
                for lineIndex in range(0, numLines):
                    numValues = len(set([x[lineIndex] for x in lineLists.values()]))
                    if numValues > 1:
                        numDiffLines += 1
                        rawLinesByProto.append(dict([(key, value[lineIndex]) for key, value in lineLists.items()]))
                    else:
                        rawLinesByProto.append(list(lineLists.values())[0][lineIndex])
                if numDiffLines * 2 < numLines:
                    lineByLine = True

            if lineByLine:
                for lineIndex in range(0, numLines):
                    thisEntry = rawLinesByProto[lineIndex]
                    if isinstance(thisEntry, str):
                        descriptions.append(thisEntry)
                    else:
                        for i, proto in enumerate(protoList):
                            descriptions.append(f"{workingSet[i]}: {thisEntry[proto]}")
            else:
                for i, proto in enumerate(protoList):
                    desc = f"<tth>{workingSet[i]}:\\n{valueDict[proto]}"
                    descriptions.append(desc)
            globals.stringMap[key] = "\\n".join(descriptions)
            #print(key, valueDict.values())
            print(f"{workingSet} share {key} but want different values for it: written {'out each entry separately' if not lineByLine else 'line by line comparison'}")

def prependTextToHistoryFile(objectName: str, objectType: str, text: Union[str, List[str]]):
    """Prepend some amount of text to a history file.
    objectType should probably be one of "units" or "techs".
    objectName should be the proto/techtree tech name of the thing being modified.
    
    Fails if there is no history file for the given object."""

    historyFile = os.path.join(globals.historyPath, objectType, f"{objectName}.txt")
    if not os.path.isfile(historyFile):
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
        warn_data(f"History file for {objectType}/{objectName} has nonexistent string id {strid}, couldn't write its entry")
        return
    
    if not isinstance(text, str):
        text = "\\n".join(text)

    globals.stringMap[strid] = text + "\\n"*3 + "----------\\n" + globals.dataCollection["string_table.txt"][strid]

def findGodPowerByName(powerName: Union[str, ET.Element]) -> ET.Element:
    if isinstance(powerName, str):
        return globals.dataCollection["god_powers_combined"].find(f"power[@name='{powerName}']")
    return powerName

def collapseSpaces(string: str) -> str:
    return re.sub(" +", " ", string)
    
def attemptAllWordwiseTextMerges(inputStrings: List[str], outputIdentifier: Union[str, None]=None, maxReplacements=0.1):
    stringsByWordCount: Dict[int, List[str]] = {}
    for stringContent in inputStrings:
        count = len(collapseSpaces(stringContent).split(" "))
        if count not in stringsByWordCount:
            stringsByWordCount[count] = []
        stringsByWordCount[count].append(stringContent)
    

    for wordCount, strings in stringsByWordCount.items():
        if len(strings) > 1:
            # Variant of "powerset" from the itertools docs page!
            possibleStringLists = reversed(list(itertools.chain.from_iterable(itertools.combinations(strings, r) for r in range(2, len(strings)+1))))
            for possibleList in possibleStringLists:
                mergeResponse = wordwiseTextMerger(possibleList, outputIdentifier, maxReplacements)
                if mergeResponse is not None:
                    print(possibleList)
                    print(f"Fuzzy wordwise merge performed merge on {outputIdentifier} with wordcount {wordCount} -> {mergeResponse}")
                    for possibleString in possibleList:
                        inputStrings.remove(possibleString)
                    return [mergeResponse, *attemptAllWordwiseTextMerges(inputStrings, outputIdentifier, maxReplacements)]
                    #return [mergeResponse, *list(stringsWithColourisationKeys.keys())]
    return inputStrings

class WordwiseMergeRemoveAffixes:
    def __init__(self, words):
        words = list(set(words))
        output = []
        self.prefix = ""
        self.suffix = ""
        # Things we are trying to handle here:
        # Myth Unit: Damage: +10%
        # Myth Unit: Hitpoints: +10%
        # -> Myth Unit: Damage: and Hitpoints: +10% (need to avoid duplicated colons)

        # Merging "+1m/+2m/+3m" and make it into "+1/2/3m" or similar
        # (as well as worse issues like newlines becoming part of the split)

        # Nonsensical text merging, eg Arkantos and Ajax getting split to Arkantos and jax
        commonStartChars = 1
        commonEndChars = -1
        while 1:
            samplePrefix = words[0][:commonStartChars]
            # There is never a reason for prefixes to contain letters
            if not all([word.startswith(words[0][:commonStartChars]) for word in words]) or re.search("[0-9]", samplePrefix) is not None or re.search("[A-Za-z]", samplePrefix) is not None:
                commonStartChars -= 1
                break
            commonStartChars += 1
        while 1:
            sampleSuffix = words[0][commonEndChars:]
            hasNumericWord = False
            for word in words:
                try:
                    float(word[commonStartChars:commonStartChars+1])
                    hasNumericWord = True 
                    break
                except ValueError:
                    pass
            isBad = False
            # Letter suffixes only allowed if numeric, eg "2m" - but splitting up actual words is a no-no
            # So allow it only if the first character of any combinable word is a number
            if not hasNumericWord and re.search("[A-Za-z]", sampleSuffix):
                isBad = True
            elif not all([word.endswith(words[0][commonEndChars:]) for word in words]):
                isBad = True # suffix doesn't match
            elif re.search("[0-9]", sampleSuffix) is not None:
                isBad = True # numeric suffix never allowed
            if isBad:
                commonEndChars += 1
                break
            commonEndChars -= 1

        sharedPrefix = words[0][:commonStartChars]
        # Attempting slices with 0 as the end index introduces an extra suffix that shouldn't be there
        if commonEndChars == 0:
            sharedSuffix = ""
        else:
            sharedSuffix = words[0][commonEndChars:]
        for word in words:
            if commonEndChars == 0:
                strippedAffixes = word[commonStartChars:]
            else:
                strippedAffixes = word[commonStartChars:commonEndChars]
            output.append(strippedAffixes)
        self.words = output
        self.prefix = sharedPrefix
        self.suffix = sharedSuffix

        

def wordwiseTextMerger(strings: List[str], outputIdentifier: Union[str, None]=None, maxReplacements=0.1) -> Union[str, None]:
    """Try merging multiple strings into a single one wordwise. 

    :param strings: The strings to merge.
    :param outputIdentifier: An identifier included in error messages only.
    :return: None if merging was not possible, else a merged string
    :rtype: Union[str, None]
    """
    stringsSplitToWords = [collapseSpaces(string).split(" ") for string in strings]

    wordLengths = list(set([len(words) for words in stringsSplitToWords]))
    if len(wordLengths) > 1:
        return None
    
    items = []

    maxReplacementInt = max(1, round(maxReplacements*wordLengths[0]))
    diffIndexes = []

    outputWords = []

    for wordIndex in range(0, wordLengths[0]):
        thisWords = []
        for wordList in stringsSplitToWords:
            thisWords.append(wordList[wordIndex])
        affixes = WordwiseMergeRemoveAffixes(thisWords)
        if len(affixes.words) > 1:
            diffIndexes.append(wordIndex)
            if len(diffIndexes) > maxReplacementInt:
                return None
            # Don't allow merge of numbers 
            for word in affixes.words:
                try:
                    float(word)
                    return None
                except ValueError:
                    pass
                        
            outputWords.append(f"{affixes.prefix}{commaSeparatedList(affixes.words)}{affixes.suffix}")
        else:
            outputWords.append(thisWords[0])
    return " ".join(outputWords)
        
class DataWarning(UserWarning):
    "Warning for issues where the passed data files seem to be clearly at fault."
    pass

class UnhandledImplementationWarning(UserWarning):
    "Warning for unhandled cases of data which is quite possibly valid - eg new kinds of tech subtypes, or attributes on things for which there was no reason to write handling before."
    pass

def warn_data(msg: str):
    "Warning for when something in the data files seems to be clearly at fault."
    warnings.warn(msg, DataWarning, stacklevel=2)

def warn(msg: str):
    "Generic warning."
    warnings.warn(msg, stacklevel=2)

def warn_unhandled(msg: str):
    "Warning for unhandled cases of data which is quite possibly valid - eg new kinds of tech subtypes, or attributes on things for which there was no reason to write handling before."
    warnings.warn(msg, UnhandledImplementationWarning, stacklevel=2)