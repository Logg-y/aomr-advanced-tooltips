import globals
import common
from xml.etree import ElementTree as ET
from typing import List, Dict, Union, Callable, Any
import dataclasses
import action
import icon


dataSubtypes = set()

# The way to go here is probably to do a once-over to work out the things we want to say about all the effects
# And then have handling to try to group up similar statements about different effects
# This means we need to track all the things that might be combined in different ways

# The things we might want to do are:
# "X and Y: increases damage by..."
# "X and Y: reduces food and gold cost by..."

# Unwrap abstract types with this many members or fewer into a list of actual object names
AUTO_UNWRAP_ABSTRACT_TYPE_SIZE = 4

# Always unwrap these
ABSTRACT_TYPES_TO_UNWRAP = (
    "SiegeLineUpgraded",    # Engineers target that excludes cheiroballista
    "HeroInfantry",
)

@dataclasses.dataclass
class EffectHandlerResponse:
    # For when a tech effect doesn't affect some object types (eg Thurisaz rune regen on titans), we can list what isn't affected
    #doesntAffect: List[str] = dataclasses.field(default_factory=list)

    # A list of objects affected by the effect. It's probably just 1 item, but in some cases I might want to expand abstract types to raw proto lists
    # This gets used to make the "X and Y: ..." combinations if the rest of the effect matches
    affects: Union[str, List[str]] = dataclasses.field(default_factory=list)

    # Raw string explaining what the effect does. If set, combining similar effects together is not possible.
    # This is used for effects where there is no possibility of ever combining with similar effects, like action enabling or flag addition
    fullEffectText: Union[str, None] = None

    # "X: reduces food and gold cost by..."
    
    # These are targets that can get combined if everything else is the same, eg "food" "gold" in the above
    combinableTargets: Union[List[str], str] = dataclasses.field(default_factory=list)

    # This is the text that comes before the targets list, "reduces" in the above
    preTargetText: str = ""

    # The text that comes after the targets list, "cost by <amount>" in the above
    postTargetText: str = ""

    # In a combined case like "Increases damage bonus against archers and cavalry by +0.25x"
    # preTargetText = "Increases damage bonus against"
    # combinableTargets = ["archers", "cavalry"]
    # postTargetText = "by +0.25x"
    def canCombineAffects(self, other):
        if self.fullEffectText == other.fullEffectText and self.preTargetText == other.preTargetText and self.postTargetText == other.postTargetText and self.combinableTargets == other.combinableTargets:
            return True
        return False
    
    def canCombineTargets(self, other):
        if self.fullEffectText is not None or other.fullEffectText is not None:
            return False
        if self.preTargetText == other.preTargetText and self.postTargetText == other.postTargetText and self.affects == other.affects:
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
    
    def toString(self):
        components = []
        if isinstance(self.affects, list):
            self.affects = list(set(self.affects))
            components.append(common.commaSeparatedList(self.affects))
        else:
            components.append(self.affects)
        components[-1] += ":"
        if self.fullEffectText:
            components.append(self.fullEffectText)
        else:
            combinables = self.combinableTargets
            if isinstance(self.combinableTargets, list):
                combinables = common.commaSeparatedList(self.combinableTargets)
            if len(combinables):
                if len(self.postTargetText):
                    combinables += ":"
            else:
                self.preTargetText += ":"
            components += [self.preTargetText, combinables, self.postTargetText]

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
    # This is not a detail I want to expose
    targetTexts = [node.text for node in effect.findall("target")]
    if effectType == "data" and subType == "hitpoints" and "LogicalTypeUnitIsConstructed" in targetTexts:
        return True
    # WorkRate on JumpAttacks doesn't seem to do a whole lot
    if effectType == "data" and subType == "workrate" and effect.attrib.get("action") == "JumpAttack":
        return True
    
    return False
    

def getEffectTargets(tech: ET.Element, effect: ET.Element):
    targets = []
    nodes = effect.findall("target")
    for node in nodes:
        nodeType = node.attrib["type"].lower()
        if nodeType == "protounit":
            if node.text in globals.protosByUnitType:
                targetsList = globals.protosByUnitType[node.text]
                if node.text in ABSTRACT_TYPES_TO_UNWRAP or len(targetsList) <= AUTO_UNWRAP_ABSTRACT_TYPE_SIZE:
                    targets += map(common.getDisplayNameForProtoOrClass, targetsList)
                else:
                    targets.append(common.getDisplayNameForProtoOrClass(node.text))
            else:
                targets.append(common.getDisplayNameForProtoOrClass(node.text))
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
        elif nodeType == "techwithflag" and node.text == "AgeUpgrade":
            targets.append("Age Upgrades")
        else:
            raise ValueError(f"{tech.attrib['name']}: unhandled effect target type {nodeType}")
    return targets

