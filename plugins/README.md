# JEEV plugins

Installed plugins live under `plugins/installed/`.
Temporary GitHub downloads are placed under `plugins/downloads/`.
The manager requires a `jeev.plugin.json` manifest before a repository can be installed.

For a plugin to be automatically discoverable by JEEV, its repository should contain:

- `jeev.plugin.json`
- the manifest's `entrypoint` file
- optional `requirements.txt`

JEEV validates the manifest and declared permissions before installation.
Plugins requesting high-risk permissions are not silently activated.

