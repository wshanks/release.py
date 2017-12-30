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

Config
======
Config file is a yaml file with a `version_strings` block containing a list of mappings containing `path` and `pattern` entries. `path` is a file path relative to the git root directory. `pattern` is a Python regular expression with a group named `release` (i.e. something like `(?P<release>\d+\.\d+\.\d+[ab]\d+)`. That file will be searched line by line for that pattern and when found the `release` will be replaced with the new release version string.

The first entry in `version_strings` list is used to determine the current version when sanity checking. If `RELEASE` is lower than the current version, an exception is raised. Also, if the current version is lower than the latest tagged release, an exception is raised. This check is there to prevent accidentally releasing from an old branch.

The config can also contain a `github` mapping with `user`, `repo`, `token` and `assets` entries. `assets` is a list mappings with `path` and `type` entries. These file paths relative to the git root will be attached to a GitHub release for `RELEASE`. The `type` is the MIME type as required by GitHub. `user` and `repo` are the user and repo to create the release for on GitHub. `token` is a text file containing the authorization token required to use the GitHub API for that repo.