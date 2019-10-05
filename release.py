#!/usr/bin/env python3
'''Cut new release'''
import argparse
from functools import total_ordering
import os
import re
import shutil
import subprocess
import tempfile

import requests
from uritemplate import expand
import yaml


VERSION_FMT = (r'^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<micro>\d+)'
               r'(?P<prerelease>(b|(beta)|a|(alpha))(\d+)?)?'
               r'(?P<revision>\+[A-Za-z0-9]+)?$')
SRC_DIR = os.path.dirname(os.path.abspath(__file__))


def check_version(version):
    '''Sanity check version string

    Version should be well-formed, larger than current version and not already
    exist
    '''
    if not re.match(VERSION_FMT, version):
        raise ValueError(f'Invalid version: {version}')


@total_ordering
class Version:
    def __init__(self, string='', version_tuple=None):
        pre = None
        rev = None

        if string:
            if string.startswith('v'):
                string = string[1:]

            match = re.match(VERSION_FMT, string)
            if not match:
                raise ValueError(f'Invalid version: {string}')
            self.major = int(match.group('major'))
            self.minor = int(match.group('minor'))
            self.micro = int(match.group('micro'))
            pre = match.group('prerelease')
            if pre is not None:
                if pre.startswith('b'):
                    self.prerelease_type = 'b'
                    prerelease_number = pre.strip('beta').strip('b')
                elif pre.startswith('a'):
                    self.prerelease_type = 'a'
                    prerelease_number = pre.strip('alpha').strip('a')

                if prerelease_number:
                    self.prerelease_number = int(prerelease_number)
                else:
                    self.prerelease_number = 0
            else:
                self.prerelease_type = 'r'
                self.prerelease_number = 0
            rev = match.group('revision')
        else:
            self.major = version_tuple[0]
            self.minor = version_tuple[1]
            self.micro = version_tuple[2]
            if len(version_tuple) > 3:
                self.prerelease_type = version_tuple[3]
                self.prerelease_number = version_tuple[4]
            else:
                self.prerelease_type = 'r'
                self.prerelease_number = 0
            if len(version_tuple) > 5:
                rev = version_tuple[5]

        self.revision = None
        if rev is not None:
            self.revision = rev.strip('+')

    def _prerelease_string(self):
        if self.prerelease_type in ('a', 'b'):
            fmt = '{prefix}{prerelease}'
            return fmt .format(prefix=self.prerelease_type,
                               prerelease=self.prerelease_number)
        return ''

    def __str__(self):
        fmt = '{major}.{minor}.{micro}{beta}{rev}'

        if self.revision:
            rev = '+{}'.format(self.revision)
        else:
            rev = ''

        return fmt.format(major=self.major,
                          minor=self.minor,
                          micro=self.micro,
                          beta=self._prerelease_string(),
                          rev=rev)

    def __eq__(self, other):
        return str(self) == str(other)

    @property
    def version_tuple(self):
        return (self.major, self.minor, self.micro, self.prerelease_type,
                self.prerelease_number, self.revision)

    def __gt__(self, other):
        if self.version_tuple[:5] == other.version_tuple[:5]:
            return (self.version_tuple[5] is None and
                    other.version_tuple[5] is not None)
        else:
            return self.version_tuple[:5] > other.version_tuple[:5]


def get_last_version():
    '''Get last version from git tags'''
    proc = subprocess.run(['git', 'tag'], universal_newlines=True,
                          stdout=subprocess.PIPE)
    tags = proc.stdout.splitlines()
    newest = Version(version_tuple=(0, 0, 0))
    for tag in tags:
        try:
            version = Version(string=tag)
        except ValueError:
            continue

        if version > newest:
            newest = version

    return version


def get_git_root():
    proc = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                          universal_newlines=True, stdout=subprocess.PIPE)
    return proc.stdout.strip()


def get_current_version(path, pattern):
    git_root = get_git_root()
    with open(os.path.join(git_root, path)) as file_:
        for line in file_.readlines():
            match = re.search(pattern, line)
            if match:
                return Version(string=match.group("release"))


def check_versions(last_version, current_version, release):
    'Check last, current, next versions are in order'
    print('Last version:', last_version)
    print('Current version:', current_version)
    print('New version:', release)
    if last_version > current_version:
        raise Exception('Current version older than last version. '
                        'Working from old branch?')
    if release < current_version:
        raise Exception('Requested release not newer than current version.')


def replace_string(filepath, regex, replacement):
    pattern = re.compile(regex)
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_file:
        with open(filepath) as src_file:
            for line in src_file:
                match = pattern.search(line)
                if match:
                    new_line = (line[:match.start('release')] +
                                str(replacement) +
                                line[match.end('release'):])
                    tmp_file.write(new_line)
                else:
                    tmp_file.write(line)

    shutil.copystat(filepath, tmp_file.name)
    shutil.move(tmp_file.name, filepath)


