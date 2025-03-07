import globals
import common
from xml.etree import ElementTree as ET
from typing import Dict, Callable, List, Union
import tech
import pprint
import re
import dataclasses
import action
import unitdescription
import icon

RARITY_COLOURS: Dict[int, Callable[[str], str]] = {
    0: lambda s: "<color=0.80,0.80,0.80>" + s + "</color>", # simple, grey
    1: lambda s: "<color=0.55,0.82,0.42>" + s + "</color>", # fine, green
    2: lambda s: "<color=0.36,0.60,1.00>" + s + "</color>", # heroic, blue
    3: lambda s: "<color=0.81,0.42,0.98>" + s + "</color>", # mythical, purple
    4: lambda s: "<color=1.00,0.50,0.20>" + s + "</color>", # divine, orange
    5: lambda s: "<color=0.93,0.31,0.31>" + s + "</color>", # eternal, red
}

def wordwiseBlessingHandler(stringId: str, elemsByRarity: Dict[int, ET.Element]) -> Union[str, None]:
    stringsToRarity: Dict[str, int] = {}
    for rarity, techElem in elemsByRarity.items():
        response = tech.processTech(techElem)
        if response is not None and len(response.strip()) > 0:
            stringsToRarity[response] = rarity
    if len(stringsToRarity) == 0:
        #print(f"Warning: no text generated for blessing {stringId}")
        return None
    

    textByRarity: Dict[int, List[str]] = {}
    for stringContent, rarity in stringsToRarity.items():
        if rarity is None:
            rarity = len(textByRarity)
        if rarity in textByRarity:
            raise ValueError(f"Aotg wordwise text merger: duplicate colourisation key {rarity} for {stringId}")
        textByRarity[rarity] = common.collapseSpaces(stringContent).split(" ")

    wordLengths = list(set([len(words) for words in textByRarity.values()]))
    if len(wordLengths) > 1:
        raise ValueError(f"Aotg wordwise tech merger: different word lengths for {stringId}")
    
    items = []

    for wordIndex in range(0, wordLengths[0]):
        thisWord = {}
        for rarity, wordList in textByRarity.items():
            thisWord[rarity] = wordList[wordIndex]
        wordsAtThisPosition: List[str] = list(set(thisWord.values()))
        if len(wordsAtThisPosition) == 1:
            items.append(thisWord[rarity])
        else:
            affixes = common.WordwiseMergeRemoveAffixes(wordsAtThisPosition)
            # Look for common prefix/suffix, and move that outside the split section
            # This should stop "+1m/+2m/+3m" and make it into "+1/2/3m" or similar
            # (as well as worse issues like newlines becoming part of the split)
            commonStartChars = len(affixes.prefix)
            commonEndChars = len(affixes.suffix)
            #print(affixes.prefix, affixes.suffix, affixes.words)
            sortedVariants = []
            for rarity in textByRarity:
                thisText = textByRarity[rarity][wordIndex]
                if commonEndChars == 0:
                    strippedAffixes = thisText[commonStartChars:]
                else:
                    strippedAffixes = thisText[commonStartChars:-commonEndChars]
                #print(stringId, strippedAffixes, thisText, commonStartChars, commonEndChars)
                sortedVariants.append(RARITY_COLOURS[rarity](strippedAffixes))
            items.append(f"{affixes.prefix}{'/'.join(sortedVariants)}{affixes.suffix}")
    return " ".join(items)

    

def incrementalBlessingHandler(introText="Higher tiers of this blessing grant all lower tiers' effects as well.") -> Callable[[str, Dict[int, str]], Union[str, None]]:
    def inner(stringId: str, elemsByRarity: Dict[int, ET.Element]):
        items = [introText]
        for rarity in sorted(elemsByRarity.keys()):
            colour = RARITY_COLOURS[rarity]
            techElem = elemsByRarity[rarity]
            response = tech.processTech(techElem)
            if response is not None:
                items += [f"{colour(text)}" for text in response.split("\\n")]
        return "\\n".join(items)
    return inner

AGES_TO_INDEX = {
    "ArchaicAge":0,
    "ClassicalAge":1,
    "HeroicAge":2,
    "MythicAge":3,
    "WonderAge":4,
}

def ageProgressionBlessingHandler(stringId: str, elemsByRarity: Dict[int, ET.Element]):
    ageData: Dict[str, Dict[int, ET.Element]] = {}
    for rarity in sorted(elemsByRarity.keys()):
        colour = RARITY_COLOURS[rarity]
        techElem = elemsByRarity[rarity]
        techTargets = [common.techFromName(e.text) for e in techElem.findall("effects/effect[@type='TechStatus']")]
        for target in techTargets:
            targetAge = target.find("prereqs/specificage").text
            if targetAge not in ageData:
                ageData[targetAge] = {}
            ageData[targetAge][rarity] = target
    responsesByAgeIndex = {}
    for age, entriesByRarity in ageData.items():
        response = wordwiseBlessingHandler(f"_{age}_{stringId}", entriesByRarity)
        index = AGES_TO_INDEX[age]
        responsesByAgeIndex[index] = response
    
    responses = [f"{common.AGE_LABELS[index]}: {responsesByAgeIndex[index]}" for index in sorted(responsesByAgeIndex.keys())]
    
    return "\\n".join(responses)

