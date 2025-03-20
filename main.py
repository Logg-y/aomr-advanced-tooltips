import configparser
import os
import xml.etree.ElementTree as ET
from typing import Dict
from unitdescription import generateUnitDescriptions
from tech import generateTechDescriptions
from godpower import generateGodPowerDescriptions
from majorgodtooltip import generateMajorGodDescriptions
from aotg import generateBlessingDescriptions
from loadingtips import generateLoadTips
import re
import globals
import json
import datetime
import common
import action

def readConfig() -> configparser.ConfigParser: 
    fp = "config.ini"
    # See if current working dir is just root, or if we need to switch to /scripts
    if not os.path.isfile(fp):
        raise FileNotFoundError(f"Didn't find config.ini - make a copy of configtemplate.ini and fill it!")
    config = configparser.ConfigParser()
    config.read(fp)
    return config

def readStringTable(path) -> Dict[str, str]:
    with open(path, "r", encoding="utf8") as f:
        c = f.read()
    pattern = re.compile("ID\\W*=\\W*\"(.*?)\".*?Str\\W*=\\W*\"((?:[^\"\\\\]|\\\\.)*?)\"")
    matches = pattern.finditer(c)
    table = {}
    for match in matches:
        key, value = match.groups()
        table[key] = value
    return table

def mergeXmls(parent: ET.Element, child: ET.Element):
    for elem in child:
        parent.append(elem)

def loadXmls(gameplayDir):
    subpaths = ("", "abilities", "god_powers", "tactics")
    for subpath in subpaths:
        currentdir = os.path.join(gameplayDir, subpath)
        for xml in os.listdir(currentdir):
            filepath = os.path.join(currentdir, xml)
            if xml.endswith(".xml") or xml.endswith(".tactics") or xml.endswith(".abilities") or xml.endswith(".godpowers") or xml.endswith(".techtree"):
                root = ET.parse(filepath).getroot()
                if subpath == "":
                    globals.dataCollection[xml] = root
                else:
                    if subpath not in globals.dataCollection:
                        globals.dataCollection[subpath] = {}
                    globals.dataCollection[subpath][xml] = root
            if xml.endswith(".simjson"):
                with open(filepath, encoding="utf8") as f:
                    doc = json.load(f)
                    globals.dataCollection[xml] = doc
    
    mergeXmls(globals.dataCollection['techtree.xml'], globals.dataCollection['aotg_techtree.techtree'])
    mergeXmls(globals.dataCollection['proto.xml'], globals.dataCollection['aotg_proto.xml'])


def mergeAbilities():
    abilities = ET.Element("powers")
    for filename in [x for x in list(globals.dataCollection["abilities"].keys()) if x.endswith(".abilities")]:
        root = globals.dataCollection["abilities"][filename]
        for child in root:
            abilities.insert(0, child)
    globals.dataCollection["abilities_combined"] = abilities
    abilities = ET.Element("powers")
    for filename in [x for x in list(globals.dataCollection["god_powers"].keys()) if x.endswith(".godpowers")]:
        root = globals.dataCollection["god_powers"][filename]
        for child in root:
            abilities.insert(0, child)
    globals.dataCollection["god_powers_combined"] = abilities

def loadGameCfg():
    configData = {}
    with open(os.path.join(globals.config["paths"]["configPath"], "game.cfg")) as f:
        for line in f:
            stripped = line.strip()
            if stripped == "" or stripped.startswith("//"):
                continue
            if "//" in stripped:
                stripped = stripped[:stripped.find("//")].strip()
            if stripped.startswith("+"):
                stripped = stripped[1:].strip()
            isString = False
            twoPart = re.match("([A-Za-z0-9]*)(?:\\s*=\\s*|\\s+)(-?[0-9.]*);?\\Z", stripped)
            if twoPart is None:
                twoPart = re.match("([A-Za-z0-9]*)(?:\\s*=\\s*|\\s+)\"(.*)\";?\\Z", stripped)
                isString = True
            if twoPart is not None:
                value = twoPart.groups()[1]
                if isString:
                    valueTyped = value
                elif "." in value:
                    valueTyped = float(value)
                else:
                    valueTyped = int(value)
                configData[twoPart.groups()[0]] = valueTyped
            else:
                if "=" in stripped in " " in stripped:
                    raise ValueError(f"Failed cfg parse at: {stripped}")
                configData[stripped] = True

    globals.dataCollection["game.cfg"] = configData

