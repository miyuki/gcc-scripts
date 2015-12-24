# System
from __future__ import print_function

import os, os.path
import shutil, subprocess
import string
import sys, traceback
pjoin = os.path.join

# Packages
import sh

# Local
from .common import StopWatch, print_exception

# === Constants ===

# Build types:
MINIMAL     = 'minimal'
STAGE1      = 'stage1'      # (disable bootstrap)
BOOTSTRAP   = 'bootstrap'
FDO         = 'fdo'         # aka "profiled bootstrap"
COVERAGE    = 'coverage'

# Languages:
C           = 'c'
CXX         = 'c++'
LTO         = 'lto'
OBJC        = 'objc'
OBJCXX      = 'obj-c++'
FORTRAN     = 'fortran'
GO          = 'go'
ADA         = 'ada'
JAVA        = 'java'
JIT         = 'jit'

default_lang    = [C, CXX, LTO]
extra_lang      = [OBJC, FORTRAN, GO, JAVA]
all_lang        = default_lang + extra_lang

class BuildError(Exception): pass
class InternalError(Exception): pass

def read_file(path):
    with open(path, 'rb') as f:
        return '\n'.join([l.strip() for l in f])

def get_isl_ver_for_gcc_ver(ver):
    ver_num = [int(v) for v in ver.split('.')]
    return '0.12.2' if ver_num[0] == 4 else '0.15'

def is_native_build(args):
    return args.target is None

def is_stage1_build(args):
    return args.build_type in [MINIMAL, STAGE1, COVERAGE]

def is_bootstrap(args):
    return args.build_type in [BOOTSTRAP, FDO]

def catch_errors(func):
    def wrapper(self, *args, **kwargs):
        env = self._env
        assert(env is not None)
        try:
            func(self, *args, **kwargs)
        except BuildError as ex:
            print_exception(env, ex, 'Build error: ' + str(ex))
        except InternalError as ex:
            print_exception(env, ex, 'Internal error')
        except Exception as ex:
            print_exception(env, ex)
        else:
            return
        sys.exit(1)

    return wrapper

def cleanup_dir(path):
    for subdir in os.listdir(path):
        full_path = pjoin(path, subdir)
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.unlink(full_path)

