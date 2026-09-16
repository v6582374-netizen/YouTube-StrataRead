# macOS release credential checklist

The first release needs a distribution identity distinct from a personal Apple Development certificate.

## External prerequisites

1. The releasing Apple account is enrolled in the Apple Developer Program and has access to the selected team.
2. That team has a valid **Developer ID Application** certificate for the release identity.
3. The team can notarize software through either an App Store Connect API key or a dedicated notarization credential.

## GitHub repository configuration

The release workflow will need restricted repository secrets for the Developer ID certificate bundle and its password, the selected notarization credential, Apple team identity, and the Tauri updater private key plus its password. Their values belong in GitHub Actions secrets; they never enter the repository, issue tracker, workspace data or chat.

The updater public key is safe to include in the application configuration. Generate the updater key only once the release workflow exists, then keep its private key and password in the restricted release-secret set.

## Current audit

This machine has one personal **Apple Development** signing identity. It is not a Developer ID Application identity. The repository currently has no macOS release or updater secrets configured.
