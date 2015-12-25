#!/usr/bin/env python

# System
import ftplib
import argparse
import sys, os, os.path
import shutil
import subprocess
import multiprocessing
import re
import tarfile

# Local
from gcc.common import print_exception, dict_to_struct
import gcc.build
from gcc.invoke import GCCInvoker
from gcc.env import Environment

env = Environment()
con = env
try:
    # FIXME: This code should be inside main (and cfg should be passed as
    # parameter instead of being global).
    from config import cfg
except:
    env.fatal_error('config.py not found. Please create config.py '
                    '(see config.py.example)')

fname_re = re.compile(r'^gcc-([0-9.]+)-(\d{4})(\d{2})(\d{2}).tar.bz2$')

pjoin = os.path.join
pexists = os.path.exists

def update_symlink(args, ver, tarball):
    local_path = pjoin(args.snapdir, tarball)
    symlink = pjoin(args.snapdir, 'gcc-{}-latest.tar.bz2'.format(ver))
    if pexists(symlink):
        os.unlink(symlink)
    con.info('Setting symlink "{}" -> "{}"'.format(symlink, local_path))
    os.symlink(local_path, symlink)

def get_prefix_for_gcc_snapshot_ver(ver):
    ver_num = [int(v) for v in ver.split('.')]
    if ver_num[0] < 5:
        return 'gcc-{0[0]}.{0[1]}-latest'.format(ver_num)
    else:
        return 'gcc-{}-latest'.format(ver_num[0])

def make_fname(ver, date):
    return 'gcc-{0}-{1[0]:04}{1[1]:02}{1[2]:02}.tar.bz2'.format(ver, date)

def make_release_fname(ver):
    if isinstance(ver, list):
        ver = '.'.join([int(v) for v in ver])
    return 'gcc-{}.tar.bz2'.format(ver)

def date_of(fname):
    match = fname_re.match(fname)
    if match:
        return tuple([int(match.group(i)) for i in range(2, 5)])
    return None

def version_of(fname):
    match = fname_re.match(fname)
    if match:
        return match.group(1)
    return None

def ensure_path(path):
    if not pexists(path):
        os.makedirs(path)

def catch_errors(func):
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except ftplib.all_errors as ex:
            print_exception(env, ex, 'FTP error')
        except Exception as ex:
            print_exception(env, ex)
        else:
            return
        sys.exit(1)

    return wrapper

def build_and_install(args, ver, tarball):
    bld_args = { }
    # FIXME: caller should pass prefix
    if args.versions:
        # Building release
        bld_args['prefix'] = 'gcc-' + ver
    else:
        # Building weekly snapshots
        bld_args['prefix'] = get_prefix_for_gcc_snapshot_ver(ver)

    if args.fdo:
        bld_args['prefix'] += '-fdo'
        bld_args['build_type'] = 'fdo'
    else:
        bld_args['build_type'] = 'bootstrap'
        if not args.checking:
            bld_args['prefix'] += '-rel'    # -rel = "Release"
    bld_args['install'] = True
    bld_args['install_dir'] = args.dest
    bld_args['build_dir'] = args.build_dir
    bld_args['languages'] = gcc.build.default_lang + [gcc.build.OBJC,
                                                      gcc.build.FORTRAN]
    ver_num = [int(v) for v in ver.split('.')]
    if ver_num[0] >= 5:
        bld_args['languages'].append(gcc.build.JIT)
    bld_args['multilib'] = True
    bld_args['isl'] = cfg.libs_dir
    bld_args['checking'] = 'yes' if args.checking else 'release'
    bld_args['jobs'] = multiprocessing.cpu_count()
    bld_args['debug'] = False
    con.info('Extracting {} to {}'.format(tarball, args.source_dir))
    if os.path.isdir(args.source_dir):
        shutil.rmtree(args.source_dir)
    os.makedirs(args.source_dir)
    tar = tarfile.open(tarball)
    tar.extractall(args.source_dir)
    con.ok('Extracted files from ' + tarball)
    lst = os.listdir(args.source_dir)
    if len(lst) != 1 or not os.path.isdir(pjoin(args.source_dir, lst[0])):
        raise Exception('Unexpected tarball contents: ' + str(lst))
    bld_args['source_dir'] = pjoin(args.source_dir, lst[0])
    args = dict_to_struct(bld_args)
    builder = gcc.build.GCCBuilder(env)
    builder.build(args)
    if args.install:
        builder.install(args)

