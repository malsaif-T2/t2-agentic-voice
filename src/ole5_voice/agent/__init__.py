"""agent: the talker, the model that speaks, asks, and calls tools.

Its prompts, its few tool definitions, the language it replies in, and one turn: the user's
words in, a reply and tool calls out. It never words an outcome itself: actions do, and the
output guard checks every sentence against the call's record of completed actions.
"""