class GCCBuilder:
    def __init__(self, environment):
        self._version = None
        self._stopwatch = StopWatch()
        self._buildtime = 0
        self._do_invoke = None
        self._env = environment
        self._script_dir = os.path.normpath(pjoin(os.path.dirname(__file__), '..'))
        site_config = pjoin(self._script_dir, 'configury.stfu')
        self.site_config = site_config if os.path.exists(site_config) else None


    def _common_init(self, args):
        self._env.verbosity = 1 if args.quiet else 2
        self._source_dir = args.source_dir

    def set_source_dir(self, source_dir):
        self._source_dir = source_dir
        return self.version

    def _get_configure_options_native(self, args):
        res = { }
        res['with-fpmath'] = 'sse'
        res['disable-nls'] = True
        res['with-system-zlib'] = True
        res['with-demangler-in-ld'] = True
        res['enable-shared'] = True
        if JIT in args.languages:
            res['enable-host-shared'] = True
        if not args.multilib:
            res['disable-multilib'] = True
        if args.build_type == COVERAGE:
            res['enable-coverage'] = True
        if args.build_type == FDO:
            res['disable-werror'] = True
        if args.valgrind:
            res['enable-valgrind-annotations'] = True
        res['disable-bootstrap'] = is_stage1_build(args)
        return res

    def _get_canonical_name(self, args):
        target = args.target
        config_sub = sh.Command(pjoin(self._source_dir, 'config.sub'))
        con = self._env
        con.info('Getting canonical name for: ' + target)
        name = str(config_sub(target)).strip()
        if not name:
            raise BuildError('config.sub returned empty result')
        con.info('Canonical name: ' + name)
        return name

    def _get_configure_options_cross(self, args):
        res = { }
        res['target'] = self._get_canonical_name(args)
        return res

    def get_prefix(self, args):
        prefix = args.prefix
        if prefix is None:
            prefix = 'gcc-' + self.version
            if not is_native_build(args):
                prefix += '-cross'
            if not args.checking:
                prefix += '-rel'
        return pjoin(args.install_dir, prefix)

    def _get_c_cxx_flags(self, args, add_flags=[]):
        if args.flags is not None:
            return args.flags
        if args.debug:
            return '-Og -ggdb3 -pipe'
        if is_stage1_build(args):
            return '-O2 -g -pipe'
        return ''

    @property
    def version(self):
        if self._version is not None:
            return self._version
        try:
            # Note: self._source_dir must be set before calling version
            self._version = read_file(pjoin(self._source_dir, 'gcc', 'BASE-VER'))
            return self._version
        except:
            raise BuildError('Invalid source directory: gcc/BASE-VER not found')

    def get_configure_options(self, args):
        if is_native_build(args):
            res = self._get_configure_options_native(args)
        else:
            res = self._get_configure_options_cross(args)

        res['prefix'] = self.get_prefix(args)
        langs = args.languages[:]
        if CXX not in langs:
            langs.append(CXX)
        if C not in langs:
            langs.append(C)
        langs_str = ','.join(langs)
        res['enable-languages'] = langs_str
        res['enable-clocale'] = 'gnu'
        res['disable-nls'] = True
        if args.isl is not None:
            isl_dir = 'isl-' + get_isl_ver_for_gcc_ver(self.version)
            res['with-isl'] = pjoin(args.isl, isl_dir)
        if not is_bootstrap(args):
            res['MAKEINFO'] = '/bin/true'
        if args.mem_stats:
            res['enable-gather-detailed-mem-stats'] = True

        checking = args.checking
        assert(checking is not None)
        if isinstance(checking, list):
            checking = ','.join(checking)
        res['enable-checking'] = checking

        if args.cc is not None:
            res['CC'] = args.cc
        if args.cxx is not None:
            res['CXX'] = args.cxx
        if args.assembler is not None:
            res['with-as'] = args.assembler
        flags_str = self._get_c_cxx_flags(args)
        if flags_str:
            res['CFLAGS'] = flags_str
            res['CXXFLAGS'] = flags_str

        if args.config_script:
            path_src = pjoin(self._source_dir, 'config',
                             args.config_script + '.mk')
            if not os.path.exists(path_src):
                path_script = pjoin(self._script_dir, args.config_script + '.mk')
                if not os.path.exists(path_script):
                    raise BuildError(args.config_script + '.mk not found')
                shutil.copyfile(path_script, path_src)
            res['with-build-config'] = args.config_script

        lines = []
        for (k, v) in res.items():
            if v == False:
                continue
            # Convert lower-case stuff (e.g., "prefix") to flags ("--prefix"), but
            # do not modify variables ("CFLAGS"), which are upper-case
            line = k if k[0] in string.ascii_uppercase else '--' + k
            if v != True:
                line += '=' + v
            lines.append(line)

        if self.site_config is not None and not is_bootstrap(args):
            for var in ['build_configargs', 'host_configargs']:
                lines.append('{}=CONFIG_SITE={}'.format(var, self.site_config))

        if args.config_options is not None:
            lines += args.config_options.split()

        return lines

    @catch_errors
    def configure(self, args):
        self._common_init(args)
        con = self._env
        con.ok('Found GCC source tree, version: ' + self.version)
        conf_opt = self.get_configure_options(args)
        os.chdir(args.build_dir)
        con.info('Entering build directory: ' + args.build_dir)
        con.info('Configure options: ' + ' '.join(['\'{}\''.format(opt) if ' ' in opt else opt for opt in conf_opt]))
        self._env.invoke(pjoin(self._source_dir, 'configure'), *conf_opt)

    def _get_make_command(self, args, in_gcc=False, seq=False):
        path = [args.build_dir]
        if in_gcc:
            path.append('gcc')
        path.append('Makefile')
        res = ['-f', pjoin(*path)]
        if not seq and args.jobs > 1:
            res.append('-j' + str(args.jobs))
        return res

    def _make_full(self, args):
        make_args = self._get_make_command(args)
        if args.build_type in [MINIMAL, COVERAGE]:
            make_args.append('all-gcc')
        elif args.build_type == FDO:
            make_args.append('profiledbootstrap')
        self._env.invoke('make', *make_args)

    @catch_errors
    def make(self, args):
        self._common_init(args)
        os.chdir(args.build_dir)
        self._make_full(args)

    @catch_errors
    def build(self, args):
        self._common_init(args)
        con = self._env
        if os.path.exists(args.build_dir):
            con.info('Build directory exists, cleaning')
            cleanup_dir(args.build_dir)
        else:
            os.makedirs(args.build_dir)
        self._stopwatch.start()
        self.configure(args)
        con.info('Configure time: ' + self._stopwatch.delta_str)
        if args.nomake:
            con.ok('Configured successfully')
            self._stopwatch.stop()
        else:
            con.ok('Configured successfully, running make')
            self.make(args)
            self._stopwatch.stop()
            con.ok('Built successfully in ' + self._stopwatch.delta_str)

    @property
    def build_time_str(self):
        return self._stopwatch.delta_str

    @catch_errors
    def install(self, args):
        self._common_init(args)
        con = self._env
        prefix = self.get_prefix(args)
        if os.path.exists(prefix):
            con.info('Install directory already exists. Cleaning up.')
            shutil.rmtree(prefix)
        make_args = self._get_make_command(args, seq=True)
        make_args.append('install')
        self._env.invoke('make', *make_args)
        con.ok('Installed successfully')

