import globals
import datetime
import action

NEW_TIPS = [
    f"Mods do not update automatically - check the mod manager page from time to time to see if there are updates for any!\\n\\nThis version of Advanced Tooltips was built on {datetime.datetime.now().strftime('%d %b %y')}.",
    f"Most melee attacks slow targets to {100*(action.STANDARD_SNARE['rate']):0.3g}% of their normal movement speed for {action.STANDARD_SNARE['duration']:0.3g} seconds.",
    "Dead animals lose 1 food every 5 seconds.",
    "Unfinished buildings take double damage from most sources.",
    "A player's ingame score is approximately their total unspent resouces, plus the total resource costs of all their units in the world, completed buildings, researched and queued technologies.",
    "Most damage over time effects inherit the damage bonuses of the action that applied them. For example, a Wadjet's poison does more damage to Myth Units and less damage to Heroes.",
]

def generateLoadTips():
    #STR_LOADINGSCREEN_TIP_14 - AI assist
    #STR_LOADINGSCREEN_TIP_15 - controller
    #STR_LOADINGSCREEN_TIP_28 - TC support population
    #STR_LOADINGSCREEN_TIP_31 - one boat per fish
    #STR_LOADINGSCREEN_TIP_34 - GP myth unit bolt immunity
    #STR_LOADINGSCREEN_TIP_38 - minor god techs cheaper
    #STR_LOADINGSCREEN_TIP_42 - lore
    #STR_LOADINGSCREEN_TIP_43 - lore
    #STR_LOADINGSCREEN_TIP_47 - monuments give favor and god specific bonuses
    tipsToChange = [14, 15, 28, 31, 34, 38, 42, 43, 47]

    for index, tip in enumerate(NEW_TIPS):
        strid = f"STR_LOADINGSCREEN_TIP_{tipsToChange[index]}"
        globals.stringMap[strid] = tip

    