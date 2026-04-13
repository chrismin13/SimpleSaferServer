## HDSentinel Linux Assets

This directory stores vendored HDSentinel Linux console archives used by `install.sh`.

Bundled files:

- `hdsentinel-linux-amd64.zip`
- `hdsentinel-linux-arm64.zip`
- `hdsentinel-linux-armv7.gz`

Source URLs:

- `https://www.hdsentinel.com/hdslin/hdsentinel-020c-x64.zip`
- `https://www.hdsentinel.com/hdslin/hdsentinel-armv8.zip`
- `https://www.hdsentinel.com/hdslin/hdsentinel-armv7.gz`

Why these files are vendored:

- The installer can run even when outbound access to the vendor host is blocked.
- The archive names are normalized so install logic stays simple across architectures.
- Keeping all architecture variants together avoids accidental partial updates later.