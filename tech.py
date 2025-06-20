import globals
import common
from xml.etree import ElementTree as ET
from typing import List, Dict, Union, Callable, Any
import dataclasses
import action
import icon
import unitdescription
import copy

VANILLA_FULL_TOOLTIP_EFFECT_COLOUR = lambda s: "<color=0.65,0.65,0.65>" + s + "</color>"

dataSubtypes = set()

# The way to go here is probably to do a once-over to work out the things we want to say about all the effects
# And then have handling to try to group up similar statements about different effects
# This means we need to track all the things that might be combined in different ways

# The things we might want to do are:
# "X and Y: increases damage by..."
# "X and Y: reduces food and gold cost by..."

@dataclasses.dataclass
class EffectHandlerResponse:
    # For when a tech effect doesn't affect some object types (eg Thurisaz rune regen on titans), we can list what isn't affected
    #doesntAffect: List[str] = dataclasses.field(default_factory=list)

    # A list of objects affected by the effect. It's probably just 1 item, but in some cases I might want to expand abstract types to raw proto lists
    # This gets used to make the "X and Y: ..." combinations if the rest of the effect matches
    affects: Union[str, List[str]] = dataclasses.field(default_factory=list)

    # Text for the tooltip. If combinableTargets is not None, responses with identical text fields can be combined.
    # The token {combinable} is replaced with the final list of combinables.
    text: str = "{combinable}"
    
    # These are targets that can get combined if everything else is the same, eg "food" "gold" in the above
    combinableTargets: Union[List[str], str, None] = None

    def canCombineAffects(self, other):
        if self.text == other.text and self.combinableTargets == other.combinableTargets:
            return True
        return False
    
    def canCombineTargets(self, other):
        if self.combinableTargets is None or other.combinableTargets is None:
            return False
        if self.text == other.text and self.affects == other.affects:
            return True
        return False
    
    def combineAffects(self, other):
        if not isinstance(self.affects, list):
            self.affects = [self.affects]
        if not isinstance(other.affects, list):
            self.affects.append(other.affects)
        else:
            self.affects += other.affects

    def combineTargets(self, other):
        if not isinstance(self.combinableTargets, list):
            self.combinableTargets = [self.combinableTargets]
        if not isinstance(other.combinableTargets, list):
            self.combinableTargets.append(other.combinableTargets)
        else:
            self.combinableTargets += other.combinableTargets
    
    def toString(self, skipAffectedObjects=False):
        components = []
        if not skipAffectedObjects:
            if isinstance(self.affects, list):
                # Remove duplicates while preserving order
                self.affects = list(dict.fromkeys(self.affects))
                components.append(common.commaSeparatedList(self.affects))
            else:
                components.append(self.affects)
            components[-1] += ":"
        combinables = self.combinableTargets
        if isinstance(self.combinableTargets, list):
            self.combinableTargets = list(dict.fromkeys(self.combinableTargets))
            combinables = common.commaSeparatedList(self.combinableTargets)
        components.append(self.text.format(combinable=combinables).replace(" :", ":"))
        components = [component.strip() for component in components if len(component.strip()) > 0]
        text = f"{' '.join(components)}"
        if text[-1] != ".":
            text += "."
        return text
        
def combineHandlerResponses(responses: List[EffectHandlerResponse]):
    for attempt in ("affects", "targets"):
        if attempt == "affects":
            test = EffectHandlerResponse.canCombineAffects
            merge = EffectHandlerResponse.combineAffects
        else:
            test = EffectHandlerResponse.canCombineTargets
            merge = EffectHandlerResponse.combineTargets
        while True:
            doneMerge = False
            for index, response in enumerate(responses):
                for otherIndex in range(index+1, len(responses)):
                    other = responses[otherIndex]
                    if test(response, other):
                        merge(response, other)
                        responses.pop(otherIndex)
                        doneMerge = True
                        break
                if doneMerge:
                    break
                        
            if not doneMerge:
                break



def shouldSuppressDataEffect(tech: ET.Element, effect: ET.Element):
    effectType = effect.attrib['type'].lower()
    techName = tech.attrib['name']
    subType = effect.attrib.get("subtype")
    if subType is not None:
        subType = subType.lower()
    # LogicalTypeUnitIsConstructed - for ox carts under construction
    # Because they are technically buildings things that affect building hp have to subtract the same amount from the ox cart under construction
    # This is not a detail there is any point in exposing
    targetTexts = [node.text for node in effect.findall("target")]
    if effectType == "data" and subType == "hitpoints" and "LogicalTypeUnitIsConstructed" in targetTexts:
        return True    
    return False
    

def getEffectTargets(tech: ET.Element, effect: ET.Element) -> List[str]:
    targets = []
    nodes = effect.findall("target")
    for node in nodes:
        nodeType = node.attrib["type"].lower()
        if nodeType == "protounit":
            targets += common.getListOfDisplayNamesForProtoOrClass(node.text)
        elif nodeType == "tech":
            tech = globals.dataCollection["techtree.xml"].find(f"tech[@name='{node.text}']")
            targets.append(common.getObjectDisplayName(tech))
        elif nodeType == "player":
            targets.append("Player")
        elif nodeType == "techall":
            targets.append("All Techs")
        elif nodeType == "techtype" and node.text == "HeroCavalry":
            targets.append("Cavalry Hero Promotion")
        elif nodeType == "techtype" and node.text == "HeroPromotion":
            targets.append("Hero Promotion")
        elif nodeType == "techtype" and node.text == "HeroInfantry":
            targets.append("Infantry Hero Promotion")
        elif nodeType == "techtype" and node.text == "TrainingYard":
            targets.append("Training Yard")
        elif nodeType == "techtype" and node.text == "MilitaryCampSocket":
            targets.append("Military Camp Addons")
        elif nodeType == "techwithflag" and node.text == "AgeUpgrade":
            targets.append("Age Upgrades")
        else:
            raise ValueError(f"{tech.attrib['name']}: unhandled effect target type {nodeType}")
    return targets

def resolveActionModificationOnAbstractToTargetList(target: str, actionName: str, actionFilter: Callable[[ET.Element, ET.Element], bool] = lambda actionElem, tactics: True) -> List[ET.Element]:
    "Return a list of protounits affected by trying to modify action of target, even if target is an abstract type"
    proto = common.protoFromName(target)
    protos = []
    if proto is None:
        # Is an abstract type
        possibleProtos = globals.protosByUnitType.get(target, [])
        for possibleProtoName in possibleProtos:
            proto = common.protoFromName(possibleProtoName)
            actionElem = action.findActionByName(proto, actionName)
            if actionElem is not None:
                tactics = action.actionTactics(proto, actionElem)
                if actionFilter(actionElem, tactics):
                    #print(f"{proto.attrib['name']} seems affected by modifying {target} action {actionName}")
                    protos.append(proto)
                else:
                    #print(f"{proto.attrib['name']} not affected by modifying {target} action {actionName}")
                    pass
    else:
        protos = [proto]
    return protos

def relativityModifiedValue(effect: ET.Element, attrib: str):
    # 1.1 -> 10%
    # 0.9 -> -10%
    # etc
    rawValue = float(effect.attrib[attrib])
    relativity = effect.attrib["relativity"].lower()
    if relativity in ("percent", "basepercent"):
        rawValue = 100*(rawValue - 1.0)
    return rawValue

def relativityModifierArmor(effect: ET.Element, attrib: str):
    # -0.15 -> -15%
    rawValue = float(effect.attrib[attrib])
    relativity = effect.attrib["relativity"].lower()
    if relativity != "percent":
        raise ValueError(f"Unsupported armor modification relativity {relativity}")
    #rawValue = 100*(1+rawValue)
    rawValue = 100*rawValue
    return rawValue

def formatTechAmountWithRelativity(tech: ET.Element, effect: ET.Element, percentRelativityModifier=relativityModifiedValue, flatSuffix="", percentileSuffix="%", valueFormat: Callable[[Any], str]="{:0.3g}".format,
                                   amountModifier: Callable[[ET.Element, ET.Element], float]=lambda tech, effect: float(effect.attrib['amount'])) -> str:
    relativity = effect.attrib.get("relativity", "absolute").lower()
    amount = amountModifier(tech, effect)
    
    postValueText = ""
    preValueText = ""
    prefixes = ""
    suffixes = ""

    if relativity == "assign":
        preValueText = "set to"
    elif relativity == "absolute":
        prefixes += "+" if amount > 0.0 else "-"
        suffixes += flatSuffix
    elif relativity in ("percent", "basepercent"):
        amount = percentRelativityModifier(effect, 'amount')
        prefixes = "+" if amount > 0.0 else "-"
        suffixes += percentileSuffix
        if relativity == "percent":
            postValueText = "of current"
        else:
            postValueText = "of base"
    elif relativity == "override":
        preValueText = "sets base value to"
    else:
        raise ValueError(f"{tech.attrib['name']}: unknown relativity {relativity}")
    
    valueText = valueFormat(abs(amount))

    components = [preValueText, prefixes + valueText + suffixes, postValueText]
    components = [component.strip() for component in components if len(component.strip()) > 0]
    modifiedValueText = " ".join(components)
    return modifiedValueText

def dataSubtypeResourceReturnHandler(tech: ET.Element, effect:ET.Element):
    resource = effect.attrib.get("resource", "")
    resourceText = icon.resourceIcon(resource) + f" {float(effect.attrib['amount']):0.3g}"

    return dataSubtypeWithAmountHelper("Resources returned on death {value}: {combinable}", combinableString=resourceText, valueFormat="".format)(tech, effect)

def dataSubtypeResourceReturnRateHandler(tech: ET.Element, effect:ET.Element):
    resource = effect.attrib.get("resource", "")
    resourceText = icon.resourceIcon(resource) + f" {100*float(effect.attrib['amount']):0.3g}%"

    return dataSubtypeWithAmountHelper("Cost refunded on death: {combinable}", combinableString=resourceText, valueFormat="".format)(tech, effect)


