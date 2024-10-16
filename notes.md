# Primary purpose

This is pitched at people who know roughly what things do and don't take the time to stop and read tooltips unless they actively want to know something specific.

So, lots of detail. It'll be a bit overwhelming for people who don't know the game, but the base tooltips are probably better for getting an initial understanding of what everything in the game sort of does without getting hung up on specifics.

# Units

## Common stuff

The unit rollover importantly doesn't show ingame very easily (mouseover selection icon is the easiest way), only at train time. This means you don't always have the normal UI available to reference at the same time and so displaying duplicate info is potentially useful.

Try bullet points in this (as Wonder age). I might be able to get:
* [Unit Classes and categories]
* LOS Speed ?EHP-hack EHP-pierce
* Basic description and description of actions
* Extra notes

For not-very-useful stuff I can expand into the history.
That's also where Gullinbursti's gigantic mass of text is going, I guess.

## Unit abilities

In the end this is just describing actions, and most special abilities are just actions with charge dependence or are defined by some other flat tags in the proto data.

# Godpowers
* God power recharge, recast time, +cost per cast
* Additional details on a per-power basis

# Techs

Two options:
* Destroy everything vanilla, rely on people turning off the game's advanced tooltips and make my own descriptions for every tech in the game
* Keep the vanilla tooltip generation, except add in the stuff it missed and comment every time it says something misleading

The former is the more complete option. I might half build support for the latter in case turning off advanced tooltips turns out to do something else undesirable...
I also need to change relic text for that.


# TODO

Major god tooltips

Winged messenger respawning time

Meteor friendly fire multiplier?

Age up text output (myth unit/godpower)

Relics with missing text (eg chariot of cybele)

Scorpion man spec should probably merge projectile count

Time shift text

Grey colourise all the vanilla tooltip effect strings so they look clearly different in case people want to keep them on