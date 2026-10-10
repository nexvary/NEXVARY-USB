# Code signing policy

## Current status

The project is seeking eligibility review for free code signing from SignPath Foundation. Acceptance, a signing certificate, Microsoft driver approval, and a trusted Windows driver installation have not been obtained. Existing development driver downloads are unsigned. This page does not claim sponsorship or an active SignPath subscription.

## Intended review and release policy

Repository maintainers control source and build changes. The repository owner, Alaa Mohamed (GitHub account nexvary), is the intended release signing approver. Each release signing request requires explicit maintainer approval, build provenance tied to the exact source commit, and verification that signed artifacts match the approved build. Signing access is to be restricted to reviewed release workflows; no credentials or private signing keys belong in source or downloadable artifacts. SignPath account roles and MFA configuration remain to be verified if the application is accepted.

The Windows virtual reader is a modified GPL-3.0-or-later vsmartcard component pinned by the build scripts. Its eligibility under SignPath's upstream/fork rules must be confirmed by SignPath. Signing the application installer does not prove signing or Windows acceptance of DLL/INF/CAT driver packages. Driver installation, reader enumeration, card connection, and physical APDU tests remain separate gates.

## Privacy

Modem identifiers and card diagnostics are processed locally. Reports and exports can contain personal device/card information; sharing an export is a user action. The virtual reader connects over loopback only. Optional broker/network connections are explicitly configured by the operator and use the documented authorization and consent controls. A release must disclose any additional data transfer before enabling it. No authentication secrets are to be included in signing artifacts, telemetry, or logs.

## Licensing

Original project-owned material is GPL-3.0-or-later. Third-party notices and license terms are retained; see [license scope](LICENSE-SCOPE.md).

## Application reference

https://signpath.org/apply
https://signpath.org/terms