def dataSubtypeOnHitEffectHandler(tech: ET.Element, effect:ET.Element):
    effectType = effect.attrib.get("effecttype", "").lower()
    duration = float(effect.attrib.get("duration", "0.0"))

    targetTypeString = "targets"
    if "targettype" in effect.attrib:
        targetTypeString = common.commaSeparatedList(common.getListOfDisplayNamesForProtoOrClass(effect.attrib["targettype"], True))
    
    if effectType in ("attach"):
        # Attaches that actually do things (Sun Ray) need adding manually
        return None
    if effectType == "lifesteal":
        preTargetText = "Lifesteal"
        preTargetText += f" from {targetTypeString}"
        if effect.attrib.get("action") is not None:
            preTargetText += " with"
        return dataSubtypeWithAmountHelper(preTargetText + "{combinable} {value}", combinableAttribute="action", valueFormat="{:0.0%}".format)(tech, effect)
    elif effectType == "snare":
        preTargetText = f"Movement Speed of {targetTypeString} hit"
        if effect.attrib.get("action") is not None:
            preTargetText += " with"
        return dataSubtypeWithAmountHelper(preTargetText + " {actionof}{combinable}: {value} for " + f"{duration:0.3g}s", combinableAttribute="action", valueFormat="{:0.0%}".format)(tech, effect)
    elif effectType == "damageovertime":
        damageType = effect.attrib.get("damagetype", "Divine")
        preTargetText = "Hits"
        if effect.attrib.get("action") is not None:
            preTargetText += " with"
        preTargetText += " {combinable} "
        totalDamage = float(effect.attrib['amount'])*duration
        if targetTypeString != "targets":
            preTargetText += f"against {targetTypeString} "
        preTargetText += f"inflict {icon.damageTypeIcon(damageType)} {totalDamage:0.3g} over {duration:0.3g} seconds"
        return dataSubtypeWithAmountHelper(preTargetText, combinableAttribute="action")(tech, effect)
    else:
        print(f"Warning: {tech.attrib['name']}: unknown OnHitEffect {effectType}")

def dataSubtypeDamageHandler(tech: ET.Element, effect:ET.Element):
    damageType = effect.attrib.get("damagetype", None)
    if damageType is None:
        return dataSubtypeWithAmountHelper("Damage {actionof}{combinable}: {value}", combinableAttribute="action")(tech, effect)
    return dataSubtypeWithAmountHelper(damageType + " Damage {actionof}{combinable}: {value}", combinableAttribute="action")(tech, effect)


def dataSubtypeOnHitEffectRateHandler(tech: ET.Element, effect:ET.Element):
    effectType = effect.attrib.get("effecttype", "")
    if effectType == "Lifesteal":
        # I don't really know why the Tyrfing relic uses OnHitEffectRate for this
        return dataSubtypeOnHitEffectHandler(tech, effect)
    elif effectType == "DamageOverTime":
        # This may have target type issues down the line
        return dataSubtypeWithAmountHelper("Damage over Time {actionof}{combinable}: {value}", combinableAttribute="action")(tech, effect)
    else:
        print(f"Warning: {tech.attrib['name']} has OnHitEffectRate with unhandled effecttype {effectType}")
        return None

def dataSubtypeActionEnableHandler(tech: ET.Element, effect:ET.Element):
    actionName = effect.attrib.get("action")
    targetTypes = effect.findall("target[@type='ProtoUnit']")
    targetProtoUnits = [proto.text for proto in targetTypes if proto.text not in globals.abstractTypes]
    targetAbstractTypes = [abstract.text for abstract in targetTypes if abstract.text in globals.abstractTypes]
    for abstract in targetAbstractTypes:
        targetProtoUnits += globals.protosByUnitType[abstract]

    responses = []
    for targetType in targetProtoUnits:
        proto = common.protoFromName(targetType)
        actionNode = action.findActionByName(proto, actionName)
        tactics = action.actionTactics(proto, actionNode)
        if actionNode is None:
            #print(f"{tech.attrib['name']} trying to enable action {actionName} on {targetType}, no corresponding action found")
            continue
        actionDescription = action.describeAction(proto, actionNode, action.actionGetChargeType(actionNode, tactics), tech=tech, nameOverride="")
        if len(actionDescription) == 0:
            #print(f"{tech.attrib['name']} enabling {actionName} on {targetType}: describeAction says it doesn't do anything, but that might be okay")
            continue
        isEnabling = bool(int(float(effect.attrib.get("amount"))))

        components = ["Enables" if isEnabling else "Disables", action.getActionName(proto, actionNode, nameNonChargeActions=True) + ":", actionDescription]
        text = " ".join(components)

        responses.append(EffectHandlerResponse(affects=common.getDisplayNameForProtoOrClass(targetType), text=text))
    
    return responses

def dataSubtypeSetUnitTypeHandler(tech: ET.Element, effect:ET.Element):
    unittype = effect.attrib["unittype"]
    if unittype == "LogicalTypeBuildingsThatShoot":
        # Technically this will increase the favor production from hitting towers
        # But I don't think that's worth mentioning here
        return None
    elif unittype == "LogicalTypeValidBoltTarget":
        return EffectHandlerResponse(affects=getEffectTargets(tech, effect), text="Becomes targetable by Bolt")
    elif unittype == "WoodDropsite":
        return EffectHandlerResponse(affects=getEffectTargets(tech, effect), text="Becomes dropsite for Wood")
    elif unittype == "Dropsite":
        # Knowing something becomes a generic dropsite is not going to be useful to people
        return None
    else:
        print(f"Warning: {tech.attrib['name']} using SetUnitType with unhandled flag {unittype}")
    return None

def dataSubtypeMarketHandler(tech: ET.Element, effect:ET.Element):
    component = effect.attrib['component']
    kwargs = {}
    valueFormat = lambda amt: f"{amt:0.1%}"
    if component == "BuyFactor":
        buySell = "Buy"
    elif component == "SellFactor":
        buySell = "Sell"
        # Not doing this makes the penalty sound like it's getting bigger.
        kwargs["amountModifier"] = lambda tech, effect: -1*float(effect.attrib['amount'])
    else:
        print(f"Warning: {tech.attrib['name']} with unknown component {component}")
    return dataSubtypeWithAmountHelper("{combinable} Penalty: {value} ", combinableString=buySell, valueFormat=valueFormat, **kwargs)(tech, effect)

def dataSubtypeTributePenaltyHandler(tech: ET.Element, effect:ET.Element):
    realTributePenalty = globals.dataCollection["game.cfg"]["tributePenalty"]
    if effect.attrib["relativity"].lower() == "absolute":
        amount = float(effect.attrib["amount"])
        newValue = realTributePenalty+amount

        return dataSubtypeWithAmountHelper(f"Tribute Penalty: reduced to {newValue:0.0%}", combinableString="")(tech, effect)
    return dataSubtypeWithAmountHelper(combinableString="Tribute Penalty")(tech, effect)

def dataSubypeOnDamageModifyHandler(tech: ET.Element, effect:ET.Element):
    if effect.attrib["relativity"].lower() not in ("assign", "absolute"):
        print(f"Warning: {tech.attrib['name']} using unknown relativity {effect.attrib['relativity']} for OnDamageModify, ignored as actual function needs investigating")
        return None
    modifyType = effect.attrib["modifytype"]
    amount = float(effect.attrib['amount'])
    if modifyType == "ROF":
        modifyType = "Attack Interval"
    elif modifyType == "Speed":
        modifyType = "Movement Speed"
    elif modifyType == "ArmorSpecific":
        modifyType = f"{effect.attrib['damagetype']} vulnerability"
        amount *= -1

    text = ("Increases" if amount > 0.0 else "Decreases") + " {combinable}" + f" by {abs(100*amount):0.3g}% per 1% hitpoints lost"
    return EffectHandlerResponse(affects=getEffectTargets(tech, effect), text=text, combinableTargets=modifyType)

def dataSubtypeWorkrateHandler(tech: ET.Element, effect:ET.Element):
    action = effect.attrib['action']
    additionalPostTargetText = ""
    if action == "BurstHeal":
        preTargetText = f"Burst Heal strength for"
    elif action == "Autogather":
        preTargetText = "Trickle rate for"
        additionalPostTargetText = "per second"
    elif action in ("AutoGatherFood", "AutoGatherWood", "AutoGatherGold"):
        preTargetText = "Accumulation rate for"
        additionalPostTargetText = "per second"
    elif action == "AutoGatherFavor":
        preTargetText = "Base (non-LOS dependent) gather rate for"
    elif action == "JumpAttack":
        # This appears to do nothing?
        return None
    else:
        preTargetText = f"{action} rate for"
    return dataSubtypeWithAmountHelper(preTargetText + " {combinable}: {value} " + additionalPostTargetText, combinableAttribute="unittype", combinableAttributeFormat=common.getDisplayNameForProtoOrClass)(tech, effect)

def dataSubtypeWorkrateSpecificHandler(tech: ET.Element, effect:ET.Element):
    action = effect.attrib['action']
    additionalPostTargetText = ""
    if action == "Gather":
        preTargetText = f"{effect.attrib['resource']} gather rate from"
    else:
        print(f"Warning: Unknown WorkrateSpecific targeting action {action}, ignored")
        return None
    targetName = common.getDisplayNameForProtoOrClass(effect.attrib["unittype"])
    return dataSubtypeWithAmountHelper(preTargetText + " {combinable}: {value} " + additionalPostTargetText, combinableAttribute="unittype", combinableAttributeFormat=common.getDisplayNameForProtoOrClass)(tech, effect)


def dataSubtypeObstructionSizeHandler(tech: ET.Element, effect:ET.Element):
    # Look for matching nodes of the opposite X/Z type because it would be nice to combine them
    targets = [x.text for x in effect.findall("target[@type='ProtoUnit']")]
    myType = effect.attrib['subtype']
    other = "ObstructionRadius" + ("X" if myType.endswith("Z") else "Z")
    otherTypeNodes = tech.findall(f"effects/effect[@subtype='{other}']")
    correspondingOther = None
    for otherNode in otherTypeNodes:
        if [x.text for x in otherNode.findall("target[@type='ProtoUnit']")] == targets and otherNode.attrib["amount"] == effect.attrib["amount"]:
            correspondingOther = otherNode
            break

    if correspondingOther is not None:
        if myType == "ObstructionRadiusZ":
            return None
        return dataSubtypeWithAmountHelper(combinableString="Collison Size", flatSuffix="m")(tech, effect)
    else:
        return dataSubtypeWithAmountHelper(combinableString="Collison Size " + myType[-1], flatSuffix="m")(tech, effect)    
    
