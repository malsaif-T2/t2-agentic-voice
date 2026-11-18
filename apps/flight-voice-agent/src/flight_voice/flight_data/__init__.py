"""Flight data behind one port (plan 011): the lean agent reads flights from a source it does
not know, the mock airline, recorded answers or SerpApi's Google Flights, so a proper provider
can take its place later.

- `model.py`: what a source answers, the same for every source. A `Place` (a city or one
  airport, its airports searched together), a `Carrier`, the `Segment`s of an `Offer` with its
  `Layover`s, and its price as `Money` in whole Saudi riyals, for all its travelers on that leg
  alone. Times are each airport's local time with no zone. An offer's id is its flights' codes
  and its first day (`SV1020-2026-11-19`, `SV3079+SV8607-2026-11-19`).
- `queries.py`: what is asked and answered. One leg on one day (`OfferQuery` to `DayOffers`,
  whose `status` is `ok`, `no_flights`, or the mock's `not_served` and `cabin_not_sold`), and
  the lowest price of each day of a span (`SpanQuery` to `DayFares`; a day that could not be
  checked is `known=False`).
- `port.py`: the `FlightData` port (`day`, `days`, `nearest`, `last_day`, `aclose`), the
  `Places` a caller may name (`find`, `get`, `home`, `served`), and the one error a source
  raises when it could not answer, `FlightDataUnavailableError`: unknown, never "no flights";
  `lasting` for a rejected key or a rate limit; its details never hold a key, a URL, the
  request's params or a body. `trip_days` searches both legs of a trip at once: a failed return
  comes back as a value beside the outbound, a failed outbound is raised, and a cancellation
  propagates.
- `links.py`: a leg's booking link (`leg_link`, D-126), the Google Flights search for that leg,
  one way, on its day, filtered to its marketing carrier(s), from which the caller books on the
  airline's site.
"""
