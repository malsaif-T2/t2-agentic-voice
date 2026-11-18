"""The lean Saad (D-113, the owner's ruling of 2026-11-17, "Lean next to it"): a model-led flight
agent beside today's scripted one, the same airline, trip state, persona, words and page, chosen
by the app's setting (`FLIGHT_VOICE_AGENT`, settings.py).

The model leads: its short instructions and a calendar in its prompt (prompt.py), its tools of
plain data in and plain data out with no scripted `say` (`find_flights`, `choose_flights`,
`book_trip` where the line books, and today's `traveler_profile`), the model resolving the
caller's dates and picks itself. The tools read flights through the flight data port
(flight_voice/flight_data/, plan 011; deps.py), the mock airline behind it today, and the trip
keeps the offers as the caller heard them (draft.py). The code keeps only what the owner ruled: facts only from tools (the library's output
guard and plain speech stay on), and one booking check (booking_check.py) before `book_trip`
writes to the mock airline's store: the trip complete, its total said in a reply that played up
to it, and the caller speaking after that reply. The lean agent declares no action: `book_trip`
is a tool that writes, which departs from the library's "only actions act" design for the mock
airline alone, by the owner's ruling (docs/design/flight-voice-agent.md, section 13).
"""