def dataSubtypeEnableHandler(tech: ET.Element, effect:ET.Element):
    if "system" in effect.attrib:
        # These are much too complicated to do automatically and need manual help
        return None
    return EffectHandlerResponse(getEffectTargets(tech, effect), "Enabled if Age locked")

def dataSubtypeVeterancyEnableHandler(tech: ET.Element, effect:ET.Element):
    return [EffectHandlerResponse(getEffectTargets(tech, effect), '\\n'.join(unitdescription.veterancyText(targetNode.text, ignoreExperienceUnitFlag=True, multiline=True))) for targetNode in effect.findall("target[@type='ProtoUnit']")]

def dataSubtypeBountyResourceEarningRewardHandler(tech: ET.Element, effect:ET.Element):
    # It's just like favor, except it doesn't fall off with amount gained
    # so it's just 1 per 8 damage dealt...
    loki = globals.dataCollection['major_gods.xml'].find("civ[name='Loki']")
    goal = float(loki.find("bountyresourceearning/bountydamagegoal").text)
    goal /= float(effect.attrib["amount"])
    resourceType = effect.attrib['resourcetype']
    excludeTypes = common.getListOfDisplayNamesForProtoOrClass([element.attrib['unittype'] for element in loki.findall("bountyresourceearning/bountytargetmultiplier") if resourceType != element.attrib["resourcetype"]], plural=True) 
    return EffectHandlerResponse(common.getDisplayNameForProtoOrClass(effect.attrib['unittype']), f"Generates 1 {resourceType} per {goal:0.3g} damage inflicted on targets except {common.commaSeparatedList(excludeTypes)}.")

def dataSubtypeOnHitEffectActiveHandler(tech: ET.Element, effect:ET.Element):
    # Check effects to see if this effect is the first OnHitEffectiveActive in the list
    targetTypes = effect.findall("target[@type='ProtoUnit']")
    effectName = effect.attrib['effecttype']
    actionFilter = lambda actionElem, tactics: actionElem.find(f"onhiteffect[@type='{effectName}'][@active='0']")
    responses = []
    for targetElement in targetTypes:
        target = targetElement.text
        isAbstractType = common.protoFromName(target) is None
        protos = resolveActionModificationOnAbstractToTargetList(target, effect.attrib['action'], actionFilter)
        for proto in protos:
            actionElement = action.findActionByName(proto, effect.attrib['action'])
            #responses.append(EffectHandlerResponse(unwrapAbstractClass(target), "Modifies action {combinable}:" + f" {action.actionOnHitNonDoTEffects(proto, actionElement, True)}"))
            actionName = action.getActionName(proto, actionElement, nameNonChargeActions=True)
            if effectName == "DamageOverTime":
                modifyDetails = action.actionDamageOverTime(proto, actionElement, ignoreActive=True)
                if modifyDetails != "":
                    modifyDetails = f"Inflicts an additional {modifyDetails}"
            else:
                modifyDetails = action.actionOnHitNonDoTEffects(proto, actionElement, True, [effectName])
               
            #print(f"Details for {tech.attrib['name']} -> {proto.attrib['name']} effecttype {effectName} action {effect.attrib['action']} -> {modifyDetails}")
            if modifyDetails == "":
                continue
            if "targettype" in effect.attrib:
                if isAbstractType:
                    responses.append(EffectHandlerResponse(common.getObjectDisplayName(proto), f"Modifies {actionName} against " + "{combinable}:" + f" {modifyDetails}", effect.attrib['targettype']))
                else:
                    responses.append(dataSubtypeWithAmountHelper(f"Modifies {actionName}" + " against {combinable}:" + f" {modifyDetails}", combinableAttribute="targettype", combinableAttributeFormat=common.getDisplayNameForProtoOrClassPlural)(tech, effect))
            else:
                if isAbstractType:
                    responses.append(EffectHandlerResponse(common.getObjectDisplayName(proto), "Modifies {combinable}:" + f" {modifyDetails}", actionName))
                else:
                    responses.append(dataSubtypeWithAmountHelper("Modifies {combinable}:" + f" {modifyDetails}", combinableAttribute="action")(tech, effect))
    return responses


def dataSubtypeChargedModifyAdjustHandler(tech: ET.Element, effect:ET.Element):
    targetTypes = effect.findall("target[@type='ProtoUnit']")
    responses = []
    for targetElement in targetTypes:
        target = targetElement.text
        proto = common.protoFromName(target)
        actionElem = action.findActionByName(proto, effect.attrib['action'])
        actionName = action.getActionName(proto, actionElem, nameNonChargeActions=True)
        responses.append(dataSubtypeWithAmountHelper(f"Modifies {actionName}: increases {'{combinable}'} modification:" + " {value}", combinableAttribute='modifytype')(tech, effect))
    return responses

def dataSubtypeMinWorkRateHandler(tech: ET.Element, effect:ET.Element):
    targetTypes = effect.findall("target[@type='ProtoUnit']")
    responses = []
    for targetElement in targetTypes:
        target = targetElement.text
        proto = common.protoFromName(target)
        actionElem = action.findActionByName(proto, effect.attrib['action'])
        actionName = action.getActionName(proto, actionElem, nameNonChargeActions=True)
        if actionName != "Trade":
            print(f"Warning: {tech.attrib['name']} uses MinWorkRate on non-trade action, test how this works")
            continue
        responses.append(dataSubtypeWithAmountHelper("Trade Profit also generated as {combinable}: {value}", combinableAttribute='unittype', valueFormat=lambda val: f"{val*100:0.3g}%")(tech, effect))
    
    if len(responses) == 0:
        return None
    return responses

def dataSubtypeProtoActionAddHandler(tech: ET.Element, effect:ET.Element):
    protoFrom = effect.attrib['unittype']
    protoElement = common.protoFromName(protoFrom)
    actionElement = action.findActionByName(protoElement, effect.attrib['protoaction'])
    targetTypes = effect.findall("target[@type='ProtoUnit']")
    responses = []
    for targetElement in targetTypes:
        target = targetElement.text
        responses.append(EffectHandlerResponse(common.getDisplayNameForProtoOrClass(target), f"{action.describeAction(protoElement, actionElement, tech=tech)}"))
    return responses

def dataSubtypeAssignOnHitEffectHandler(tech: ET.Element, effect:ET.Element):
    protoFrom = effect.attrib['srcproto']
    protoElement = common.protoFromName(protoFrom)
    actionElement = action.findActionByName(protoElement, effect.attrib['srcaction'])
    effectType = effect.attrib['effecttype']
    text = ""
    if effectType == "DamageOverTime":
        text = action.actionDamageOverTime(protoElement, actionElement)
    else:
        # We want to specifically only describe the effect that was asked for, not all of them
        text = action.actionOnHitNonDoTEffects(protoElement, actionElement, ignoreActive=True, filterOnHitTypes=[effectType])
    if text == "":
        return None
    return dataSubtypeWithAmountHelper(f"On hit: {text}", combinableAttribute="action")(tech, effect)

def dataSubtypePowerCostHandler(tech: ET.Element, effect:ET.Element):
    protoPower = effect.attrib['protopower']
    powerData = globals.dataCollection['god_powers_combined'].find(f"power[@name='{protoPower}']")
    displayName = common.getObjectDisplayName(powerData)
    return dataSubtypeWithAmountHelper("Recast Cost of {combinable}: {value}", combinableString=displayName)(tech, effect)

def dataSubtypePowerRofHandler(tech: ET.Element, effect:ET.Element):
    protoPower = effect.attrib['protopower']
    powerData = globals.dataCollection['god_powers_combined'].find(f"power[@name='{protoPower}']")
    displayName = common.getObjectDisplayName(powerData)
    return dataSubtypeWithAmountHelper("Recharge Time of {combinable}: {value}", combinableString=displayName)(tech, effect)

def dataSubtypeModifyRateHandler(tech: ET.Element, effect:ET.Element):
    targets = [x.text for x in effect.findall("target[@type='ProtoUnit']")]
    responses = []
    for target in targets:
        protos = resolveActionModificationOnAbstractToTargetList(target, effect.attrib['action'])
        for proto in protos:
            actionElement = action.findActionByName(proto, effect.attrib['action'])
            tactics = action.actionTactics(proto, actionElement)
            actionType = None
            actionModifyRate = None
            for source in actionElement, tactics:
                if actionType is None:
                    actionType = common.findAndFetchText(source, "modifytype", None)
                if actionModifyRate is None:
                    actionModifyRate = common.findAndFetchText(source, "modifyamount", None, float)
            if actionType is None:
                print(f"Warning: {tech.attrib['name']} using ModifyRate on an action we couldn't retrieve")
                continue
            if actionType == "HealRate":
                responses.append(dataSubtypeWithAmountHelper(combinableString="Area Damage Rate" if actionModifyRate < 0.0 else "Area Healing Rate")(tech, effect))
            else:
                print(f"Warning: {tech.attrib['name']} using ModifyRate on a {actionType}, no text defined to handle this case")
                continue
    return responses


