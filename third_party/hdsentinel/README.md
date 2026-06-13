## HDSentinel Linux Assets

This directory stores vendored HDSentinel Linux console archives used by `install.sh`.

Bundled files:

- `hdsentinel-linux-amd64.zip`
- `hdsentinel-linux-arm64.zip`

Source URLs:

- `https://www.hdsentinel.com/hdslin/hdsentinel-020c-x64.zip`
- `https://www.hdsentinel.com/hdslin/hdsentinel-armv8.zip`

Why these files are vendored:

- The automated installer only uses the files in this directory, so HDSentinel never gets downloaded from the vendor site during `install.sh`.
- Manual installs can still fetch upstream binaries from the vendor URLs when someone wants to verify or compare them directly.
- The archive names are normalized so install logic stays simple across supported 64-bit architectures.