def update_version(release, version_strings):
    'Update repo contents for new release and commit changes'
    check_git_clean()

    git_root = get_git_root()
    for file_spec in version_strings:
        path = os.path.join(git_root, file_spec['path'])
        replace_string(path, file_spec['pattern'], release)

        subprocess.run(['git', 'add', path], check=True)

    if not git_clean(cached=True):
        msg = 'Version {}'.format(release)
        subprocess.run(['git', 'commit', '-m', msg], check=True)
    tag = 'v{}'.format(release)
    subprocess.run(['git', 'tag', tag], check=True)


def git_clean(cached=False):
    cmd = ['git', 'diff', '--quiet']
    if cached:
        cmd.append('--cached')
    proc = subprocess.run(cmd)
    return proc.returncode == 0


def check_git_clean():
    if not git_clean():
        raise Exception('Git state not clean when it should be.')


def build(release):
    orig_dir = os.path.abspath(os.curdir)
    git_root = get_git_root()
    os.chdir(git_root)
    subprocess.run(['make', 'clean'], check=True)
    subprocess.run(['make'], check=True)
    os.chdir(orig_dir)


def github_release(release, user, repo, token, assets):
    api_url = 'https://api.github.com/repos/{user}/{repo}/releases'
    api_url = api_url.format(user=user, repo=repo)

    def get_release_json():
        tag_url = api_url + '/tags/{release}'.format(release=release)
        req = requests.get(tag_url)
        release_json = req.json()
        if ('message' in release_json and
                release_json['message'] == 'Not Found'):
            return False
        return release_json

    release_json = get_release_json()

    with open(os.path.join(get_git_root(), token)) as token_file:
        token = token_file.read().strip()

    if not release_json:
        headers = {'Authorization': 'token {}'.format(token)}
        req = requests.post(api_url,
                            json={'tag_name': release},
                            headers=headers)
        req.raise_for_status()
        release_json = get_release_json()

    for file_ in assets:
        upload_url = expand(release_json['upload_url'],
                            {'name': os.path.basename(file_['path'])})
        headers = {'Content-Type': file_['type'],
                   'Authorization': 'token {}'.format(token)}
        req = requests.post(upload_url, headers=headers,
                            data=open(os.path.join(get_git_root(),
                                                   file_['path']), 'rb'))
        req.raise_for_status()


def push_release(release, config):
    subprocess.run(['git', 'push'])
    subprocess.run(['git', 'push', '--tags'])
    if 'git_release' in config:
        subprocess.run(['git', 'push', config['git_release']['remote'],
                        'HEAD:{}'.format(config['git_release']['branch'])])
    if 'github' in config:
        github_release('v{}'.format(release), **config['github'])


def update_to_alpha(release, version_strings):
    new_release = Version(version_tuple=(release.major,
                                         release.minor,
                                         release.micro+1,
                                         'a',
                                         1))
    git_root = get_git_root()
    for file_spec in version_strings:
        if file_spec.get('skip_alpha'):
            continue
        path = os.path.join(git_root, file_spec['path'])
        replace_string(path, file_spec['pattern'], new_release)
        subprocess.run(['git', 'add', path], check=True)

    msg = 'Bump version to beta {}'.format(new_release)
    subprocess.run(['git', 'commit', '-m', msg], check=True)
    subprocess.run(['git', 'push'])


def parse_args():
    '''Parse command line arguments'''
    parser = argparse.ArgumentParser('Mark git release')
    parser.add_argument('--release', '-r', required=True,
                        help='Release version string')
    parser.add_argument('--config', '-c', default='config.yaml',
                        help='Config file', required=True)

    return parser.parse_args()


def main():
    '''Main logic'''
    args = parse_args()

    with open(args.config) as file_:
        config = yaml.load(file_, Loader=yaml.SafeLoader)
    try:
        from pykwalify.core import Core
        core = Core(source_data=config,
                    schema_files=[os.path.join(SRC_DIR, "config_schema.yaml")])
        core.validate(raise_exception=True)
    except ImportError:
        # No validation
        pass

    # Get versions
    last_version = get_last_version()
    current_version = \
        get_current_version(config['version_strings'][0]['path'],
                            config['version_strings'][0]['pattern'])
    release = Version(args.release)
    check_versions(last_version, current_version, release)

    update_version(release, config['version_strings'])

    build(release)

    push_release(release, config)

    update_to_alpha(release, config['version_strings'])


if __name__ == '__main__':
    main()
