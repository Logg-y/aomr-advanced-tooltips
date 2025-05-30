import globals
from typing import Union
import common

ICON_SIZE = 20
BULLET_POINT = "•"
BULLET_POINT_ALT = "◦"

def generalIcon(path: str) -> str:
    # Some icons aren't displaying properly
    # Backslashes to front slashes?
    return f"<icon=\\\"({ICON_SIZE})({path.replace(chr(92), '/')})\\\">"

def damageTypeIcon(damageType: str):
    return f"<icon=\\\"({ICON_SIZE})(resources/in_game/stat_{damageType.lower()}_dmg.png)\\\">"

def armorTypeIcon(damageType: str):
    return f"<icon=\\\"({ICON_SIZE})(resources/in_game/stat_{damageType.lower()}_armor.png)\\\">"

def resourceIcon(resource: str):
    return f"<icon=\\\"({ICON_SIZE})(resources/in_game/res_{resource.lower()}.png)\\\">"

def iconNumProjectiles():
    return generalIcon('resources/in_game/stat_projectile.png')

def iconRof():
    return generalIcon("resources/in_game/stat_rof.png")

def iconAoe():
    return generalIcon("resources/in_game/stat_area.png")

def iconTime():
    return generalIcon("resources/in_game/stat_time.png")

def iconRange():
    return generalIcon("resources/in_game/stat_range.png")

def iconSpeed():
    return generalIcon("resources/in_game/stat_speed.png")

def iconLos():
    return generalIcon("resources/in_game/minimap/Icon_Reveal1.png")

def iconPop():
    return generalIcon("resources/in_game/res_pop.png")
    
def iconUnitClass(targetType: str) -> Union[None, str]:
    "Return the icon for damage multipliers vs a given target unit type, or None if one isn't defined."
    iconNameMatch = globals.unitTypeData.get(targetType)
    if iconNameMatch is not None:
        iconName = common.findAndFetchText(iconNameMatch, "icon", None)
        if iconName is not None:
            return generalIcon(iconName)
    return None