def install_all_snapshots(args, local_snaps):
    print('Checking local GCC versions:')
    local_versions = {}
    for ver in args.branches:
        prefix = get_prefix_for_gcc_snapshot_ver(ver)
        if not args.checking:
            prefix += '-rel'
        localpath = pjoin(args.dest, prefix, 'bin', 'gcc')
        if not pexists(localpath):
            con.info('File {} does not exist'.format(localpath))
        else:
            gcc = GCCInvoker(localpath)
            date = gcc.date
            (y, m, d) = (int(date[:4]), int(date[4:6]), int(date[6:]))
            con.info('{}, build date: {:02}.{:02}.{:02}'.format(localpath, d, m, y))
            local_versions[ver] = (y, m, d)

    for ver in args.branches:
        if not ver in local_versions or local_snaps[ver] > local_versions[ver]:
            con.info('Locally installed version {} is outdated, rebuilding'.format(ver))
            tarball = pjoin(args.snapdir, make_fname(ver, local_snaps[ver]))
            build_and_install(args, ver, tarball)
        else:
            con.info('Locally installed version is up-to-date')


def update_snapshot(args, ver, tarball):
    full_url = 'ftp://{}/{}/LATEST-{}/{}'.format(args.mirror,
                                                 cfg.remote_snapshot_dir,
                                                 ver, tarball)
    ensure_path(args.snapdir)
    local_path = pjoin(args.snapdir, tarball)
    try:
        env.invoke('wget', full_url, '-O', local_path)
    except:
        if pexists(local_path):
            os.unlink(local_path)
        raise

def update_all_snapshots(args, local_snaps):
    con.info('Connecting to {}'.format(args.mirror))
    need_reconnect = True
    ftp = None
    for ver in args.branches:
        if need_reconnect:
            ftp = ftplib.FTP(args.mirror)
            ftp.login()
            need_reconnect = False
        rdir = '/{}/LATEST-{}'.format(cfg.remote_snapshot_dir, ver)
        con.info('Changing directory to: ' + rdir)
        ftp.cwd(rdir)
        con.info('Getting directory listing')
        files = ftp.nlst()
        tarball = None
        date = None
        for fname in files:
            date = date_of(fname)
            if date:
                tarball = fname
                break
        if not tarball:
            con.warn('Tarball not found on remote server')
            continue
        (y, m, d) = date
        con.info('Remote date of gcc-{}: {:02}.{:02}.{:04}'.format(ver, d, m, y))
        if not ver in local_snaps or date > local_snaps[ver]:
            con.info('Remote snapshot is newer, updating')
            ftp.close()
            need_reconnect = True
            update_snapshot(args, ver, tarball)
            con.ok('Updated successfully')
            local_snaps[ver] = date
        else:
            con.info('Local snapshot is up-to-date')
        update_symlink(args, ver, tarball)

def download_release_tarball(args, ver):
    tarball = make_release_fname(ver)
    full_url = 'ftp://{}/{}/gcc-{}/{}'.format(args.mirror,
        cfg.remote_releases_dir, ver, tarball)
    local_path = pjoin(cfg.tarball_dir, tarball)
    ensure_path(cfg.tarball_dir)
    try:
        env.invoke('wget', full_url, '-O', local_path)
    except:
        if pexists(local_path):
            os.unlink(local_path)
        raise

@catch_errors
def list_versions_on_ftp(args):
    con.info('Connecting to {}'.format(args.mirror))
    ftp = ftplib.FTP(args.mirror)
    ftp.login()
    rdir = cfg.remote_releases_dir
    con.info('Changing directory to: ' + rdir)
    ftp.cwd(rdir)
    con.info('Getting directory listing')
    files = ftp.nlst()
    ftp.close()
    con.ok('Retrieved list of avaialable versions:')
    fname_re = re.compile('gcc-(\d+).(\d+).(\d+)')
    skipped = []
    versions = {}
    for fname in files:
        if fname in ['.', '..']:
            continue
        match = fname_re.match(fname)
        if match:
            ver = [int(x) for x in match.groups()]
        if not match or ver[0] < 4:
            skipped.append(fname)
            continue
        # Number of digits in major part
        major_num = 2 if ver[0] < 5 else 1
        vparts = [ver[0:major_num], ver[major_num:]]
        (major, minor) = ['.'.join([str(p) for p in x]) for x in vparts]
        if major not in versions:
            versions[major] = []
        versions[major].append(minor)
    for major in sorted(versions.keys()):
        all_nums = sorted(['.'.join([major, v]) for v in versions[major]])
        con.info("{}.x:\t\t{}".format(major, ', '.join(all_nums)))
    con.info('Skipped: ' + ', '.join(skipped))

