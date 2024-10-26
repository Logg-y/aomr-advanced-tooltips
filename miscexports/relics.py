import os
import sys

if not os.path.isdir("main.py"):
    sys.path.append("./")

import tech
import globals
import main
import common


def relics():
    main.prepareData()
    tech.generateTechDescriptions()
    out = {}
    for relicNode in globals.dataCollection["relics.xml"]:
        if "reserved" not in relicNode.attrib:
            techName = relicNode.attrib["tech"]
            techElem = globals.dataCollection["techtree.xml"].find(f"tech[@name='{techName}']")
            out[common.getObjectDisplayName(techElem)] = tech.processTech(techElem)

    with open("relics.txt", "w") as f:
        for techName, content in out.items():
            f.write(techName + "\n")
            f.write(content.replace("\\n", "\n"))
            f.write("\n"*3)

if __name__ == "__main__":
    relics()