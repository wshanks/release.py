release.py
----------
Script to help with marking and pushing a new release in git.

    python release.py -h
    usage: Mark git release [-h] --release RELEASE --config CONFIG

    optional arguments:
    -h, --help            show this help message and exit
    --release RELEASE, -r RELEASE
                            Release version string
    --config CONFIG, -c CONFIG
                            Config file


Script does the following:
1. Get last version from git tags.
2. Get current version from first `version_strings` entry in `CONFIG`.
3. Compare last and current version to `RELEASE` to make sure order is correct.
4. Change `version_strings` paths/patterns to use new `RELEASE`.
5. Commit changes with message about new release version and tag the commit with the version number.
6. Run `make clean` and `make`.
7. Push the new release commit and tag.
8. If `github` is configured in `CONFIG`, convert tag to a GitHug release and upload assets to it.
9. Bump `version_strings` again to an alpha version one micro version ahead of `RELEASE` and make a new commit with this version string change.