def dataHandlerGeneral(tech: ET.Element, effect: ET.Element, valueText: str, combinableTarget: str, additionalPreTargetText: str = "", additionalPostTargetText: str = "", flatSuffix="", percentileSuffix="%", combinePostTargetAndPreTarget=False) -> EffectHandlerResponse:
    relativity = effect.attrib["relativity"].lower()
    amount = float(effect.attrib["amount"])

    preTargetText = ""
    postValueText = ""

    if relativity == "assign":
        preValueText = "set to "
    elif relativity == "absolute":
        preValueText = "+" if amount > 0.0 else "-"
        postValueText = ""
        valueText += flatSuffix
    elif relativity in ("percent", "basepercent"):
        if effect.attrib['type'].lower() == "armorvulnerability":
            amount += 1.0
        preValueText = "+" if amount > 1.0 else "-"
        valueText += percentileSuffix
        if relativity == "percent":
            postValueText = "of current value"
        else:
            postValueText = "of base value"
    elif relativity == "override":
        preValueText = "sets base value to "
    else:
        raise ValueError(f"{tech.attrib['name']}: unknown relativity {relativity}")

    if additionalPreTargetText:
        preTargetText += f" {additionalPreTargetText}"
    

    components = [preValueText + valueText, postValueText]
    components = [component.strip() for component in components if len(component.strip()) > 0]
    postTargetText = " ".join(components)
    if additionalPostTargetText:
        postTargetText += f" {additionalPostTargetText}"

    if combinePostTargetAndPreTarget:
        preTargetText = preTargetText.strip() + " " + postTargetText.strip()
        postTargetText = ""

    affectedObjects = getEffectTargets(tech, effect)

    return EffectHandlerResponse(affects=affectedObjects, combinableTargets=combinableTarget, preTargetText=preTargetText.strip(), postTargetText=postTargetText.strip())

def relativityModifiedValue(effect: ET.Element, attrib: str):
    rawValue = float(effect.attrib[attrib])
    relativity = effect.attrib["relativity"].lower()
    if relativity in ("percent", "basepercent"):
        rawValue = 100*(rawValue - 1.0)
    return abs(rawValue)

def relativityModifierArmor(effect: ET.Element, attrib: str):
    rawValue = float(effect.attrib[attrib])
    relativity = effect.attrib["relativity"].lower()
    if relativity != "percent":
        raise ValueError(f"Unsupported armor modification relativity {relativity}")
    
    rawValue = 100*rawValue
    return abs(rawValue)

def dataSubtypeDamageHandler(tech: ET.Element, effect:ET.Element):
    damageType = effect.attrib.get("damagetype", "")
    preTargetText = f"{damageType} Damage".strip()
    if effect.attrib.get("action") is not None:
        preTargetText += " of"

    return dataSubtypeHelper("amount", combinableAttribute="action", additionalPreTargetText=preTargetText)(tech, effect)

def dataSubtypeResourceReturnHandler(tech: ET.Element, effect:ET.Element):
    resource = effect.attrib.get("resource", "")
    preTargetText = f"Resources returned on death"
    resourceText = f"{icon.resourceIcon(resource)} {float(effect.attrib['amount']):0.3g}"

    return dataHandlerGeneral(tech, effect, "", resourceText, preTargetText, combinePostTargetAndPreTarget=True)

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
            print(f"{tech.attrib['name']} trying to enable action {actionName} on {targetType}, no corresponding action found")
            continue
        actionDescription = action.describeAction(proto, actionNode, action.tacticsGetChargeType(tactics))
        if len(actionDescription) == 0:
            print(f"{tech.attrib['name']} enabling {actionName} on {targetType}: describeAction says it doesn't do anything, but that might be okay")
            continue
        isEnabling = bool(int(float(effect.attrib.get("amount"))))

        components = ["Enables" if isEnabling else "Disables", "action:", actionDescription]
        text = " ".join(components)

        responses.append(EffectHandlerResponse(affects=common.getDisplayNameForProtoOrClass(targetType), fullEffectText=text))
    
    return responses

def dataSubtypeWorkrateHandler(tech: ET.Element, effect:ET.Element):
    action = effect.attrib['action']
    additionalPostTargetText = ""
    if action == "BurstHeal":
        preTargetText = f"Burst Heal strength for"
    elif action == "Autogather":
        preTargetText = "Trickle rate for"
        additionalPostTargetText = "per second"
    elif action == "AutoGatherFood":
        preTargetText = "Fatten rate for"
        additionalPostTargetText = "per second"
    elif action == "AutoGatherFavor":
        # TODO oracle related stuff
        preTargetText = "???"
    else:
        preTargetText = f"{action} rate for"
    return dataSubtypeHelper("amount", combinableAttribute="unittype", combinableAttributeFormat=common.getDisplayNameForProtoOrClass, additionalPreTargetText=preTargetText, additionalPostTargetText=additionalPostTargetText)(tech, effect)

