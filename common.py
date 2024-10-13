import globals
from xml.etree import ElementTree as ET
from typing import Union, List, Dict



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

OVERRIDE_DISPLAY_NAMES = {
    "MinionReincarnated":"Minion (Mummy)",
    "Minion":"Minion (Ancestors)",
    "HeroOfRagnarok":"Hero of Ragnarok (Gatherer)",
    "HeroOfRagnarokDwarf":"Hero of Ragnarok (Dwarf)",
    "ProjectileSatyrSpearSpecialAttack": "Satyr Piercing Throw Spear",
    "BerserkDamageBoost":"Invisible Berserk Damage Booster",
    "EyesOnForestRevealer":"Revealer",
    "SunRayRevealer":"Revealer",
    "SunRayGroundRevealer":"Revealer",
    "ChimeraFireArea":"Chimera Special Fire Area",
    # TODO hopefully remove this WW hackery once the underlying data is fixed
    "WalkingWoodsCypress":"Most trees",
    "WalkingWoodsHades":"Hades trees",
}


UNIT_CLASS_LABELS = {
    "Hero": "Hero",
    "AbstractInfantry":"Infantry",
    "AbstractCavalry":"Cavalry",
    "AbstractArcher":"Ranged Soldier",
    "AbstractSiegeWeapon":"Siege",
    "AbstractVillager":"Villager",
    "AbstractArcherShip":"Archer Ship",
    "AbstractCloseCombatShip":"Close Combat Ship",
    "AbstractSiegeShip":"Siege Ship",
    "CavalryLineUpgraded": "Cavalry Line Upgrades",
    "InfantryLineUpgraded": "Infantry Line Upgrades",
    "ArcherLineUpgraded": "Ranged Line Upgrades",
    "Building":"Building",
    "MythUnit":"Myth Unit",
    "HumanSoldier":"Human Soldier",
    "Huntable":"Huntable",
    "Ship": "Ship",
    "FoodDropsite": "Food Dropsite",
    "WoodDropsite": "Wood Dropsite",
    "GoldDropsite": "Gold Dropsite",
    "HeroShadowUpgraded":"Upgrades with Age",
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
    "LogicalTypeBuildingsNotWalls":"Buildings (except Walls)",
    "LogicalTypeMythUnitNotTitan":"Myth Units (except Titans)",
    "LogicalTypeShipNotHero":"Ships (except Heroes)",
    "LogicalTypeVillagerNotHero":"Villagers (except Heroes)",
    "Favor":"Favor",
    "AbstractMonument":"Monuments",
    "WoodResource":"Wood",
    "GoldResource":"Gold",
    "FishResource":"Fish",
    "Food":"Food",
    "AbstractFarm":"Farms",
    "Herdable":"Herdables",
    "NonConvertableHerdable":"Chicken-like",
    "LogicalTypeHealed":"Healable Units",
    "AbstractHealer":"Healer",
    "AbstractTownCenter":"Town Centers",
    "AbstractFortress":"Fortress Buildings",
    "LogicalTypeBuildingNotWonderOrTitan":"Buildings (except Wonder and Titan Gate)",
    "LogicalTypeRangedMythUnit":"Ranged Myth Units",
    "LogicalTypeBuildingsThatShoot":"Buildings that Shoot",
    "AbstractEmpowerer":"Empowerer",

    # Partial Lies
    "EconomicUpgraded":"Villager",
    "TradeUnit":"Caravan",
    "AbstractWall":"Wall",
    "AbstractSettlement":"Town Center",
    "LogicalTypeSunRayProjectile":"Projectile",
    "AbstractTemple":"Temple",
}

UNIT_CLASS_LABELS_PLURAL = {
    "MilitaryUnit":"Military Units",
    "EconomicUnit":"Economic Units",
    "Unit":"Units",
    "Building":"Buildings",
    "AbstractSiegeWeapon":"Siege Weapons",
    "Huntable":"Huntables",
    "AbstractFlyingUnit":"Flying Units",
    "HumanSoldier":"Human Soldiers",
    "LogicalTypeMythUnitNotTitan":"Myth Units (except Titans)",
    "LogicalTypeVillagerNotHero":"Villagers (except Heroes)",
    "TradeUnit":"Caravans",
    "LogicalTypeMythUnitNotTitan":"Myth Units (except Titans)",
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
    "LogicalTypeSeidrTarget":"Hersir, Godi, and Valkyrie",
    "LogicalTypeMilitaryProductionBuilding":"Military Production Buildings",
    "AbstractTemple":"Temples",

    # Specific protos
    "Serpent":"Serpents",
    "Automaton":"Automatons",
    "UFO":"UFOs",
    "VillagerDwarf":"Dwarves",
    "Wonder":"Wonders",
    "TitanGate":"Titan Gates",
    "Nidhogg":"Nidhogg",
    "Football":"Footballs",
    "SiegeWorks":"Siege Works",

    # Partial lies for clarity:
    "LogicalTypeHealed":"Units",
    "LogicalTypeGarrisonInShips":"Transportable Units",
    "LogicalTypeFreezableMythUnit":"nearly all land Myth Units",
    "LogicalTypeBuildingSmall":"Buildings (except Wonder and Titan Gate)",
    "LogicalTypeBuildingLarge":"Buildings (except Wonder and Titan Gate)",
}

def commaSeparatedList(words: List[str], joiner="and"):
    if len(words) == 0:
        return ""
    if len(words) == 1:
        return words[0]
    separated = ", ".join(words[:-1])
    separated += f" {joiner} " + words[-1]
    return separated

def getDisplayNameForProtoOrClass(object: Union[str, ET.Element]) -> str:
    if not isinstance(object, str):
        return getObjectDisplayName(object)
    proto = protoFromName(object)
    if proto is not None:
        return getObjectDisplayName(proto)
    return UNIT_CLASS_LABELS[object] # KeyError means a label needs adding to the dictionary manually

def getObjectDisplayName(object: ET.Element) -> str:
    override = OVERRIDE_DISPLAY_NAMES.get(object.attrib.get("name", None), None)
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

def protoFromName(protoName: Union[ET.Element, str]) -> Union[ET.Element, None]:
    if isinstance(protoName, ET.Element):
        return protoName
    return globals.dataCollection["proto.xml"].find(f"./*[@name='{protoName}']")


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