def parseUnitTypeData():
    for unitTypeEntry in globals.dataCollection['unit_type_data.xml']:
        globals.unitTypeData[unitTypeEntry.find("unittype").text] = unitTypeEntry
    #for abstractType in globals.dataCollection['abstract_unit_types.xml']:
    #    globals.abstractTypes.add(abstractType.text)
    for proto in globals.dataCollection['proto.xml']:
        for unittype in proto.findall("unittype"):
            if unittype.text not in globals.protosByUnitType:
                globals.protosByUnitType[unittype.text] = []
            globals.protosByUnitType[unittype.text].append(proto.attrib['name'])
    globals.abstractTypes = set(globals.protosByUnitType.keys())

def prepareData():
    globals.config = readConfig()
    gameplayDir = os.path.join(globals.config["paths"]["dataPath"], "game/data/gameplay")
    loadXmls(gameplayDir)
    
    globals.dataCollection["string_table.txt"] = readStringTable(os.path.join(globals.config["paths"]["dataPath"], "game/data/strings", globals.config["paths"]["lang"], "string_table.txt"))

    # I think someone did some sillies. These strings are missing in the base game and it breaks my code!
    if "STR_ABILITY_PETRIFIED_FRAME" not in globals.dataCollection["string_table.txt"]:
        globals.dataCollection["string_table.txt"]["STR_ABILITY_PETRIFIED_FRAME"] = "Petrified Frame"
    parseUnitTypeData()
    mergeAbilities()
    loadGameCfg()
    globals.historyPath = os.path.join(globals.config["paths"]["dataPath"], "game/data/strings", globals.config["paths"]["lang"], "history")

def main():
    print("Beginning build...")
    prepareData()

    # This class doesn't include Nidhogg, for now
    mythUnitNotTitanExceptions = ["Titan"]
    # This is technically correct but returns some useless things like Locusts
    #for protoElem in globals.dataCollection["proto.xml"]:
    #    if protoElem.find("unittype[.='MythUnit']", None) is not None:
    #        if protoElem.find("unittype[.='LogicalTypeMythUnitNotTitan']", None) is None:
    #            mythUnitNotTitanExceptions.append(protoElem.attrib['name'])

    possibleMythUnitNotTitanExceptions = ("Nidhogg", "YingLong")
    for exception in possibleMythUnitNotTitanExceptions:
        if common.protoFromName(exception).find("unittype[.='LogicalTypeMythUnitNotTitan']") is None:
            mythUnitNotTitanExceptions.append(exception)
    replacement = f"(except {common.commaSeparatedList(mythUnitNotTitanExceptions)})"
    common._UNIT_CLASS_LABELS["LogicalTypeMythUnitNotTitan"] = common._UNIT_CLASS_LABELS["LogicalTypeMythUnitNotTitan"].replace("LOGICAL_TYPE_MYTH_UNIT_NOT_TITAN_EXCEPTION", replacement)
    common._UNIT_CLASS_LABELS_PLURAL["LogicalTypeMythUnitNotTitan"] = common._UNIT_CLASS_LABELS_PLURAL["LogicalTypeMythUnitNotTitan"].replace("LOGICAL_TYPE_MYTH_UNIT_NOT_TITAN_EXCEPTION", replacement)
    
    generateTechDescriptions()           
    generateUnitDescriptions()
    generateGodPowerDescriptions()
    generateMajorGodDescriptions()
    generateBlessingDescriptions()
    generateLoadTips()
    
    
    additionalCompendium = f"\\n\\nAdvanced Tooltips is active for (hopefully correct) additional information!\\nThis version was built on {datetime.datetime.now().strftime('%d %b %y')}. Game updates or data mods will make displayed values incorrect."
    additionalCompendium += "\\n\\nAll stats shown in tooltips are for the unit's base data - any techs that apply will NOT be included, including 'hidden' effects such as the bonuses from age advancement given to heroes and myth units.\\n\\n"
    additionalCompendium += f"\'Snares\' is used as a shorthand for the 'standard' slowing effect ({100*(1.0-action.STANDARD_SNARE['rate']):0.3g}% for {action.STANDARD_SNARE['duration']:0.3g} seconds) caused primarily by nearly every melee attack in the game. Effects that slow movement by any other amount or duration will list their true numbers."
    globals.stringMap["STR_HISTORY_HISTORY"] = globals.dataCollection["string_table.txt"]["STR_HISTORY_HISTORY"] + additionalCompendium
    
    
    with open(os.path.join(globals.config["paths"]["outputPath"], "game/data/strings/stringmods.txt"), "w", encoding="utf8") as f:
        for strid, value in globals.stringMap.items():
            f.write(f"ID = \"{strid}\"   ;   Str = \"{value}\"\n")
                        
    
    
if __name__ == "__main__":
    main()