# Run Edison as one self-hosted web instance

**Status: accepted.** Supersedes the desktop-only delivery of ADR 0004 and ADR 0011.

The YouTube workbench needs to work around the clock, which a laptop cannot. We therefore run the whole of Edison as a single web instance on a server the owner controls, reached by browser from every device, and retire the desktop app instead of keeping two copies. Two copies would double YouTube API quota and model spend and split every library.

The server is addressed by raw IP with no domain. TLS uses Let's Encrypt short-lived IP certificates, and access requires a login session rather than the desktop launch token. The agent's shell and file tools act on the server, so they run as an unprivileged account confined to its own directory. Nothing in the instance may reach the proxy panel that shares the host.

## Consequences

- Google does not accept a raw IP as an OAuth redirect, so the first YouTube authorization happens on a trusted device and is handed to the server once. The server then refreshes it itself.
- Desktop-only capabilities are dropped rather than emulated: local dictation (use the device's own voice input), visible browser automation and local models. Course notifications move to browser push.
- The host has 2.5 GB of memory, so continuous YouTube preparation takes priority over optional heavy components.
