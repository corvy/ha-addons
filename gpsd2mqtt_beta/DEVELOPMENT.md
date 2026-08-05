# Development and release process

Maintainer notes. Not shipped to users — this file is excluded from `rsync.sh`.

`gpsd2mqtt_beta/` and `gpsd2mqtt/` are two add-ons sharing one codebase. Changes
always flow **beta → prod**, never the other way. Beta is `stage: experimental`
and is only for testing; prod is what people install.

## What is shared and what is not

`rsync.sh` copies everything from beta to prod **except** the files in
`exclude_list.txt`:

| File | Shared? |
|---|---|
| `gpsd2mqtt.py`, `run.sh`, `Dockerfile`, `apparmor.txt`, `DOCS.md`, `translations/` | shared — edit in beta only |
| `config.yaml` | per-channel (different slug, name, version, image) |
| `CHANGELOG.md` | per-channel (separate release histories) |
| `README.md` | per-channel |
| `DEVELOPMENT.md`, `rsync.sh`, `exclude_list.txt` | beta only |

**Never edit the shared files in `gpsd2mqtt/` directly** — the next `rsync.sh`
will overwrite them.

## 1. Make and release a beta

1. Edit files in `gpsd2mqtt_beta/`.
2. **Bump `version:` in `gpsd2mqtt_beta/config.yaml`** — e.g. `2026.8.0b1` →
   `2026.8.0b2`. This is not optional, see "Version bumps are what ship code".
3. Add a `CHANGELOG.md` entry in the categorised format (see below).
4. Commit, push to `dev`, open a PR against `main`.
   The PR runs Builder with `--test`: it builds every arch but publishes
   nothing. This is where a broken Dockerfile or a rotted package pin shows up.
5. Merge the PR. Two things now happen automatically:
   - Builder publishes `ghcr.io/corvy/{arch}-addon-gpsd2mqtt-beta:<version>`
   - Release creates the GitHub release, marked as a prerelease
6. Wait a few minutes — the Supervisor re-reads add-on repositories on a timer,
   so the update will not appear in Home Assistant instantly. Then update the
   beta add-on and test it on real GPS hardware.

## 2. Promote to prod

Only once the beta has actually run on hardware.

1. `cd gpsd2mqtt_beta && ./rsync.sh`
2. Bump `version:` in `gpsd2mqtt/config.yaml` — the same number without the
   `bN` suffix, e.g. `2026.8.0`.
3. Write the `gpsd2mqtt/CHANGELOG.md` entry. This is **cumulative**: it covers
   everything since the last prod release, including work spread over several
   betas. Write it for someone who has never heard of the beta channel.
4. Commit, PR, merge. Builder publishes
   `ghcr.io/corvy/{arch}-addon-gpsd2mqtt:<version>`, and Release creates the
   GitHub release.
5. Confirm the image tag actually exists before telling anyone:
   https://github.com/corvy?tab=packages

## Rules worth remembering

**Version bumps are what ship code.** The Builder only runs when
`config.yaml`, `Dockerfile`, `build.yaml` or `rootfs` change — see
`MONITORED_FILES` in `.github/workflows/builder.yaml`. Editing `gpsd2mqtt.py`
or `run.sh` alone triggers **no build**, and the change never reaches anyone.
Since `version:` lives in `config.yaml`, bumping it is what both triggers the
build and tags the image. This is deliberate: it means an image can never be
silently republished over an existing tag.

**`image:` must never be swapped between channels.** Prod is
`ghcr.io/corvy/{arch}-addon-gpsd2mqtt`, beta is the same with `-beta`. If prod's
image name is ever changed, the version must be bumped in the same commit —
otherwise Home Assistant looks for a tag that does not exist in the other
repository. (This happened in Dec 2025 and went unnoticed for eight months.)

**The prod changelog never mentions beta.** Beta versions are a testing
mechanism, not part of the users' release history. Beta-only changes — like
`stage: experimental` — stay in the beta changelog.

**Pushing `dev` publishes nothing.** Builder only reacts to `main`. A push to
`dev` runs no workflows at all; the PR and the merge are what matter.

## Changelog format

Newest entry visible, everything older folded into one `<details>` block:

```markdown
# Changelog

## [2026.8.0] - 2026-08-01

### Changed
- ...

### Fixed
- ...

### Added
- ...

### Removed
- ...

<details>
<summary>Older changes</summary>

## [2025.12.0] - 2025-12-10
- ...
</details>
```

Use only the sections you need. Versions are calendar-based: `YYYY.M.P`, with
betas adding `bN`.

## Version numbers

The month is the month of *release*, and the beta number names the prod release it
will **become** — not the one already shipped. So after `2026.8.0` goes out, the
next beta cycle opens at `2026.8.1b1` and promotes to `2026.8.1`. If a cycle slips
into the next month, both numbers move together.

The release tag is the `version:` string verbatim, so the format here is the format
on the releases page. Two consequences:

- **Do not zero-pad the month.** `2026.8.1`, not `2026.08.1`. The `2026.08.0` tag is
  a one-off from before releases were automated; it is left alone because it is
  published, but nothing should match it.
- **No two add-ons may share a version.** Tags are repository-wide, so a collision
  would silently skip the second release. The `bN` suffix is what keeps beta and
  prod apart, and `scripts/check_addons.py` enforces all of this in CI.

**The changelog is the source of truth for GitHub releases.**
`.github/workflows/release.yaml` watches `main` for a changed `version:` in any
add-on's `config.yaml`. When it sees one it creates the GitHub release: tag and
title from the version, body from that add-on's newest changelog entry, marked
as a prerelease when the version ends in `bN`. You never write release notes by
hand, and the release can never drift from the changelog.

Two things follow from this:

- **Write the entry properly in the PR** — it is what users read on the
  releases page, not just in the add-on.
- **Collapsing is manual.** When adding an entry, move the previous one below
  the `<details>` line so only the newest stays visible. It is a two-line edit
  and shows up in the PR diff.

Nothing is ever committed back to `main` by CI.

## Pinning policy

Keep pins and repository overrides to a minimum, and stay on standard Alpine
releases wherever possible. Every pin is something that rots later. What exists
today, and what would remove it:

| Pin | Why it exists | How it goes away |
|---|---|---|
| `gpsd>=3.27.1` from **edge** | Stable is on 3.26.1, which has CVE-2025-67268 and CVE-2025-67269 | Alpine stable reaching 3.27.1; then drop the `--repository` override too |
| `py3-paho-mqtt<2` | `gpsd2mqtt.py` uses the v1 callback signatures | Not by an Alpine bump: every branch holds 1.6.1 deliberately, and 2.x is proposed as a separate `py3-paho-mqtt2` aport. Switching means that package or pip, plus the 2.x `CallbackAPIVersion` API |
| `gpsdclient==1.3.2` (pip) | No Alpine package exists | An Alpine package appearing |

Python is **not** pinned — it follows the Alpine base image, so nothing may
hardcode a python minor version. `run.sh` logs both the python and gpsd versions
at startup, so the add-on log shows what is actually running.

Check what Alpine currently ships:
https://pkgs.alpinelinux.org/packages?name=gpsd&repo=main

## Verifying a release

- Add-on log shows the expected `gpsd` version at startup
- MQTT connects and discovery is published
- The periodic summary reports a fix with a sensible satellite count
- `device_tracker.gps_location` and `sensor.gpsd_service_sky_data` update
- Stopping the add-on is quick — a slow stop means SIGTERM is not reaching the
  script and it is being SIGKILLed