def dataSubtypeModifySpawnHandler(tech: ET.Element, effect:ET.Element):
    spawnType = effect.attrib['spawntype']
    if spawnType == "Dead":
        preText = "On death,"
    elif spawnType == "HitGround":
        preText = "On hitting ground,"
    elif spawnType == "HitWater":
        preText = "On hitting water,"
    elif spawnType == "Build":
        preText = "When fully built,"
    elif spawnType == "SelfDestruct":
        preText = "On self destruct,"
    else:
        print(f"Warning: {tech.attrib['name']} using ModifySpawn with unknown spawntype {spawnType}, ignored")
        return None
    plus = "+" if effect.attrib["relativity"].lower() == "absolute" else ""
    spawnName = common.getDisplayNameForProtoOrClass(effect.attrib['proto'])
    amount = int(float(effect.attrib['amount']))
    spawnText = f" spawns {plus}{amount} {spawnName}"
    chance = float(effect.attrib.get("chance", 1.0))
    if chance < 1.0:
        spawnText = f" has a {chance:0.0%} chance to spawn {plus}{amount} {spawnName}"
    return EffectHandlerResponse(getEffectTargets(tech, effect), preText + spawnText)

def dataSubtypeProtoUnitFlagHandler(tech: ET.Element, effect:ET.Element):
    flag = effect.attrib['flag']
    if flag == "AreaDamageConstant":
        return EffectHandlerResponse(getEffectTargets(tech, effect), "Remove damage falloff with distance for area attacks")
    elif flag == "TradeAddAllyResources":
        # According to the data modding guide: the hardcoded 10% here is actually the modifyamount of the target's action.
        return EffectHandlerResponse(getEffectTargets(tech, effect), "When trading with an ally's Town Center: that ally also gains 10% of your trade Gold profit.")
    elif flag == "SelfRespawn":
        return EffectHandlerResponse(getEffectTargets(tech, effect), "On death, respawns in the same location 30s later. This happens only once per unit")
    elif flag in ("HideResourceInventory", "Deleteable", "DisplayRange"):
        return None
    else:
        print(f"Warning: {tech.attrib['name']} using ProtoUnitFlag with unknown flag {flag}, ignored")

def dataSubtypeActionAddAttachingUnitHandler(tech: ET.Element, effect:ET.Element):
    attachType = effect.attrib["unittype"]
    return dataSubtypeWithAmountHelper("On hit {actionof}{combinable}: Attaches " + f"{common.getDisplayNameForProtoOrClass(attachType)}", combinableAttribute="action")(tech, effect)

def dataSubtypeRechargeTimeHandler(tech: ET.Element, effect:ET.Element):
    # If this tech has a RechargeType effect we need to let that take over
    # Those techs enable actions and set the recharge time (which can change form from time) and the whole lot needs to be read together to make any sense
    rechargeType = tech.find("effects/effect[@subtype='RechargeType']")
    if rechargeType is not None:
        return None
    return dataSubtypeWithAmountHelper(combinableString="Special Attack Recharge Time")(tech, effect)

def dataSubtypeAuxRechargeTimeHandler(tech: ET.Element, effect:ET.Element):
    return dataSubtypeWithAmountHelper(combinableString="Secondary Special Attack Recharge Time")(tech, effect)

def dataSubtypeOnHitEffectDurationHandler(tech: ET.Element, effect:ET.Element):
    targetTypes = effect.findall("target[@type='ProtoUnit']")
    responses = []
    for targetElement in targetTypes:
        target = targetElement.text
        proto = common.protoFromName(target)
        actionElement = action.findActionByName(proto, effect.attrib['action'])
        actionName = action.getActionName(proto, actionElement, nameNonChargeActions=True)
        responses.append(dataSubtypeWithAmountHelper(f"Modifies {actionName} " + "against {combinable}: duration {value}", combinableAttribute="targettype", combinableAttributeFormat=common.getDisplayNameForProtoOrClassPlural, flatSuffix=" seconds")(tech, effect))
    return responses

def dataSubtypeEmpowerModifyHandler(tech: ET.Element, effect:ET.Element):
    modifyType = effect.attrib['modifytype']
    unitType = effect.attrib['unittype']
    targetsList = map(common.getDisplayNameForProtoOrClass, globals.protosByUnitType[unitType])
    responses = []

    if modifyType == "DoubleTrainChance":
        chance = float(effect.attrib['amount'])
        if chance < 1.0:
            chanceString = f"{chance:0.0%} chance to produce double units"
        else:
            chanceString = f"produces double units"
        responses += [dataSubtypeWithAmountHelper("While Empowering {combinable}: building" + f" {chanceString}", combinableString=unitType)(tech, effect) for unitType in targetsList]
    elif modifyType == "MilitaryTrainingRate":
        responses += [dataSubtypeWithAmountHelper("While Empowering {combinable}: building's military training rate {value}", combinableString=unitType)(tech, effect) for unitType in targetsList]
    else:
        print(f"Warning: {tech.attrib['name']} using unknown EmpowerModify {modifyType}, ignored")
        return None
    return responses

def dataSubtypeAddGoalHandler(tech: ET.Element, effect:ET.Element):
    goalType = effect.attrib["goaltype"]
    rewardtrackingType = effect.attrib["rewardtrackingtype"]
    quantity = float(effect.attrib['amount'])
    if goalType != "DeathCount":
        print(f"Warning: AddGoal with unknown goal type {goalType}, ignoring")
        return None
    contributors = [elem.attrib['contributorid'] for elem in tech.findall("effects/effect[@subtype='AddGoalContributor']")]
    contributorText = common.getDisplayNameForProtoOrClass(contributors)
    if rewardtrackingType == "Single":
        rewardTrackingText = f"For every {quantity:0.3g} {contributorText} that die,"
        spawnProto = tech.find("effects/effect[@subtype='AddGoalReward']").attrib["rewardtype"]
        outcomeText = f"spawns a {common.getDisplayNameForProtoOrClass(spawnProto)}"
    elif rewardtrackingType == "PerPossibleReward":
        rewardTrackingText = f"After {quantity:0.3g} of the same kind of {contributorText} have died,"
        outcomeText = "one spawns"
    else:
        print(f"Warning: AddGoal DeathCount with unknown rewardtrackingtype {rewardtrackingType}, ignoring")
        return None
    
    spawnLocationLand = tech.find("effects/effect[@subtype='SetGoalSpawnLocationLand']")
    spawnLocationWater = tech.find("effects/effect[@subtype='SetGoalSpawnLocationWater']")
    if spawnLocationLand is not None:
        spawnLocationLand = common.getDisplayNameForProtoOrClass(spawnLocationLand.attrib["locationprotoid"])
    if spawnLocationWater is not None:
        spawnLocationWater = common.getDisplayNameForProtoOrClass(spawnLocationWater.attrib["locationprotoid"])
    if spawnLocationLand is not None and spawnLocationWater is not None:
        spawnLocationText = f"from your {spawnLocationLand} (on land) or {spawnLocationWater} (on water)"
    elif spawnLocationLand is not None:
        spawnLocationText = f"from your {spawnLocationLand}"
    elif spawnLocationWater is not None:
        spawnLocationText = f"from your {spawnLocationWater}"
    else:
        print(f"Warning: AddGoal DeathCount didn't find a valid spawn location effect to read from")
        return None
    
    text = " ".join((rewardTrackingText, outcomeText, spawnLocationText)) + "."
    return EffectHandlerResponse(getEffectTargets(tech, effect), text, None)

def dataSubtypeDamageByCostHandler(tech: ET.Element, effect:ET.Element):
    amount = float(effect.attrib['amount'])
    return dataSubtypeWithAmountHelper(f"Damage {{actionof}}{{combinable}}: {{value}} per {icon.resourceIcon(effect.attrib['resource'])} 1 cost", combinableAttribute='action')(tech, effect)
    
def dataSubtypeBuildingChainResourceFactorHandler(tech: ET.Element, effect: ET.Element):
    return dataSubtypeWithAmountHelper(f"{{combinable}} gain from Favored Land: {{value}}", combinableAttribute="resource")(tech, effect)

def dataSubtypeBuildingChainEffectHandler(tech: ET.Element, effect:ET.Element):
    modifyType = effect.attrib['modifytype']
    unitType = effect.attrib['unittype']
    effectType = effect.attrib['effecttype']

    if effectType == "InRange":
        connectionText = "While on Favored Land: "
    elif effectType == "Connected":
        connectionText = "While connected to Favored Land: "
    else:
        print(f"Warning: {tech.attrib['name']} has BuildingChainEffect with unknown effecttype {effectType}")
        return None
    
    if modifyType == "RegenRate":
        effectText = "Regeneration Rate"
    elif modifyType == "ResearchRate":
        effectText = "Research Rate"
    elif modifyType == "CommandResearchCost":
        effectText = "Building Addon Cost"
    elif modifyType == "AutoBuildRate":
        effectText = "Self-build Rate"
    elif modifyType == "Speed":
        effectText = "Movement Speed"
    elif modifyType == "HealRate":
        effectText = "Heal Rate"
    elif modifyType == "DropsiteRate":
        effectText = "Bonus Resources on Dropoff"
    else:
        effectText = modifyType
        print(f"Warning: {tech.attrib['name']} has BuildingChainEffect with unknown modifytype {modifyType}")
    
    return EffectHandlerResponse(common.getDisplayNameForProtoOrClass(unitType), connectionText + "{combinable}: " + formatTechAmountWithRelativity(tech, effect), effectText)

def handleOnTechResearchedTech(tech: ET.Element, effect:ET.Element):
    if "techtype" not in effect.attrib:
        techNames = ["any technology"]
    else:
        techList = globals.dataCollection["techtree.xml"].findall(f"tech/techtype[.='{effect.attrib['techtype']}']/..")
        techNames = [common.getObjectDisplayName(techElem) for techElem in techList]
    text = f"<tth>Upon researching {common.commaSeparatedList(techNames)}:\\n"
    targetTech = common.techFromName(effect.text)
    text += processTech(targetTech)
    return EffectHandlerResponse(getEffectTargets(tech, effect), text)

