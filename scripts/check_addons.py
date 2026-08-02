#!/usr/bin/env python3
"""Check invariants across the add-on config.yaml files.

`config.yaml` is deliberately excluded from `gpsd2mqtt_beta/rsync.sh`, because the
slug, name, version and image must differ between the two channels. The cost is
that schema changes have to be mirrored by hand, and nothing used to notice when
that was forgotten -- `mqtt_state` was removed from beta in 2026.8.0 and the prod
changelog said so, but it sat in the prod schema for another release.

Run from the repository root, or with the repository root as the only argument.
"""

import pathlib
import re
import sys

import yaml

# The two channels of the same add-on. Everything a user configures must be
# identical between them; only packaging differs.
MIRRORED_CHANNELS = ("gpsd2mqtt", "gpsd2mqtt_beta")

# Keys that must match across the channels above.
MIRRORED_KEYS = ("schema", "options")

# The beta channel's version carries a bN suffix. Nothing else may.
BETA_SUFFIX = re.compile(r"b\d*$")


def load_addons(root):
    """Return {slug: config} for every add-on directory under root."""
    addons = {}
    for config_path in sorted(root.glob("*/config.yaml")):
        with open(config_path) as config_file:
            addons[config_path.parent.name] = yaml.safe_load(config_file)
    return addons


def check_mirrored_keys(addons, errors):
    """The user-facing configuration must be identical across both channels."""
    present = [slug for slug in MIRRORED_CHANNELS if slug in addons]
    if len(present) < 2:
        return

    first, second = present[0], present[1]
    for key in MIRRORED_KEYS:
        left = addons[first].get(key)
        right = addons[second].get(key)
        if left == right:
            continue

        left_keys = set(left or {})
        right_keys = set(right or {})
        for extra in sorted(left_keys - right_keys):
            errors.append(f"{first}/config.yaml has `{key}.{extra}`, {second} does not")
        for extra in sorted(right_keys - left_keys):
            errors.append(f"{second}/config.yaml has `{key}.{extra}`, {first} does not")
        for shared in sorted(left_keys & right_keys):
            if (left or {})[shared] != (right or {})[shared]:
                errors.append(
                    f"`{key}.{shared}` differs: "
                    f"{first}={(left or {})[shared]!r}, {second}={(right or {})[shared]!r}"
                )


def check_versions(addons, errors):
    """Release tags come from `version:` and are repository-wide, so they must be unique."""
    seen = {}
    for slug, config in addons.items():
        version = str(config.get("version", ""))
        if not version:
            errors.append(f"{slug}/config.yaml has no version")
            continue

        # Two add-ons at the same version would collide on the GitHub release tag
        # created by .github/workflows/release.yaml, and the second would be
        # silently skipped.
        if version in seen:
            errors.append(
                f"{slug} and {seen[version]} both declare version {version}; "
                "release tags are repository-wide and must be unique"
            )
        seen[version] = slug

        # This is what keeps the uniqueness above true by construction rather
        # than by luck: beta always carries the suffix, prod never does.
        is_beta_channel = slug.endswith("_beta")
        has_beta_suffix = bool(BETA_SUFFIX.search(version))
        if is_beta_channel and not has_beta_suffix:
            errors.append(f"{slug} version {version} must end in a bN suffix")
        if not is_beta_channel and has_beta_suffix:
            errors.append(f"{slug} version {version} must not end in a bN suffix")


def check_images(addons, errors):
    """Each add-on publishes to its own image repository."""
    seen = {}
    for slug, config in addons.items():
        image = config.get("image")
        if not image:
            continue
        # Prod pointed at the beta image repository for eight months in 2025
        # because both folders build identical code, so the mislabelled image
        # worked and nobody noticed.
        if image in seen:
            errors.append(
                f"{slug} and {seen[image]} both publish to {image}"
            )
        seen[image] = slug


def main():
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    addons = load_addons(root)

    if not addons:
        print(f"No add-on config.yaml found under {root.resolve()}", file=sys.stderr)
        return 1

    errors = []
    check_mirrored_keys(addons, errors)
    check_versions(addons, errors)
    check_images(addons, errors)

    if errors:
        print("Add-on consistency check failed:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Checked {len(addons)} add-on(s): {', '.join(sorted(addons))} - all consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