def dataSubtypeHelper(valueAttrib: str, 
                      combinableString: Union[str, None]=None, 
                      combinableAttribute: Union[str, None]=None,
                      combinableAttributeFormat: Union[str, Callable[[str], str]] = "{}",
                      additionalPreTargetText: str="", 
                      additionalPostTargetText: str="",
                      valueFormat: str="{:0.3g}", 
                      percentileSuffix="%", 
                      flatSuffix="",
                      relativityModifier: Callable[[ET.Element, str], str]=relativityModifiedValue
                      ) -> Callable[[ET.Element, ET.Element], EffectHandlerResponse]:
    def inner(tech: ET.Element, effect:ET.Element):
        valueText = valueFormat.format(relativityModifier(effect, valueAttrib))
        if combinableString is not None:
            combinableTarget = combinableString
        elif combinableAttribute is not None:
            if combinableAttribute == "action":
                if effect.attrib.get("allactions") is not None:
                    combinableTarget = ""
                else:
                    actionName = effect.attrib['action']
                    # If we can find an actual action name, do so
                    targetNodes = effect.findall("target[@type='ProtoUnit']")
                    targets = [x.text for x in targetNodes if x.text not in globals.abstractTypes]
                    if len(targets) == 1:
                        actionNode = action.findActionByName(targets[0], actionName)
                        actionNameFromProto = action.getActionName(targets[0], actionNode)
                        if action.tacticsGetChargeType(action.actionTactics(targets[0], actionNode)) != action.ActionChargeType.NONE:
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
            raise ValueError("dataSubtypeHelper passed no combinable item!")

        return dataHandlerGeneral(tech, effect, valueText, combinableTarget, additionalPreTargetText=additionalPreTargetText, additionalPostTargetText=additionalPostTargetText, percentileSuffix=percentileSuffix, flatSuffix=flatSuffix)
    return inner

DATA_SUBTYPE_HANDLERS: Dict[str, Callable[[ET.Element, ET.Element], Union[EffectHandlerResponse, List[EffectHandlerResponse]]]] = {
    "damagebonus":dataSubtypeHelper("amount", additionalPreTargetText="Damage Bonus against", flatSuffix="x", combinableAttribute="unittype", combinableAttributeFormat=common.getDisplayNameForProtoOrClass),
    "hitpoints":dataSubtypeHelper("amount", combinableString="Hitpoints"),
    "los":dataSubtypeHelper("amount", combinableString="LOS"),
    "maximumvelocity":dataSubtypeHelper("amount", combinableString="Movement Speed"),
    "trackrating":dataSubtypeHelper("amount", combinableAttribute="action", additionalPreTargetText="Track Rating"),
    "armorvulnerability":dataSubtypeHelper("amount", combinableAttribute="armortype", additionalPreTargetText="Damage Vulnerability to", relativityModifier=relativityModifierArmor),
    "damage":dataSubtypeDamageHandler,
    "workrate":dataSubtypeWorkrateHandler,
    "godpowercostfactor":dataSubtypeHelper("amount", combinableString="God Power recast cost"),
    "godpowerroffactor":dataSubtypeHelper("amount", combinableString="God Power recharge time"),
    "resourcereturn":dataSubtypeResourceReturnHandler,
    "buildpoints":dataSubtypeHelper("amount", combinableString="Build Time"),
    "actionenable":dataSubtypeActionEnableHandler,
    "cost":dataSubtypeHelper("amount", combinableAttribute="resource", combinableAttributeFormat=icon.resourceIcon, additionalPreTargetText="Cost"),
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
    elif effectType in ("setname", "textoutput"):
        pass
    else:
        print(f"Warning: Unknown effect type {effectType} on {techName}")
    return None


def processTech(tech: ET.Element):
    effects = tech.findall("effects/effect")
    responses: List[Union[None, EffectHandlerResponse]]= []
    for effect in effects:
        response = processEffect(tech, effect)
        if response is not None:
            if isinstance(response, list):
                responses += response
            else:
                responses.append(response)
    
    combineHandlerResponses(responses)
    strings = [response.toString() for response in responses]
    output = "\\n".join(strings)
    if len(output) == 0: # Need to output something or we get <MISSING> if empty
        output = " "
    return output


def generateTechDescriptions():
    proto = globals.dataCollection["proto.xml"]
    techtree = globals.dataCollection["techtree.xml"]

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