def dataSubtypeWithAmountHelper(
                      textFormat: str = "{combinable}: {value}",
                      combinableString: Union[str, None]=None, 
                      combinableAttribute: Union[str, None]=None,
                      combinableAttributeFormat: Union[str, Callable[[str], Union[List[str], str]]] = "{}",
                      percentileSuffix="%", 
                      flatSuffix="",
                      valueFormat: Callable[[Any], str] = "{:0.3g}".format,
                      relativityModifier: Callable[[ET.Element, str], str]=relativityModifiedValue,
                      amountModifier: Callable[[ET.Element, ET.Element], float]=lambda tech, effect: float(effect.attrib.get('amount', 0.0))
                      ) -> Callable[[ET.Element, ET.Element], EffectHandlerResponse]:
    def inner(tech: ET.Element, effect:ET.Element):
        valueText = formatTechAmountWithRelativity(tech, effect, relativityModifier, flatSuffix, percentileSuffix, valueFormat, amountModifier)
        actionofReplacement = ""
        actionforReplacement = ""
        if combinableString is not None:
            combinableTarget = combinableString
        elif combinableAttribute is not None:
            if combinableAttribute == "action":
                if effect.attrib.get("allactions") is not None or "action" not in effect.attrib:
                    combinableTarget = ""
                else:
                    actionofReplacement = "of "
                    actionforReplacement = "for "
                    actionName = effect.attrib['action']
                    # If we can find an actual action name, do so
                    targetNodes = effect.findall("target[@type='ProtoUnit']")
                    targets = [x.text for x in targetNodes if x.text not in globals.abstractTypes]
                    if len(targets) == 1:
                        actionNode = action.findActionByName(targets[0], actionName)
                        actionNameFromProto = action.getActionName(targets[0], actionNode, nameNonChargeActions=True)
                        if action.actionGetChargeType(actionNode, action.actionTactics(targets[0], actionNode)) != action.ActionChargeType.NONE:
                            actionNameFromProto += " (special attack)"
                        if actionNameFromProto:
                            actionName = actionNameFromProto
                        
                    combinableTarget = action.ACTION_TYPE_NAMES.get(actionName, actionName)
            else:
                formatter = combinableAttributeFormat
                if not callable(formatter):
                    formatter = combinableAttributeFormat.format
                combinableTarget = formatter(effect.attrib[combinableAttribute])
        else:
            raise ValueError("dataSubtypeWithAmountHelper passed no combinable item!")
        return EffectHandlerResponse(getEffectTargets(tech, effect), textFormat.format(value=valueText, combinable="{combinable}", actionof=actionofReplacement, actionfor=actionforReplacement), combinableTargets=combinableTarget)
    return inner

def dataSubtypeIgnore(tech: ET.Element, effect:ET.Element):
    return None

DATA_SUBTYPE_HANDLERS: Dict[str, Callable[[ET.Element, ET.Element], Union[EffectHandlerResponse, List[EffectHandlerResponse]]]] = {
    "damagebonus":dataSubtypeWithAmountHelper(textFormat="Damage bonus against {combinable}: {value}", flatSuffix="x", combinableAttribute="unittype", combinableAttributeFormat=common.getDisplayNameForProtoOrClassPlural),
    "hitpoints":dataSubtypeWithAmountHelper(combinableString="Hitpoints"),
    "los":dataSubtypeWithAmountHelper(combinableString="LOS"),
    "maximumvelocity":dataSubtypeWithAmountHelper(combinableString="Movement Speed"),
    "trackrating":dataSubtypeWithAmountHelper("Track Rating {actionof}{combinable}: {value}", combinableAttribute="action"),
    "accuracy":dataSubtypeWithAmountHelper("Accuracy {actionof}{combinable}: {value}", combinableAttribute="action", valueFormat=lambda val: f"{val*100:0.3g}%"),
    "maximumrange":dataSubtypeWithAmountHelper("Max Range {actionof}{combinable}: {value}", combinableAttribute="action"),
    "armorvulnerability":dataSubtypeWithAmountHelper(textFormat="Damage Vulnerability to {combinable}: {value}", combinableAttribute="armortype", relativityModifier=relativityModifierArmor),
    "damage": dataSubtypeDamageHandler,
    "workrate":dataSubtypeWorkrateHandler,
    "workratespecific":dataSubtypeWorkrateSpecificHandler,
    "godpowercostfactor":dataSubtypeWithAmountHelper(combinableString="God Power recast cost"),
    "godpowerroffactor":dataSubtypeWithAmountHelper(combinableString="God Power recharge time"),
    "resourcereturn":dataSubtypeResourceReturnHandler,
    "resourcereturnrate":dataSubtypeResourceReturnRateHandler,
    "buildpoints":dataSubtypeWithAmountHelper(combinableString="Build Time"),
    "trainpoints":dataSubtypeWithAmountHelper(combinableString="Train Time"),
    "researchpoints":dataSubtypeWithAmountHelper(combinableString="Research Time"),
    "actionenable":dataSubtypeActionEnableHandler,
    "cost":dataSubtypeWithAmountHelper(textFormat="{combinable} Cost: {value}", combinableAttribute="resource"),
    "onhiteffectrate":dataSubtypeOnHitEffectRateHandler,
    "onhiteffect":dataSubtypeOnHitEffectHandler,
    "populationcount":dataSubtypeWithAmountHelper(combinableString="Population Usage"),
    "rechargetime":dataSubtypeRechargeTimeHandler,
    "auxrechargetime":dataSubtypeAuxRechargeTimeHandler,
    "costbuildingtechs":dataSubtypeWithAmountHelper(textFormat="{combinable} Research Cost: {value}", combinableAttribute="resource"),
    "resourcetricklerate":dataSubtypeWithAmountHelper(textFormat="{combinable} Trickle Rate: {value}", combinableAttribute="resource", flatSuffix=" per second"),
    "unitregenrate":dataSubtypeWithAmountHelper(combinableString="Regeneration Rate", flatSuffix=" per second"),
    "populationcapaddition":dataSubtypeWithAmountHelper(combinableString="Population Cap"),
    "setunittype":dataSubtypeSetUnitTypeHandler,
    "maximumcontained":dataSubtypeWithAmountHelper(combinableString="Garrison Capacity"),
    "carrycapacity":dataSubtypeWithAmountHelper("{combinable} Carry Capacity: {value}", combinableAttribute="resource"),
    "market":dataSubtypeMarketHandler,
    "tributepenalty":dataSubtypeTributePenaltyHandler,
    "ondamagemodify":dataSubypeOnDamageModifyHandler,
    "rateoffire":dataSubtypeWithAmountHelper("Attack Interval {actionof}{combinable}: {value}", combinableAttribute="action"),
    "commandadd":dataSubtypeIgnore,
    "commandremove":dataSubtypeIgnore,
    "onhiteffectattachbone":dataSubtypeIgnore,
    "obstructionradiusx":dataSubtypeObstructionSizeHandler,
    "obstructionradiusz":dataSubtypeObstructionSizeHandler,
    "resourcebykbstat":dataSubtypeIgnore, # Rheia's gift only, and there's no real point in trying to write generic handling for this effect as it'll probably be wrong if it ever gets use
    "enable":dataSubtypeEnableHandler,
    "modifyspawn":dataSubtypeModifySpawnHandler,
    "godpower":dataSubtypeIgnore,
    "timeshiftingcost":dataSubtypeWithAmountHelper(textFormat="{combinable} Time Shift Cost: {value}", combinableAttribute="unittype", combinableAttributeFormat=common.getDisplayNameForProtoOrClass),
    "timeshiftingconcurrentshifts":dataSubtypeWithAmountHelper("Number of Simultaneous Time Shifts: {value}", combinableString=""),
    "veterancyenable":dataSubtypeVeterancyEnableHandler,
    "rechargetype":dataSubtypeIgnore, # Handled in other place
    "rechargeinit":dataSubtypeIgnore,
    "bountyresourceearningreward":dataSubtypeBountyResourceEarningRewardHandler,
    "additionalscale":dataSubtypeWithAmountHelper(combinableString="Model Scale", flatSuffix="x"),
    "onhiteffectactive":dataSubtypeOnHitEffectActiveHandler,
    "homingballistics":dataSubtypeWithAmountHelper("Enables Homing Projectiles {actionfor}{combinable}", combinableAttribute="action"),
    "buildingworkrate":dataSubtypeWithAmountHelper(combinableString="Work Rate"),
    "trainingrate":dataSubtypeWithAmountHelper(combinableString="Unit Training Speed"),
    "protoactionadd":dataSubtypeProtoActionAddHandler,
    "assignonhiteffect":dataSubtypeAssignOnHitEffectHandler,
    "powercost":dataSubtypePowerCostHandler,
    "powerrof":dataSubtypePowerRofHandler,
    "onhiteffectduration":dataSubtypeOnHitEffectDurationHandler,
    "damagearea":dataSubtypeWithAmountHelper("Area of Effect {actionof}{combinable}: {value}", combinableAttribute="action", flatSuffix="m"),
    "empowermodify":dataSubtypeEmpowerModifyHandler,
    "lifespan":dataSubtypeWithAmountHelper(combinableString="Lifespan"),
    "modifyrate":dataSubtypeModifyRateHandler,
    "actionaddattachingunit":dataSubtypeActionAddAttachingUnitHandler,
    "protounitflag":dataSubtypeProtoUnitFlagHandler,
    "revealenemyui":dataSubtypeWithAmountHelper(textFormat="Allow viewing building production/garrisons for {combinable} while in LOS", combinableString="Enemies"),
    "revealallyui":dataSubtypeWithAmountHelper(textFormat="Allow viewing building production for {combinable}", combinableString="Allies"),
    "fullcapacitymultiplier":dataSubtypeWithAmountHelper(textFormat="Favor generation multiplier while at maximum LOS expansion: {value}", combinableString=""),
    "modifyratecap":dataSubtypeWithAmountHelper(textFormat="Maximum LOS expansion: {value}", combinableString=""),
    "godpowerrof":dataSubtypeWithAmountHelper("God Power {combinable}: {value}", combinableString="Recharge"),
    "godpowercost":dataSubtypeWithAmountHelper("God Power {combinable}: {value}", combinableString="Cost"),
    "setage":dataSubtypeIgnore,
    "godpowerblockradius":dataSubtypeWithAmountHelper("God Power Block Radius: {value}", combinableString="", flatSuffix="m"),
    "resource":dataSubtypeWithAmountHelper("{combinable}: {value}", combinableAttribute="resource"),
    "populationcap":dataSubtypeWithAmountHelper("Base Population Cap: {value}", combinableString=""),
    "selfdestructprotoaction":dataSubtypeIgnore,
    "damageflags":dataSubtypeIgnore, # could matter someday
    "buildingchaineffect":dataSubtypeBuildingChainEffectHandler,
    "chargedmodifyadjust":dataSubtypeChargedModifyAdjustHandler,
    "setprotomaxarmor":dataSubtypeWithAmountHelper("Maximum possible {combinable} armor: {value}", valueFormat=lambda val: f"{val*100:0.3g}%", combinableAttribute='damagetype'),
    "addattacktype":dataSubtypeWithAmountHelper("Becomes able to attack {combinable}", combinableAttribute="unittype", combinableAttributeFormat=common.getDisplayNameForProtoOrClassPlural),
    "minworkrate":dataSubtypeMinWorkRateHandler,
    "repaircostfactor":dataSubtypeWithAmountHelper("Building Repair Cost: {value}", combinableString=""),
    "addgoal":dataSubtypeAddGoalHandler,
    "addgoalreward":dataSubtypeIgnore,
    "addgoalcontributor":dataSubtypeIgnore,
    "setgoalspawnlocationland":dataSubtypeIgnore,
    "setgoalspawnlocationwater":dataSubtypeIgnore,
    "setgoalflag":dataSubtypeIgnore,
    "displayedrange":dataSubtypeIgnore,
    "damagebycost":dataSubtypeDamageByCostHandler,
    "buildingchainresourcefactor":dataSubtypeBuildingChainResourceFactorHandler,
    "workrateall":dataSubtypeWithAmountHelper("All Action Work Rate: {value}", combinableString=""),
}


