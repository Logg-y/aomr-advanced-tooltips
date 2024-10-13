import configparser
import os
import xml.etree.ElementTree as ET
from typing import Dict
from unitdescription import generateUnitDescriptions
from tech import generateTechDescriptions
import re
import globals

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

def loadXmls(gameplayDir):
    subpaths = ("", "abilities", "god_powers", "tactics")
    for subpath in subpaths:
        currentdir = os.path.join(gameplayDir, subpath)
        for xml in os.listdir(currentdir):
            if xml.endswith(".xml") or xml.endswith(".tactics") or xml.endswith(".abilities") or xml.endswith(".godpowers"):
                filepath = os.path.join(currentdir, xml)
                root = ET.parse(filepath).getroot()
                if subpath == "":
                    globals.dataCollection[xml] = root
                else:
                    if subpath not in globals.dataCollection:
                        globals.dataCollection[subpath] = {}
                    globals.dataCollection[subpath][xml] = root

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
    

def main():
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

    generateTechDescriptions()           
    generateUnitDescriptions()
    
    
    with open(os.path.join(globals.config["paths"]["outputPath"], "game/data/strings/stringmods.txt"), "w", encoding="utf8") as f:
        for strid, value in globals.stringMap.items():
            f.write(f"ID = \"{strid}\"   ;   Str = \"{value}\"\n")
                        
    
    
if __name__ == "__main__":
    main()