@dataclasses.dataclass
class AotgBlessingHandler:
    handlerFunction: Callable[[str, Dict[int, str]], Union[str, None]] = wordwiseBlessingHandler
    postHandlerProcess: Callable[[str], str] = lambda x: x
    

aotgBlessingHandlers: Dict[str, AotgBlessingHandler] = {}

def generateBlessingDescriptions():

    defaultHandler = AotgBlessingHandler()

    aotgBlessingHandlers["STR_AOTG_EFF_KASTOR_RETINUE_DESC"] = AotgBlessingHandler(handlerFunction=incrementalBlessingHandler("Higher tiers of this blessing grant all lower tier units as well. The population boost also stacks."), postHandlerProcess=lambda s: s.replace("Town Center: Spawns", "Start with:"))

    # On current data, this horrible looking target list really just filter down to all heroes
    aotgBlessingHandlers["STR_AOTG_EFF_HERO_AREA_DAMAGE_DESC"] = AotgBlessingHandler(postHandlerProcess=lambda s: s.replace("Heroes with Build Limits, Legends and Heroes without Build Limits", "Hero"))

    def mythExplodePostHandler(s):
        s = s.replace("DPS", "Explodes on Death")
        s = re.sub("Myth Unit: On death[^\\\\]*", "", s)
        return s.strip()
    aotgBlessingHandlers["STR_AOTG_EFF_MYTH_DEATH_EXPLODE_DESC"] = AotgBlessingHandler(postHandlerProcess=mythExplodePostHandler)

    # This is just simpler.
    aotgBlessingHandlers["STR_AOTG_EFF_HOUSE_VILL_SPAWN_DESC"] = AotgBlessingHandler(handlerFunction=lambda x, y: "Houses and Manors cost double, but spawn a Villager when built.")

    gaiaTech = common.techFromName("AOTGGaiaUniqueTech")

    gaiaTechCost = " ".join([f"{icon.resourceIcon(costElem.attrib['resourcetype'])} {float(costElem.text):0.3g}" for costElem in gaiaTech.findall("cost")])
    gaiaTechCost += f" {icon.iconTime()} {float(gaiaTech.find('researchpoints').text):0.3g}"
    blessingDryad = common.protoFromName("DryadBlessing")

    aotgBlessingHandlers["STR_AOTG_EFF_GAIA_UNIQUE_DESC"] = AotgBlessingHandler(handlerFunction= lambda x, y: f"Town Centers may spend {gaiaTechCost} to produce 10 Dryads. These Dryads lose {-1*common.findAndFetchText(blessingDryad, "unitregen", 0.0, float):0.3g} hitpoints/second.")

    aotgBlessingHandlers["STR_BLESS_EFF_FAVOR_ON_AGE_UP_DESC"] = AotgBlessingHandler(handlerFunction=ageProgressionBlessingHandler)
    aotgBlessingHandlers["STR_BLESS_EFF_HEALING_TEMPLES_DESC"] = AotgBlessingHandler(handlerFunction=ageProgressionBlessingHandler)
    aotgBlessingHandlers["STR_AOTG_EFF_DWARF_ON_AGE_UP_DESC"] = AotgBlessingHandler(handlerFunction=ageProgressionBlessingHandler)
    aotgBlessingHandlers["STR_BLESS_EFF_AGE_UP_MYTH_UNIT_DESC"] = AotgBlessingHandler(handlerFunction=ageProgressionBlessingHandler)

    # stringid: {rarity: techtree element}
    stringIdsToTechUsers: Dict[str, Dict[int, ET.Element]] = {}

    for effect in globals.dataCollection['aotg_effects.xml']:
        techName = common.findAndFetchText(effect, "tech", None, str)
        stringId = common.findAndFetchText(effect, "descriptionid", None, str)
        if stringId is None or techName is None:
            continue
        rarity = common.findAndFetchText(effect, "rarity", None, int)
        techElem = globals.dataCollection['techtree.xml'].find(f"tech[@name='{techName}']")
        if techElem is None:
            continue
        if rarity not in RARITY_COLOURS:
            #print(f"Warning: {techElem.attrib['name']} has unknown rarity {rarity}, ignoring")
            continue
        
        if stringId not in stringIdsToTechUsers:
            stringIdsToTechUsers[stringId] = {}
        stringIdsToTechUsers[stringId][rarity] = techElem

    
    for stringId in stringIdsToTechUsers:
        # As of right now there is no way to get tier 3 (eternal) of blessings with 0-2 defined
        # With daily challenges I don't know if I can take this chance any more - can extract colours for the unseen tiers from the blessing UI border assets
        #if 0 in stringIdsToTechUsers[stringId] and 1 in stringIdsToTechUsers[stringId] and 2 in stringIdsToTechUsers[stringId]:
        #    if 3 in stringIdsToTechUsers[stringId]:
        #        del stringIdsToTechUsers[stringId][3]

        handler = aotgBlessingHandlers.get(stringId, defaultHandler)
        response = handler.handlerFunction(stringId, stringIdsToTechUsers[stringId])
        if response is not None:
            response = handler.postHandlerProcess(response)
            globals.stringMap[stringId] = response

    otherAotgStrings()

