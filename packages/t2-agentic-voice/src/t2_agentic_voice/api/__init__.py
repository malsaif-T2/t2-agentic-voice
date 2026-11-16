"""api: the outermost layer, the backend's HTTP surface and composition root: it serves `t2v/1`
(a call's join and its WebRTC offer, handed to voice, which answers it), the health and ready
routes, the reference client (`t2v-client.js`), on a dev machine the dev page and the test
console, and for an app's own demo page the access-code token route and the page's headers;
an app's widget is the app's to serve. It builds the adapters from the settings and
injects them into the layers below, maps every error to one shape for its transport (GP-19),
serves a runtime (`serve`, the sidecar) and gives the `t2v` command.

It may import every other layer. ARCHITECTURE.md's "Layers" maps the layers and what each owns;
each module's docstring says what it holds.
"""
