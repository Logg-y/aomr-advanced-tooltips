from xml.etree import ElementTree as ET
from typing import Dict, Union, Set, List

config = None

historyPath = ""

# The working dict of string ids: replacements
stringMap: Dict[str, str] = {}

# In most cases: filename.xml : XML root
# "string_table":{strid:strvalue}
dataCollection: Dict[str, Union[ET.Element, Dict[str, Union[ET.Element, str]], Dict[str, Union[float, int, bool]]]] = {}
# protoName: techName that looks like it respawns it
respawnTechs: Dict[str, str] = {}
# While doing its thing, the unit processor also wants to save output for unit abilities
# strid:{proto ET node:target description}
unitAbilityDescriptions: Dict[str, Dict[ET.Element, str]] = {}

unitTypeData: Dict[str, ET.Element] = {}

abstractTypes: Set[str] = set()

protosByUnitType: Dict[str, List[str]] = {}