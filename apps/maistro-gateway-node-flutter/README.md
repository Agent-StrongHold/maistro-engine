# Gateway node — Flutter (iOS + Android)

Flutter **node** companion for the **gateway** product. Requirements and tests: **[`docs/specs/SPEC-179-flutter-gateway-node.md`](../../docs/specs/SPEC-179-flutter-gateway-node.md)**.

**Reference:** native node apps and shared kit live in the **gateway product repository** (not vendored here). Use that tree for wire-protocol details.

## First-time setup

Install [Flutter](https://docs.flutter.dev/get-started/install) and run `flutter doctor`.

Create the project **into this directory name** from the repo root:

```bash
cd "$(git rev-parse --show-toplevel)/apps"
flutter create maistro_gateway_node_flutter --org com.maistro --project-name maistro_gateway_node
mv maistro_gateway_node_flutter maistro-gateway-node-flutter
```

If `maistro-gateway-node-flutter/` already contains `pubspec.yaml`, only run:

```bash
cd "$(git rev-parse --show-toplevel)/apps/maistro-gateway-node-flutter"
flutter pub get
flutter test
```

Commit generated platform metadata; do not commit `build/` or `.dart_tool/`.

## Configuration

Discovery service type and any path prefixes must come from **`--dart-define`**, CI env, or in-app settings—**not** from hardcoded vendor strings in committed sources.