def otherAotgStrings():
    # World twist text

    # Gaia's Remnants of Atlantis - fine
    # Thoth's Divine Wisdom - fine
    # Freyja's Second Ride - the box is too small, trying to document this fully is hopeless.
    freyja = f"Cavalry are {100*(float(globals.dataCollection['techtree.xml'].find("tech[@name='AOTGFreyjaMinorWT']").find("effects/effect").attrib['amount'])-1.0):0.3g}% more expensive, but spawn infantry units when killed."
    # The new daily challenges unfortunately don't offer a scrollbar, meaning listing all the unit effects isn't really an option any more.
    #for culture in ("Greek", "Egyptian", "Norse", "Atlantean"):
    #    freyja += "\\n" + tech.processTech(common.techFromName(f"AOTGFreyjaMinorWT{culture}"))
    globals.stringMap["STR_AOTG_RULE_FREYJA_MINOR_DESC"] = freyja

    # Prometheus' Secret Knowledge
    prometheusTGBuildPoints = float(globals.dataCollection['techtree.xml'].find("tech[@name='AOTGPrometheusMinorWT']").find("effect[@subtype='BuildPoints']").attrib['amount'])
    prometheusTGAutoBuild = float(globals.dataCollection['techtree.xml'].find("tech[@name='AOTGPrometheusMinorWT']").find("effect[@subtype='AutoBuildRate']").attrib['amount'])
    globals.stringMap["STR_AOTG_RULE_PROMETHEUS_MINOR_DESC"] = f"Human players start with a free usage of Titan Gate. It takes {prometheusTGBuildPoints:0.3g}x longer to build than normal, but slowly builds itself as if {prometheusTGAutoBuild:0.3g} Greek villagers were working on it."

    # Hel's Mythic Frenzy - The tech changes BUILD POINTS???
    hel = tech.processTech(globals.dataCollection['techtree.xml'].find("tech[@name='AOTGHelMinorWT']"))
    hel = re.sub("Myth Unit: Build Time[^\\\\]*", "", hel)
    if hel.startswith("\\n"):
        hel = hel[2:]
    globals.stringMap["STR_AOTG_RULE_HEL_MINOR_DESC"] = hel

    # Athena's Vanguard Heroism - probably need to do something with this
    athena = f"Heroes cost no Favor. When a Hero dies, {action.actionOnHitNonDoTEffects('AthenaMinorWTDeathContainerMinor', action.findActionByName('AthenaMinorWTDeathContainerMinor', 'BoostOnDeath'))} Heroes with build limits or that cannot be mass produced offer double the damage bonus over double the radius."
    globals.stringMap["STR_AOTG_RULE_ATHENA_MINOR_ALT_DESC"] = athena

    # Horus' Ancestral Protection
    globals.stringMap["STR_AOTG_RULE_HORUS_MINOR_DESC"] = tech.processTech(common.techFromName("AOTGHorusMinorWT"))

    # Aphrodite's Rite of Flourishing
    globals.stringMap["STR_AOTG_RULE_APHRODITE_MINOR_DESC"] = "Affects human players only. 10 minutes into the game, all Villagers are duplicated.\\n" + tech.processTech(common.techFromName("AOTGAphroditeMinorWT"))

    # Oceanus' Driftwood Empire - not used, but it's in the data
    globals.stringMap["STR_AOTG_RULE_OCEANUS_MINOR_DESC"] = "Affects human players only. Start with +10000 Wood, but Villagers cannot gather any more."

    # Freyr's Harsh Weather
    # Loki's Harsh Weather
    globals.stringMap["STR_AOTG_WT_HARSHSEASONS_SPRING_BONUS"] = "Villagers and Human Soldiers train twice as fast"
    globals.stringMap["STR_AOTG_WT_HARSHSEASONS_SUMMER_BONUS"] = "Forest Fires a random tree every 30 seconds, then regrows it with Gaia Forest"
    globals.stringMap["STR_AOTG_WT_HARSHSEASONS_AUTUMN_BONUS"] = "Villager food gather rates +100% of base"
    globals.stringMap["STR_AOTG_WT_HARSHSEASONS_WINTER_BONUS"] = "Casts Frost (10s) at a random unit of every player after 45s"
    globals.stringMap["STR_AOTG_WT_HARSHSEASONS_WINTER_BONUS_2"] = "0.3 Favor per second"
    globals.stringMap["STR_AOTG_WT_HARSHSEASONS_WINTER_BONUS_3"] = "Myth units +50% base speed, Human Soldiers -30% base speed"
    globals.stringMap["STR_AOTG_WT_HARSHSEASONS_WINTER_BONUS_4"] = "Casts Fimbulwinter (halved wolf spawns) after 45s"

    