def processEffect(tech: ET.Element, effect: ET.Element) -> Union[None, EffectHandlerResponse, List[EffectHandlerResponse]]:
    effectType = effect.attrib['type'].lower()
    techName = tech.attrib['name']
    subType = effect.attrib.get("subtype")
    if subType is not None:
        subType = subType.lower()
    if effectType == "data":
        dataSubtypes.add(subType)
        if not shouldSuppressDataEffect(tech, effect):
            handler = DATA_SUBTYPE_HANDLERS.get(subType)
            if handler is None:
                print(f"Warning: Unhandled effect data effect subtype {subType} on {techName}")
            else:
                return handler(tech, effect)
    # Techstatus needs handling on a case by case I think
    # The noteworthy ones (eg respawning units) would be a bit involved to work out automatically
    elif effectType in ("setname", "textoutput", "techstatus", "setage", "createpower"):
        pass
    elif effectType == "sharedlos":
        return EffectHandlerResponse("Player", "Grants line of sight as if you owned all players' units.")
    elif effectType == "transformunit":
        return EffectHandlerResponse(common.getDisplayNameForProtoOrClass(effect.attrib['fromprotoid']), f"Transform into {common.getDisplayNameForProtoOrClass(effect.attrib['toprotoid'])}")
    elif effectType == "createunit":
        quantity = int(float(effect.find("pattern").attrib['quantity']))
        return EffectHandlerResponse(f"Oldest {common.commaSeparatedList(common.getListOfDisplayNamesForProtoOrClass(effect.attrib['generator']), 'or')}", f"Spawns {quantity}x {common.getDisplayNameForProtoOrClass(effect.attrib['unit'])} (one time only)")
    elif effectType == "setontechresearchedtech":
        return handleOnTechResearchedTech(tech, effect)
    else:
        print(f"Warning: Unknown effect type {effectType} on {techName}")
    return None

@dataclasses.dataclass
class TechAddition:
    # One or more lines to put at the top of the effect list
    startEntry: Union[str, List[str]] = ""
    # One or more lines to put at the bottom of the effect list
    endEntry: Union[str, List[str]] = ""

    # A callable that is called for each line of text in the output. Any for which it returns False to are removed.
    lineFilter: Callable[[str], bool] = lambda x: True
    # A string or list of lines to prepend to the tech's history entry, if one exists.
    historyText: Union[str, List[str]] = ""
    # Whether or not to try fuzzy merge on generated text lines with near identical content. In some cases, this can produce a more natural tooltip.
    # However, it does have potential to make a complete mess of things
    fuzzyMerge: bool = True

def handlerResponseListToStrings(input: Union[EffectHandlerResponse, List[EffectHandlerResponse]], skipAffectedObjects: bool=False) -> List[str]:
    if isinstance(input, EffectHandlerResponse):
        return [input.toString(skipAffectedObjects=skipAffectedObjects)]
    combineHandlerResponses(input)
    strings = [response.toString(skipAffectedObjects=skipAffectedObjects) for response in input]
    return strings


def processTech(tech: ET.Element, skipAffectedObjects: bool=False, lineJoin: str=f"\\n"):
    #print(f"Processing tech: {tech.attrib['name']}")
    # Minor god techs show up over the portraits. That makes me very sad, but I don't want to get into changing UI files as well really
    # so let's just leave these strings as vanilla
    if tech.find("flag[.='AgeUpgrade']") is not None:
        return None
    additions = techManualAdditions.get(tech.attrib['name'], None)

    effects = tech.findall("effects/effect")
    responses: List[Union[None, EffectHandlerResponse]]= []
    for effect in effects:
        response = processEffect(tech, effect)
        if response is not None:
            if isinstance(response, list):
                responses += response
            else:
                responses.append(response)
    if additions is not None:
        responses = [response for response in responses if additions.lineFilter(response.toString())]
    combineHandlerResponses(responses)
    strings = [response.toString(skipAffectedObjects=skipAffectedObjects) for response in responses]

    if tech.find("flag[.='DynamicCost']") is not None:
        costs = [x for x in tech.findall("cost")]
        costString = " ".join([f"{icon.resourceIcon(x.attrib['resourcetype'])} {float(x.text):0.3g}" for x in costs])
        strings.insert(0, f"Costs {costString} per enemy unit.")

    if additions is not None:
        if additions.startEntry:
            if isinstance(additions.startEntry, list):
                strings = additions.startEntry + strings
            else:
                strings.insert(0, additions.startEntry) 
        if additions.endEntry:
            if isinstance(additions.endEntry, list):
                strings += additions.endEntry
            else:
                strings.append(additions.endEntry) 
    if additions is None or additions.fuzzyMerge:
        strings = common.attemptAllWordwiseTextMerges(strings, tech.attrib['name'])

    output = lineJoin.join(strings)
    if len(output) == 0: # Need to output something or we get <MISSING> if empty
        if len(effects):
            print(f"Warning: tech {tech.attrib['name']} with {len(effects)} effects had no text output, reverting to vanilla text")
        return None
    
    if additions is not None and len(additions.historyText) > 0:
        common.prependTextToHistoryFile(tech.attrib['name'], "techs", additions.historyText)

    return output

techManualAdditions: Dict[str, TechAddition] = {}



