import globals
import action
import common
import icon
import re
import unitdescription
import godpower
import tech

def generateMajorGodDescriptions():
    raContent = globals.dataCollection['string_table.txt']["STR_CIV_RA_LR"]
    raMonumentEmpowerRadius = float(action.actionTactics('MonumentToVillagers', None).find("action[name='MonumentEmpowerAura']/maxrange").text)
    globals.stringMap["STR_CIV_RA_LR"] = raContent.replace("empower nearby buildings", f"empower your Buildings within {raMonumentEmpowerRadius:0.3g}m")

    isisContent = globals.dataCollection['string_table.txt']["STR_CIV_ISIS_LR"]
    isisContent = re.sub("Empowered Monuments.*?and", "Monuments: " + action.describeAction("MonumentToVillagers", "AreaHeal") + f"\n{icon.BULLET_POINT} Empowered Monuments also", isisContent)
    globals.stringMap["STR_CIV_ISIS_LR"] = isisContent

    setContent = globals.dataCollection['string_table.txt']["STR_CIV_SET_LR"]
    setMonumentRadius = float(action.actionTactics('MonumentToVillagers', None).find("action[name='DevoteesMedium']/maxrange").text)
    globals.stringMap["STR_CIV_SET_LR"] = re.sub("reduce the cost of units in nearby (.*?) by", f"reduce the cost of Barracks and Migdol units in \\1 within {setMonumentRadius:0.3g}m by", setContent)

    thorContent = globals.dataCollection['string_table.txt']["STR_CIV_THOR_LR"]
    thorTech = globals.dataCollection["techtree.xml"].find("tech[@name='ArchaicAgeThor']")
    thorDwarfBuffMagnitude = list(set([float(x.attrib['amount']) for x in thorTech.findall("effects/effect[@subtype='WorkRate']")]))
    thorDwarfBuffRestypes= [(x.attrib['unittype']) for x in thorTech.findall("effects/effect[@subtype='WorkRate']")]
    if len(thorDwarfBuffMagnitude) != 1:
        raise ValueError(f"Bad thor dwarf buff magnitudes: {thorDwarfBuffMagnitude}")
    
    
    thorDwarfBuffText = f"Dwarves have +{100*(thorDwarfBuffMagnitude[0]-1):0.3g}% base gather rates for resources except Gold. This makes them close to Gatherers initially, but they will fall behind with economic upgrades. Relative unupgraded gather rates:\n"
    thorDwarfBuffText += ''.join([f"   {icon.BULLET_POINT_ALT} {common.getDisplayNameForProtoOrClass(restype)}: {unitdescription.compareGatherRates('VillagerDwarf', 'VillagerNorse', restype, protoOneMult=thorDwarfBuffMagnitude[0])}\\n" for restype in thorDwarfBuffRestypes])

    thorContent = re.sub("-10 Gold.*", f"-10 Gold.\n{icon.BULLET_POINT} {thorDwarfBuffText}", thorContent)
    globals.stringMap["STR_CIV_THOR_LR"] = thorContent

    odinContent = globals.dataCollection['string_table.txt']["STR_CIV_ODIN_LR"]
    odinRavenTimer = f"{float(globals.respawnTechs.get('Raven', None).find('delay').text):0.3g}"
    odinContent = re.sub(", and respawn a.*", f". Killed Ravens respawn in {odinRavenTimer} seconds. If both are dead at the same time, the second must wait for the first to respawn before beginning its timer.", odinContent)
    globals.stringMap["STR_CIV_ODIN_LR"] = odinContent

    lokiContent = globals.dataCollection['string_table.txt']["STR_CIV_LOKI_LR"]
    lokiBonusUnitSpawning = globals.dataCollection['major_gods.xml'].find("civ[name='Loki']/bonusunitspawning/damagegoal")
    lokiExcludedTargets = common.getListOfDisplayNamesForProtoOrClass([elem.text for elem in lokiBonusUnitSpawning.findall("excludedtarget")])
    lokiSpawnerList = common.getListOfDisplayNamesForProtoOrClass([elem.attrib.get('unit', elem.attrib.get('type')) for elem in lokiBonusUnitSpawning.findall("contributor")])
    lokiMythSpawnNew = f"\n{icon.BULLET_POINT} {common.commaSeparatedList(lokiSpawnerList)} work towards summoning Myth Units while damaging enemy objects, except {common.commaSeparatedList(lokiExcludedTargets)}. This ability activates when reaching the Classical Age."
    lokiMythSpawnNew += f"\n {icon.BULLET_POINT_ALT} Picks a random Age up to your current Age (excluding Archaic) at equal odds. Then, picks a random Norse Myth unit that is trained from the Temple at equal odds, including from Norse minor gods not accessible to Loki."
    lokiMythSpawnNew += f"\n {icon.BULLET_POINT_ALT} The damage required to spawn this unit is the 2x (the sum of its resource costs, with Favor multiplied by 10)."
    lokiSpawnerList.remove("Hersir")
    lokiMythSpawnNew += f"\n {icon.BULLET_POINT_ALT} Hersir contribute their full damage dealt to the count. {common.commaSeparatedList(lokiSpawnerList)} only contribute a fifth of their damage."
    lokiMythSpawnNew += f"\n {icon.BULLET_POINT_ALT} Once the accumulated damage total is reached, the chosen Myth unit spawns next to the final unit to contribute damage, regardless of population availability, and this process repeats."
    lokiContent = re.sub("\n.*Damaging enemy.*", "", lokiContent)
    # Put this at the end. It's otherwise quite hard to tell where the subbullets start and end
    lokiContent += lokiMythSpawnNew
    globals.stringMap["STR_CIV_LOKI_LR"] = lokiContent

    kronosContent = globals.dataCollection['string_table.txt']["STR_CIV_KRONOS_LR"]
    kronosContent = re.sub("to new locations [(](.*)[)]", "to new locations. Time shifting takes half the time it would take 1 Citizen to build the building. \\1", kronosContent)
    globals.stringMap["STR_CIV_KRONOS_LR"] = kronosContent
    globals.stringMap["STR_PUC_UNBUILD"] = "Time shift this building. This takes half the time that 1 Citizen needs to build it." # Default: "Time shift this building."

    gaiaContent = globals.dataCollection['string_table.txt']["STR_CIV_GAIA_LR"]
    terrainCreep = globals.dataCollection['major_gods.xml'].find("civ[name='Gaia']/terraincreeps/terraincreep")
    healEffect = globals.dataCollection['terrain_unit_effects.xml'].find("terrainuniteffect[@name='GaiaCreepHealEffect']/effect")
    gaiaLushNew = f"grow up to a {float(terrainCreep.attrib['maxradius']):0.3g}m circle of Lush at {float(terrainCreep.attrib['growthrate']):0.3g}m per second. Your objects on Lush heal {float(healEffect.attrib['amount']):0.3g} per second."
    gaiaContent = re.sub("grow Lush.", gaiaLushNew, gaiaContent)
    gaiaContent = re.sub("\n.*Lush heals.*", "", gaiaContent)
    globals.stringMap["STR_CIV_GAIA_LR"] = gaiaContent

    fuxiContent = globals.dataCollection["string_table.txt"]["STR_CIV_FUXI_LR"]
    fuxiContent = re.sub("Buildings research (.*?)% faster", "Buildings research \\1% faster (except Age advancements)", fuxiContent)
    globals.stringMap["STR_CIV_FUXI_LR"] = fuxiContent

    yinyang = common.findGodPowerByName("YinAndYang")
    yinyangEffects = []
    yinyangTitles = ("Yin", "Yang")
    for effects in yinyang.findall("effects"):
        strid = effects.find("rolloverid").text
        responses = [godpower.getTechEffectHandlerResponseForGodPowerEffect(yinyang, elem) for elem in effects.findall("effect")]
        tech.combineHandlerResponses(responses)
        responses = [item.toString() for item in responses if item is not None]
        responses = common.attemptAllWordwiseTextMerges(responses)
        effectsText = "\\n".join(responses)
        globals.stringMap[strid] = effectsText
        yinyangEffects.append(effectsText)
    yinyangInterval = common.findAndFetchText(yinyang, "interval", 1.0, float)

    yinyangTechtree = f"Swaps between two sets of bonuses every {yinyangInterval/60:0.3g} minutes. Every game begins in Yin."
    for index, title in enumerate(yinyangTitles):
        yinyangTechtree += f"\\n{title}: {yinyangEffects[index]}"
    # The Chinese god blessing fake powers all have this typo
    globals.stringMap[common.findGodPowerByName("YinAndYangTechree").find("rolloverid").text] = yinyangTechtree

    nuwaContent = globals.dataCollection["string_table.txt"]["STR_CIV_NUWA_LR"]
    nuwaAutobuildRate = 1.0 - float(common.techFromName("ArchaicAgeNuwa").find("effects/effect[@modifytype='AutoBuildRate']").attrib['amount'])
    nuwaContent = re.sub(f"Foundations automatically construct", f"Foundations (except Walls and Farms) automatically construct (at {nuwaAutobuildRate:0.3g} points/second)", nuwaContent)
    if "terracotta" not in nuwaContent.lower():
        # This bonus is currently missing
        nuwaTerracottaEffect = common.techFromName("ArchaicAgeNuwa").find("effects/effect[@subtype='UnitRegenRate']")
        if nuwaTerracottaEffect is not None:
            amount = float(nuwaTerracottaEffect.attrib['amount'])
            baseAmount = -1.0*float(common.protoFromName("TerracottaRider").find("unitregen").text)
            if nuwaTerracottaEffect.attrib['relativity'] != "BasePercent":
                raise ValueError("Nuwa terracotta bonus relativity not supported")
            reduction = (1.0-amount) * baseAmount
            nuwaContent += f"\\n{icon.BULLET_POINT} Terracotta Rider: Health loss slowed by {reduction}/second."
    globals.stringMap["STR_CIV_NUWA_LR"] = nuwaContent

    # "ShieldBlessing" = Creator's Auspice
    shieldblessing = common.findGodPowerByName("ShieldBlessing")
    shieldblessingTiers = shieldblessing.findall("effects")
    shieldblessingEntries = []
    for tier in shieldblessingTiers:
        req = tier.find("resourcetierreq")
        if req is None:
            requirement = "Initial: "
        else:
            requirement = f"After {icon.resourceIcon(req.attrib['type'])} {float(req.text):0.3g} total gathered: "
        responses = [godpower.getTechEffectHandlerResponseForGodPowerEffect(shieldblessing, elem) for elem in tier.findall("effect")]
        tech.combineHandlerResponses(responses)
        responses = [item.toString() for item in responses if item is not None]
        responses = common.attemptAllWordwiseTextMerges(responses)
        effectsText = requirement + (" ".join(responses))
        shieldblessingEntries.append(effectsText)
    shieldblessingTechtree = f"Grants scaling bonuses as you earn Favor. Higher tier bonuses replace lower ones.\\n"
    shieldblessingTechtree += "\\n".join(shieldblessingEntries)
    globals.stringMap[common.findGodPowerByName("ShieldBlessingTechree").find("rolloverid").text] = shieldblessingTechtree

    shennongContent = globals.dataCollection["string_table.txt"]["STR_CIV_SHENNONG_LR"]
    shennongFixedLandHealTargetElems = common.techFromName("ArchaicAgeShennong").findall("effects/effect[@subtype='BuildingChainEffect'][@modifytype='HealRate']")
    shennongFixedLandHealTargets = common.getDisplayNameForProtoOrClassPlural([elem.attrib['unittype'] for elem in shennongFixedLandHealTargetElems])
    shennongContent = shennongContent.replace("Myth units recover", shennongFixedLandHealTargets + " recover")
    globals.stringMap["STR_CIV_SHENNONG_LR"] = shennongContent

    shennongspawning = globals.dataCollection["major_gods.xml"].find("civ[name='Shennong']/bonusunitspawning/resourcegoal")
    shennongspawningAge = "current" if getattr(shennongspawning.find("nextageonly"), "text", "") != "true" else "next"
    shennongMythPool = ["QiongQi", "QiLin", "YaZi", "TaoWu", "TaoTie", "BaiHu", "ZhuQue", "HunDun", "QingLong"]
    shennongCosts = shennongspawning.findall("rewardpointcost")
    shennongContribution = float(shennongspawning.find("contributor").text)
    shennongCostLists = {}
    shennongResourceMults = {}
    for cost in shennongCosts:
        proportion = float(cost.text) / shennongContribution
        if proportion not in shennongCostLists:
            shennongCostLists[proportion] = []
        shennongCostLists[proportion].append(icon.resourceIcon(cost.attrib['resourcetype']))
        shennongResourceMults[cost.attrib['resourcetype']] = proportion
    shennongCostText = ', '.join([f"{key*100:0.3g}% of {' '.join(icons)}" for key, icons in shennongCostLists.items()])
    shennongspawningText = f"Spawns random Myth Units from the {shennongspawningAge} age at your Temple as you gather Favor. The amount of Favor needed depends on the chosen unit's cost: {shennongCostText}."
    for myth in shennongMythPool:
        proto = common.protoFromName(myth)
        cost = 0.0
        for elem in proto.findall("cost"):
            cost += shennongResourceMults.get(elem.attrib['resourcetype'], 0.0) * float(elem.text)
        shennongspawningText += f"\\n{common.getDisplayNameForProtoOrClass(proto)}: {icon.resourceIcon('favor')} {cost:0.3g}"
    globals.stringMap[common.findGodPowerByName("SpawnRewardTechree").find("rolloverid").text] = shennongspawningText