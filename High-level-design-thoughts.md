**Notes on input data**

The high-level idea is that we should be able to encode the gameplay in basically just actions and images, as this is 
how the game is played by people. We can probably load in a gen3_extractor as a load-in initialiser for a given
game-state, as well as a description of available buttons to press and what they usually do; this is the bare-bones
approach, in terms of data flow. The LLMs output would jsut be 'a', 'b', 'start', 'R', 'L' etc., or 'SCREENSHOT' to
retrieve image data.

image data could even be translated into text using a VLM. Otherwise, we could just pump the image encodings directly
into the chat.

a more-involved visual version would be a screen shot after every move... not unreasonable? well there are 50k potential moves, so
this is a lot of data.

a more-involved text approach would be to calculate all end-actions available to the user (rather than button-presses), and
then end-actions correspond to several button presses. This saves token space and simplifies/clarifies the intended action,
at the cost of a complex interface between LLM and action-space. The avaiI madelable actions to the user should be, basically,
the same every time - things like "review stats of pokemon [1]", "review moves of pokemon [2]", "swap pokemon [1] and [4]" if
in the normal game, or "head [three] moves [up], and [five] steps [right]". Also "screenshot" would be useful.

if in the pokemon box, "move pokemon [2] in [the team] to [box 19]", etc.

I like the more-involved text approach; we should find all possible game states: in the world (inside or outside), in a pokemon box,
in a conversation, in a battle, party menu, bag menu, buying screen, healing, cutscene, receiving a pokemon/item,
evolution sequence (can press b to cancel - should cancel this ahead of time), fly/surf destination select, safari
zone, game corner, etc.

I think the best way is a joint image-caption description of the game. Captioning can be automatically generated based on mGBA's
sprite-detection, and in-game data relating to coordinates and map locattion. For example, "We are currently on Route 224, placed
in coordinates [x] and [y], approximately [a] distance from Cerulean City and [b] distance from Whatever town. There are three trainers
in the local vicinity: a hiker 10 steps up and three steps right, looking to the left; a girl 2 steps up four steps left, looking to the right,
and a boy 1 step below and 0 steps left of you."

Therefore, every game is defined by an end-to-end script and a folder of screenshots.

**Notes on battle bot**

Probably should have a separate trainable battles bot that we optimise before getting into the story.
Long-term strategic planning is something we want to train in our models, but that will be completely thrown
if we cannot battle effectively. That being said, clearly, strategy and tactics must interact. If we are strategising
to have a certain team, with certain moves and evolutions available to us, for a gym fight in the future, then that has
a non-trivial interaction with how I fight five-trainers before the gym.

The high-level strategy informs the tactics, the outcome of tactical battles updates the strategy. 

One can observe this by watching any nuzlocking youtube video, but especially PChal. He has a very clear strategy: have
certain pokemon available for timepoint X in the distant future. This allows him to appropriately prepare for fights in 
short-term. Sometimes, unexpected things happen, and that forces adaptation of strategy. But at no point, really, does a
tactical update result in a strategic update. PChal is skilled at battling in a general nuzlocking sense,
and so rarely 'realises' tactical shifts that significantly adjust his strategy. More often, he realises the guiding 
context within a fight was incorrect. 
