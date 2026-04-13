## HDSentinel Linux Assets

This directory stores vendored HDSentinel Linux console archives used by `install.sh`.

Bundled files:

- `hdsentinel-linux-amd64.zip`
- `hdsentinel-linux-arm64.zip`
- `hdsentinel-linux-armv7.zip`

Source URLs:

- `https://www.hdsentinel.com/hdslin/hdsentinel-020c-x64.zip`
- `https://www.hdsentinel.com/hdslin/hdsentinel-armv8.zip`
- `https://www.hdsentinel.com/hdslin/hdsentinel-armv7.gz`

Why these files are vendored:

- The automated installer only uses the files in this directory, so HDSentinel never gets downloaded from the vendor site during `install.sh`.
- Manual installs can still fetch upstream binaries from the vendor URLs when someone wants to verify or compare them directly.
- The archive names are normalized so install logic stays simple across architectures.
- The ARMv7 vendor download is a `.gz`, so the repo repackages it as `hdsentinel-linux-armv7.zip` to avoid architecture-specific manual-install steps later.
- Keeping all architecture variants together avoids accidental partial updates later.