@catch_errors
def update_releases(args):
    for ver in args.versions:
        if not args.no_download:
            con.info('Downloading tarball for v. ' + ver)
            download_release_tarball(args, ver)
            con.ok('Successfully downloaded tarball for v. ' + ver)
        if not args.no_build:
            tarball = pjoin(cfg.tarball_dir, make_release_fname(ver))
            con.info('Building v. ' + ver)
            build_and_install(args, ver, tarball)

@catch_errors
def update_snapshots(args):
    con.info('Local snapshots:')
    local_snaps = {}
    if os.path.isdir(args.snapdir):
        count = 0
        for fname in os.listdir(args.snapdir):
            ver = version_of(fname)
            if ver:
                date = date_of(fname)
                (y, m, d) = date
                con.info('gcc-{}: {:02}.{:02}.{:04}'.format(ver, d, m, y))
                if ver not in local_snaps:
                    local_snaps[ver] = date
                elif date > local_snaps[ver]:
                    old_name = os.path.join(args.snapdir, make_fname(ver, local_snaps[ver]))
                    con.info('Deleting old snapshot: ' + old_name)
                    os.unlink(old_name)
                    local_snaps[ver] = date
                else:
                    full_name = os.path.join(args.snapdir, fname)
                    con.info('Deleting old snapshot: ' + full_name)
                    os.unlink(full_name)
                count += 1
        if not count:
            con.info('(None)')
    else:
        con.info('Snapshot dir "{}" doest not exist, creating'.format(args.snapdir))
        os.makedirs(args.snapdir)

    if not args.no_download:
        update_all_snapshots(args, local_snaps)

    if not args.no_build:
        install_all_snapshots(args, local_snaps)


def main():
    parser = argparse.ArgumentParser()
    default_ver_str = ', '.join(cfg.maintained_branches)
    ver_group = parser.add_mutually_exclusive_group(required=True)
    ver_group.add_argument('-b', '--branch', dest='branches', metavar='VER',
            help='build and install specified GCC branche(s) from snapshots', nargs='*')
    ver_group.add_argument('-v', '--version', dest='versions', metavar='VER',
            help='build and install specified GCC release(s)', nargs='*')
    ver_group.add_argument('-l', '--list', action='store_true',
            help='list versions available on FTP server')
    parser.add_argument('--dest', default=cfg.install_dir,
            help='common install directory (default: %(default)s)')
    parser.add_argument('--build-dir', dest='build_dir', default=cfg.build_dir,
            help='temporary directory used for build (default: %(default)s)')
    parser.add_argument('--extract-dir', dest='source_dir', default=cfg.extract_dir,
            help='temporary directory for sources (default: %(default)s)')
    parser.add_argument('--mirror', default=cfg.ftp_mirror,
            help='FTP mirror hostname (default: %(default)s)')
    parser.add_argument('--snapdir', default=cfg.snapshot_dir,
            help='local directory for snapshot tarballs (default: %(default)s)')
    bld_group = parser.add_mutually_exclusive_group()
    bld_group.add_argument('--checking', action='store_true', dest='checking',
            help='build checking version (by default, "release" version is built)')
    bld_group.add_argument('--fdo', action='store_true',
            help='use profiled bootstrap')
    parser.add_argument('--no-install', action='store_false', dest='install',
            help='Do not install the built compiler')
    dl_group = parser.add_mutually_exclusive_group()
    dl_group.add_argument('--download', action='store_true', dest='no_build',
            help='only download tarballs (do not start the build)')
    dl_group.add_argument('--build', action='store_true', dest='no_download',
            help='build GCC from downloaded tarballs (do not download new ones)')
    args = parser.parse_args()
    if args.list:
        list_versions_on_ftp(args)
    elif args.versions:
        update_releases(args)
    else:
        update_snapshots(args)

if __name__ == '__main__':
    main()
