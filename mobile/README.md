# KPIMaster Mobile

React Native + TypeScript mobile app for KPIMaster personas.

## Related Documentation

- [Documentation Hub](../docs/README.md)
- [Project README](../README.md)
- [Demo and Validation Runbook](../docs/demo-and-validation-runbook.md)
- [Persona Scenario Test Matrix](../docs/persona-scenario-test-matrix.md)

## What It Supports

- Secure login, logout, and session restore
- Role-aware mobile navigation for client, vendor, developer, PM/delivery lead, executive, and admin users
- Project selector with persisted project scope
- Dashboard summary, sprint KPI overview, ticket list/detail, blocker actions, repository mismatch review, integration state, assistant chat, and profile/logout
- WebSocket project feed that refreshes loaded data when backend events arrive
- Loading, empty, error, refresh, read-only, and network-failure states

## Local Setup

```bash
cd mobile
cp .env.example .env
npm install
EXPO_PUBLIC_API_BASE_URL=http://localhost:18000 npm run start
```

Use these backend URLs depending on where the app runs:

- iOS simulator: `http://localhost:18000`
- Android emulator: `http://10.0.2.2:18000`
- Physical device: `http://YOUR_LAN_IP:18000`

## Quality Checks

```bash
npm run typecheck
npm run lint
npm run test
npx expo export --platform android --output-dir dist-android
```

## APK Generation

Cloud/internal APK build with Expo Application Services:

```bash
cd mobile
npm run build:android:apk
```

Local APK build, useful for CI machines with Android SDK installed:

```bash
cd mobile
export EXPO_PUBLIC_API_BASE_URL=http://YOUR_LAN_IP:18000
npm run prebuild:android
cd android
JAVA_HOME=/usr/lib/jvm/java-21-jdk \
ANDROID_HOME=$HOME/Android/Sdk \
ANDROID_SDK_ROOT=$HOME/Android/Sdk \
NODE_ENV=production \
./gradlew assembleRelease
```

For Android emulator builds, use `EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:18000`.
For a real phone, use the backend machine LAN address, for example `http://192.168.x.x:18000`.

The generated APK is written to:

```text
mobile/android/app/build/outputs/apk/release/app-release.apk
```

This project is managed by Expo. The generated `android/` directory is intentionally ignored because it can be recreated with `npm run prebuild:android`.

## Demo Personas

Standard seed users:

- `horizon_admin` / `ChangeMe123!`
- `horizon_exec` / `ChangeMe123!`
- `retail_pm` / `ChangeMe123!`
- `hexadev_admin` / `ChangeMe123!`
- `novaforge_delivery` / `ChangeMe123!`
- `alice_account` / `ChangeMe123!`
- `e2e` / `E2ePassword1!`

## Architecture

- `src/services`: typed API client, storage, adapters, assistant logic
- `src/state`: auth/session and project-scope providers
- `src/hooks`: dashboard aggregation and WebSocket refresh
- `src/domain`: persona and backend contract types
- `src/screens`: role-aware mobile screens
- `src/components`: reusable mobile UI primitives
- `assets`: branded icon, adaptive icon, and splash screen assets