def generateTechDescriptions():
    proto = globals.dataCollection["proto.xml"]
    techtree = globals.dataCollection["techtree.xml"]

    for techElement in techtree:
        if techElement.find("[flag='Volatile']") is not None:
            create = techElement.find("effects/effect[@type='CreateUnit']")
            if create is not None:
                globals.respawnTechs[create.attrib['unit']] = techElement

    # These assocaitions come from aotg data but will show in tooltips if not dealt with
    del globals.respawnTechs["Promethean"]
    del globals.respawnTechs["MountainGiant"]

    # Techs are done before units.
    # This means those in the unit describer aren't loaded when this runs, so any that really NEED changing need to go here...
    # And simply changing the order isn't really doable because some of the stuff in the unit describer is dependent on the tech overrides - there's no good way to do this
    unitdescription.unitDescriptionOverrides["DaoSwordsman"] = unitdescription.UnitDescription(actionNameOverrides={"SelfDestructAttack":"Infantry Buff"})
    unitdescription.unitDescriptionOverrides["GeHalberdier"] = unitdescription.UnitDescription(actionNameOverrides={"SelfDestructAttack":"Infantry Buff"})

    FreyrTechCostBonus = techtree.find("tech[@name='FreyrTechCostBonus']")
    FreyrTechCostBonusEffect = FreyrTechCostBonus.find("effects/effect")
    techManualAdditions["FreyrsGift"] = TechAddition(endEntry=f"Every time another tech is researched, this tech becomes {-1*float(FreyrTechCostBonusEffect.attrib['amount']):0.3g} {FreyrTechCostBonusEffect.attrib['resource']} cheaper.")

    eyesOnForestRevealer = common.protoFromName("EyesOnForestRevealer")
    eyesOnForestRevealerLOS = common.findAndFetchText(eyesOnForestRevealer, 'los', 0, float)
    eyesOnForestRevealerAction = eyesOnForestRevealer.find("protoaction[name='DynamicLOS']")
    eyesOnForestRevealerActionModifyAmount = common.findAndFetchText(eyesOnForestRevealerAction, "modifyamount", 0.0, float)
    eyesOnForestRevealerModifyRateCap = common.findAndFetchText(eyesOnForestRevealerAction, "modifyratecap", 0.0, float)
    eyesOnForestRevealerMaxLOS = eyesOnForestRevealerLOS + eyesOnForestRevealerModifyRateCap
    eyesOnForestRevealerModifyDecay = common.findAndFetchText(eyesOnForestRevealerAction, "modifydecay", 0.0, float)
    eyesOnForestRevealerLifetime = eyesOnForestRevealerModifyRateCap/eyesOnForestRevealerActionModifyAmount + eyesOnForestRevealerModifyRateCap/eyesOnForestRevealerModifyDecay

    techManualAdditions["WingedMessenger"] = TechAddition(startEntry=f"Grants a Pegasus that respawns for free {float(globals.respawnTechs['PegasusWingedMessenger'].find('delay').text):0.3g} seconds after it is killed. This Pegasus does not have a population cost.")

    techManualAdditions["EyesInTheForest"] = TechAddition(endEntry=f"These revealers last for {eyesOnForestRevealerLifetime:0.3g} seconds. They have {eyesOnForestRevealerLOS:0.3g} LOS, which increases by {eyesOnForestRevealerActionModifyAmount:0.3g} per second to a maximum of {eyesOnForestRevealerMaxLOS:0.3g}. Then, the LOS starts to decay at {eyesOnForestRevealerModifyDecay:0.3g} per second until the revealer disappears.")

    techManualAdditions["SunRay"] = TechAddition(endEntry=f"These revealers have {float(common.protoFromName('SunRayRevealer').find('los').text):0.3g} LOS and last for {float(common.protoFromName('SunRayRevealer').find('lifespan').text):0.3g} seconds.")
        
    techManualAdditions["NewKingdom"]=TechAddition(startEntry="Grants a second Pharaoh.")
    techManualAdditions["HandsOfThePharaoh"]=TechAddition(startEntry="Allows Priests to pick up Relics.")

    techManualAdditions["HallOfThanes"]=TechAddition(endEntry="As both Infantry and Heroes, Hersir benefit from both effects.")
    techManualAdditions["FuryOfTheFallen"]=TechAddition(endEntry=f"Damage boosters persist for {float(common.protoFromName('BerserkDamageBoost').find('lifespan').text):0.3g} seconds.")

    techManualAdditions["SonsOfTheSun"]=TechAddition(startEntry="Regular Oracles can no longer be trained: Temples produce Oracle Heroes directly instead.")
    # Hide the hero promotion text.
    # Nobody really cares that hero promotion is internally a tech, and not doing this makes it look like hero promotion is getting more expensive!
    techManualAdditions["RheiasGift"]=TechAddition(startEntry="Refunds all Favor spent on technologies.", lineFilter=lambda x: "Promotion" not in x)
    techManualAdditions["Channels"]=TechAddition(startEntry="Lush: Increases Unit Movement Speed by {:0.0%}.".format(float(globals.dataCollection['terrain_unit_effects.xml'].find("terrainuniteffect[@name='GaiaCreepSpeedEffect']/effect[@name='GaiaCreepSpeedAll']").attrib['amount'])-1.0))
    # Hide the total unit cost modifications, because they are misleading
    # The promotion cost is what people care about here
    techManualAdditions["FrontlineHeroics"]=TechAddition(lineFilter=lambda x: "Promotion" in x)
    # Avoid referring to promotion "research points" because the concept of promotion being research is going to confuse people who don't know it
    heartOfTheTitans = common.techFromName("HeartOfTheTitans")
    heartOfTitansAltEffect = processEffect(heartOfTheTitans, heartOfTheTitans.find("effects/effect[@subtype='ResearchPoints']")).toString().replace("Research Time", "Completion Time")
    techManualAdditions["HeartOfTheTitans"] = TechAddition(startEntry=heartOfTitansAltEffect, lineFilter=lambda x: "Research Time" not in x, fuzzyMerge=False)

    techManualAdditions["KuafuChieftain"] = TechAddition(startEntry=[f"Grants a Kuafu Hero that respawns for free {float(globals.respawnTechs['KuafuHero'].find('delay').text):0.3g} seconds after it is killed.", unitdescription.describeUnit("KuafuHero")])
    vibrantLandPower = common.findGodPowerByName("VibrantLand")
    vibrantLandInterval = common.findAndFetchText(vibrantLandPower, "generateinterval", None, float)
    vibrantLandRestrictionElems = vibrantLandPower.findall("placementrestriction")
    vibrantLandRestrictions = []
    for elem in vibrantLandRestrictionElems:
        vibrantLandRestrictions.append(f"Trees will not spawn within {float(elem.attrib['radius']):0.3g}m of {common.getDisplayNameForProtoOrClass(elem.text, plural=True)}.")
    vibrantLandTreeProtos = [elem.text for elem in vibrantLandPower.findall("treeproto")]
    vibrantLandWoodAmounts = [float(common.protoFromName(proto).find("initialresource[@resourcetype='Wood']").text) for proto in vibrantLandTreeProtos]
    vibrantLandWood = int(sum(vibrantLandWoodAmounts)/len(vibrantLandWoodAmounts))
    

    techManualAdditions["VibrantLand"] = TechAddition(startEntry=f"House: Every {vibrantLandInterval:0.3g}s, spawns a tree containing {icon.resourceIcon('Wood')} {vibrantLandWood}. {' '.join(vibrantLandRestrictions)}",
                                                      lineFilter=lambda x: "House: Wood Carry" not in x)
    # Spoils of War
    nuwaBountyEarnings = globals.dataCollection["major_gods.xml"].find("civ[name='Fuxi']/bountyresourceearning").findall("bountyreward")
    spoilsTargets: Dict[str, Dict[str, float]] = {}
    for elem in nuwaBountyEarnings:
        target = elem.attrib['unittype']
        if target not in spoilsTargets:
            spoilsTargets[target] = {}
        spoilsTargets[target][elem.attrib['resourcetype']] = float(elem.text)
    spoilsHistory = ["Full list of resource returns:", ""]
    for target, resourceDict in spoilsTargets.items():
        rewards = []
        for resource, amount in resourceDict.items():
            rewards.append(icon.resourceIcon(resource) + f" {amount:0.3g}")
        spoilsHistory.append(common.commaSeparatedList(common.getListOfDisplayNamesForProtoOrClass(target, plural=False)) + f": {' '.join(rewards)}")
    techManualAdditions["SpoilsOfWar"] = TechAddition(startEntry="Destroying enemy buildings rewards you with about 50% of their base resource cost. A full list is available in this tech's history section.", historyText=spoilsHistory)

    # Hide VFX spawn text
    techManualAdditions["DroughtShips"] = TechAddition(lineFilter=lambda x: "spawns" not in x)

    skyfireLand = action.actionDamageOverTimeArea("SkylanternFireAreaGround")
    skyfireWater = action.actionDamageOverTimeArea("SkylanternFireAreaWater")
    if skyfireLand == skyfireWater:
        techManualAdditions["SkyFire"] = TechAddition(startEntry=f"Sky Lantern: On death: {skyfireLand}", lineFilter=lambda x: "VFX" not in x)
    else:
        techManualAdditions["SkyFire"] = TechAddition(startEntry=[f"Sky Lantern: On death over Land: {skyfireLand}", f"Sky Lantern: On death over Water: {skyfireLand}"], lineFilter=lambda x: "VFX" not in x)

    advancedDefensesTransformTech = common.techFromName("WallConnectorToTower")
    advancedDefensesTransformTime = common.findAndFetchText(advancedDefensesTransformTech, "researchpoints", 0.0, float)
    techManualAdditions["AdvancedDefenses"] = TechAddition(startEntry=f"Wall Connector: Allows conversion to Tower ({advancedDefensesTransformTime:0.3g} seconds).")

    pixiuModifyExponent = common.findAndFetchText(action.findActionByName("PiXiu", "Trade"), "modifyexponent", 0.0, float) * 0.1
    autumnOfAbundanceEffects = common.techFromName("AutumnOfAbundance").findall("effects/effect[@subtype='MinWorkRate']")
    autumnOfAbundanceAmounts = list(set([float(x.attrib['amount']) for x in autumnOfAbundanceEffects]))
    if len(autumnOfAbundanceAmounts) != 1:
        raise ValueError(f"Autumn of Abundance assumptions invalidated: {autumnOfAbundanceAmounts}")
    pixiuModifyExponent *= autumnOfAbundanceAmounts[0]

    techManualAdditions["AutumnOfAbundance"] = TechAddition(endEntry=f"With Silk Road: Pixiu trading with an ally gives them {100*pixiuModifyExponent:0.3g}% of your Gold profit as Food and Wood.")

    maelstromSpawnAction = action.findActionByName("DouJian", "RangedAttack").find("onhiteffect[@proto]")
    maelstromObject = common.protoFromName(maelstromSpawnAction.attrib['proto'])
    maelstromChance = float(maelstromSpawnAction.attrib['prob'])
    maelstromTarget = common.getDisplayNameForProtoOrClass(maelstromSpawnAction.find("target[@attacktype]").attrib['attacktype'])
    maelstromLifetime = common.findAndFetchText(maelstromObject, "lifespan", 0.0, float)
    maelstromPullRadius = common.findAndFetchText(action.actionTactics(maelstromObject, "WaterTornado"), "maxrange", 0.0, float)
    maelstromDamageAuras = " ".join([action.describeAction(maelstromObject, aura) for aura in ("AreaDamage",)])
    techManualAdditions["Maelstrom"] = TechAddition(startEntry=f"Doujian: Each projectile fired at a {maelstromTarget} in water has a {maelstromChance:0.3g}% to spawn a Maelstrom. Maelstroms last {maelstromLifetime:0.3g} seconds, pulling in enemy units within {maelstromPullRadius:0.3g}m. Enemy units in the middle of the Maelstrom spin and cannot attack properly. {maelstromDamageAuras}",
                                                    lineFilter=lambda line: "Modifies Ranged Attack" not in line)
    
    techManualAdditions["DivineLight"]=TechAddition(startEntry="Allows Pioneers to pick up Relics.")

    techManualAdditions["SecretsOfTheTitans"]=TechAddition(startEntry="Allows the placement of a Titan Gate. Once fully excavated, releases a Titan.")

    WonderAgeTitan = techtree.find("tech[@name='WonderAgeTitan']")
    WonderAgeTitanInterval = float(WonderAgeTitan.find("effects/effect[@subtype='PowerROF']").attrib['amount'])/60
    techManualAdditions["WonderAgeGeneral"]=TechAddition(endEntry=f"Allows recasting of Titan Gate every {WonderAgeTitanInterval:0.3g} minutes.")

    techManualAdditions["RelicBridleOfPegasus"] = TechAddition(startEntry=f"Grants a Pegasus that respawns for free {float(globals.respawnTechs['PegasusBridleOfPegasus'].find('delay').text):0.3g} seconds after it is killed. This Pegasus does not have a population cost.")
    techManualAdditions["RelicChariotOfCybele"] = TechAddition(startEntry=f"Grants two Golden Lions that respawn for free {float(globals.respawnTechs['RelicGoldenLion'].find('delay').text):0.3g} seconds after both are killed.")
    techManualAdditions["RelicSkullsOfTheCercopes"] = TechAddition(startEntry=f"Grants six Monkeys that respawn for free {float(globals.respawnTechs['RelicMonkey'].find('delay').text):0.3g} seconds after all are killed.")
    techManualAdditions["RelicTuskOfDangkang"] = TechAddition(startEntry=f"Spawns two Pigs every {float(globals.respawnTechs['Pig'].find('delay').text):0.3g} seconds.")
    techManualAdditions["RelicTailOfFei"] = TechAddition(startEntry=f"Grants a Fei that respawns for free {float(globals.respawnTechs['FeiTailOfFei'].find('delay').text):0.3g} seconds after it is killed.")

    demetersthrone = common.techFromName("RelicDemetersThrone")
    demetersthroneCost = list(set([float(x.attrib['amount']) for x in demetersthrone.findall("effects/effect[@subtype='Cost']")]))
    demetersthroneBuildpoints = list(set([float(x.attrib['amount']) for x in demetersthrone.findall("effects/effect[@subtype='BuildPoints']")]))
    if len(demetersthroneCost) != 1 or len(demetersthroneBuildpoints) != 1:
        print(f"Warning: Demeter's throne override assumptions invalidated")
    else:
        costEffect = processEffect(demetersthrone, demetersthrone.find("effects/effect[@subtype='Cost']"))
        costEffect.combinableTargets = ["Food", "Wood", "Gold"]
        costEffect.affects = "House"
        costString = "House, Manor and Dedicated Dropsite: " + costEffect.toString(skipAffectedObjects=True)
        buildpointEffect = processEffect(demetersthrone, demetersthrone.find("effects/effect[@subtype='BuildPoints']"))
        buildpointString = "House, Manor and Dedicated Dropsite: " + buildpointEffect.toString(skipAffectedObjects=True)
        techManualAdditions["RelicDemetersThrone"] = TechAddition(lineFilter=lambda x: False, startEntry=[costString, buildpointString])

    ninecauldrons = common.techFromName("RelicNineCauldrons")
    ninecauldronsSomeTarget = ninecauldrons.find("effects/effect/target").text
    ninecauldronsEffectsOnThatTarget = ninecauldrons.findall(f"effects/effect/target[.='{ninecauldronsSomeTarget}']/..")
    ninecauldronsEffects = [processEffect(ninecauldrons, effect) for effect in ninecauldronsEffectsOnThatTarget]
    combineHandlerResponses(ninecauldronsEffects)
    ninecauldronsStrings = [response.toString(skipAffectedObjects=True) for response in ninecauldronsEffects]

    ninecauldronsStrings = common.attemptAllWordwiseTextMerges(ninecauldronsStrings, "RelicNineCauldrons")
    ninecauldronsStrings = ["Human Soldiers from Fortress-type Buildings (and alternate forms): " + s for s in ninecauldronsStrings]
    techManualAdditions["RelicNineCauldrons"] = TechAddition(startEntry=ninecauldronsStrings, lineFilter = lambda x: False)
    

    ochreWhipEntries = []
    for targetTechElem in common.techFromName("RelicOchreWhipOfShennong").findall("effects/effect[@type='TechStatus']"):
        targetTech = common.techFromName(targetTechElem.text)
        prereqTechs = targetTech.findall("prereqs/techstatus")
        prereqTechs = list(filter(lambda elem: not elem.text.startswith("Relic"), prereqTechs))
        if len(prereqTechs) != 1:
            raise ValueError(f"Ochre Whip of Shennong got more than one prereq for {targetTechElem.text}")
        ochreWhipEntries.append(f"{common.getObjectDisplayName(common.techFromName(prereqTechs[0].text))}: {processTech(targetTech)}")
    techManualAdditions["RelicOchreWhipOfShennong"] = TechAddition(startEntry=ochreWhipEntries)
    
    # "Spawns 1 Boar (Arkantos and Ajax)"" is fuzzymerged nonsense
    techManualAdditions["AOTGHeroBoarStartDivine"] = TechAddition(fuzzyMerge=False)


    stringIdsByOverwriters = {}

    for tech in techtree:
        strid = common.findAndFetchText(tech, "rollovertextid", None)
        if strid is not None:
            value = processTech(tech)
            if value is not None:
                if strid not in stringIdsByOverwriters:
                    stringIdsByOverwriters[strid] = {}
                if value not in stringIdsByOverwriters[strid].values():
                    stringIdsByOverwriters[strid][tech] = value

    common.handleSharedStringIDConflicts(stringIdsByOverwriters)

    ageIndexes = {"ClassicalAge":1, "HeroicAge":2, "MythicAge":3}

    # I think I resign myself to hardcoding values here. The normal output will not be anywhere NEAR concise enough
    classicalAgeGeneral = techtree.find("tech[@name='ClassicalAgeGeneral']")
    heroicAgeGeneral = techtree.find("tech[@name='HeroicAgeGeneral']")
    mythicAgeGeneral = techtree.find("tech[@name='MythicAgeGeneral']")
    ageUpComponents = ["Myth Units of Earlier Ages: Hitpoints, Damage, and Healing: +20% of base."]
    ageUpTechs = (classicalAgeGeneral, heroicAgeGeneral, mythicAgeGeneral)
    heroHitpoints = ["{:0.3g}".format(100*(-1+float(age.find("effects/effect[@subtype='Hitpoints']/target[.='HeroShadowUpgraded']/..").attrib['amount']))) for age in ageUpTechs]
    heroDamage = ["{:0.3g}".format(100*(-1+float(age.find("effects/effect[@subtype='Damage']/target[.='HeroShadowUpgraded']/..").attrib['amount']))) for age in ageUpTechs]
    ageUpComponents.append(f"Age Upgraded Heroes: Hitpoints +{'/'.join(heroHitpoints)}% of base, Damage +{'/'.join(heroDamage)}% of base (Classical/Heroic/Mythic).")
    tradePostBuffs = ["{:0.3g}".format(float(age.find("effects/effect[@action='AutoGatherFood']/target[.='TradingPost']/..").attrib['amount'])) for age in ageUpTechs]
    ageUpComponents.append(f"Trading Post gather rates: +{'/'.join(tradePostBuffs)} per second.")

    # Greek hero effects
    greekHeroTrainIncreases = []
    greekHeroDamageIncreases = []
    for ageName, ageIndex in ageIndexes.items():
        greekTech = common.techFromName(ageName + "Greek")
        greekTechEffect = greekTech.find("effects/effect[@subtype='TrainPoints']/target[.='HeroShadowUpgraded']/..")
        if greekTechEffect is None:
            greekHeroTrainIncreases.append("0")
        else:
            greekHeroTrainIncreases.append(f"{-100*(float(greekTechEffect.attrib['amount'])-1.0):0.3g}")
        greekTechEffect = greekTech.find("effects/effect[@subtype='Damagebonus'][@unittype='MythUnit']/target[.='HeroShadowUpgraded']/..")
        if greekTechEffect is None:
            greekHeroDamageIncreases.append("0")
        else:
            greekHeroDamageIncreases.append(f"{float(greekTechEffect.attrib['amount']):0.3g}")
    ageUpComponents.append(f"Greek Hero training time: -{'/'.join(greekHeroTrainIncreases)}% of current.")
    ageUpComponents.append(f"Greek Hero bonus vs Myth Units: +{'/'.join(greekHeroDamageIncreases)}x.")

    globals.stringMap["STR_FORMAT_MINOR_GOD_LR"] = f"\\n {icon.BULLET_POINT} ".join(ageUpComponents) + f"\\n\\n {icon.BULLET_POINT} " + globals.dataCollection["string_table.txt"]["STR_FORMAT_MINOR_GOD_LR"]

    

    

    # Advancement messages
    for tech in techtree:
        if tech.find("flag[.='AgeUpgrade']") is not None:
            textOutputStrId = tech.find("effects/effect[@type='TextOutput'][@all='true']").text
            unitsCreated = [elem.text for elem in tech.findall("effects/effect[@subtype='Enable']/target")]
            #unitsCreatedString = common.commaSeparatedList(common.unwrapAbstractClass(unitsCreated))
            unitsCreatedString = " ".join([icon.generalIcon(common.protoFromName(unit).find('icon').text) for unit in unitsCreated])
            powerGranted = tech.find("effects/effect[@subtype='GodPower']").attrib['power']
            powerElement = globals.dataCollection['god_powers_combined'].find(f"power[@name='{powerGranted}']")
            powerGrantedName = icon.generalIcon(powerElement.find('icon').text)
            #powerGrantedName = common.getObjectDisplayName(powerElement)
            techDisplayName = common.getObjectDisplayName(tech)
            for techType in tech.findall("techtype"):
                if techType.text in ageIndexes:
                    ageText = common.AGE_LABELS[ageIndexes[techType.text]]
            newString = f"{{0}} advances to the {ageText} Age through {techDisplayName}: {unitsCreatedString} + {powerGrantedName}"
            globals.stringMap[textOutputStrId] = newString

    # Make the vanilla detail text darker
    for key, value in globals.dataCollection['string_table.txt'].items():
        if key.startswith("STR_EFFECT_") and value.startswith("{0}"):
            globals.stringMap[key] = VANILLA_FULL_TOOLTIP_EFFECT_COLOUR(value)

    # Do the same to any defined advancedrollovertextoverrideid-s
    for tech in techtree:
        overrideVanillaElement = tech.find("advancedrollovertextoverrideid")
        if overrideVanillaElement is not None:
            globals.stringMap[overrideVanillaElement.text] = VANILLA_FULL_TOOLTIP_EFFECT_COLOUR(globals.dataCollection['string_table.txt'][overrideVanillaElement.text])
        # And for any per-effect set overrides, since those are now a thing
        for effect in tech.findall("effects/effect[@tooltipid]"):
            globals.stringMap[effect.attrib['tooltipid']] = VANILLA_FULL_TOOLTIP_EFFECT_COLOUR(globals.dataCollection['string_table.txt'][effect.attrib['tooltipid']])