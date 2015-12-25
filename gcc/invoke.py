# Currently used only by tarball_build.py

# System
import sys
import argparse
import os, os.path, stat
import re
if sys.version_info[0] < 3:
    import cStringIO as io
else:
    import io

# Packages
import sh

FAMILY_GCC      = 'GCC'
FAMILY_CLANG    = 'Clang'

FRONTEND_C      = 'C'
FRONTEND_CXX    = 'C++'
FRONTEND_LTO    = 'LTO'
FRONTEND_GO     = 'GO'


class InvocationParams(object):
    TK_PREPROCESSED = 'PREPROC'
    TK_ASSEMBLY     = 'ASM'
    TK_OBJECT_CODE  = 'OBJECT'
    TK_EXECUTABLE   = 'EXE'

    DIALECT_C89     = 'c89'
    DIALECT_C99     = 'c99'
    DIALECT_C11     = 'c11'
    DIALECT_CXX98   = 'c++98'
    DIALECT_CXX11   = 'c++11'
    DIALECT_CXX14   = 'c++14'
    DIALECT_CXX1Z   = 'c++1z'

    def __init__(self, source, target_kind):
        pass


class CompilerInvoker(object):
    def __init__(self, path):
        self._conf = None
        self._path = path
        self._cmd = sh.Command(path)

    @property
    def frontend(self):
        return self._frontend

    @property
    def base_version(self):
        return self._version

    @property
    def base_version_str(self):
        return '.'.join([str(x) for x in self.base_version])

    @property
    def full_version_str(self):
        if self.build_str:
            return '{0} ({1})'.format(self.base_version_str, self.build_str)
        return self.base_version_str + ' release'

    def _get_cmd_output(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        self._cmd(*args, _out=stdout, _err=stderr)
        result = (stdout.getvalue(), stderr.getvalue())
        stdout.close()
        stderr.close()
        return result

    def compile(self, source, args, need_output = False):
        if not need_output:
            args.append

    @property
    def configuration(self):
        if self._conf is None:
            self._conf = self._get_cmd_output(['-v'])[1].strip()
        return self._conf

    def __repr__(self):
        return '{0} {1}, {2} FE'.format(self.family, self.full_version_str, self.frontend)


class GCCInvoker(CompilerInvoker):
    _FULL_VER_RE = re.compile(r'^(gcc|g\+\+)\s+\(GCC\)\s+([0-9\.]+)(?:\s+(\d+))?.*$')

    def __init__(self, path):
        CompilerInvoker.__init__(self, path)
        ver = self._cmd('--version')
        lines = ver.split('\n')
        m = GCCInvoker._FULL_VER_RE.match(lines[0])
        self._frontend = FRONTEND_C if m.group(1) == 'gcc' else FRONTEND_CXX
        self._version = [int(x) for x in m.group(2).split('.')]
        self._date = ''
        if m.group(3) is not None:
            self._date = m.group(3)

    def compile(path, dialect):
        return

    @property
    def family(self):
        return FAMILY_GCC

    @property
    def build_str(self):
        return self._date

    @property
    def date(self):
        return self._date

class ClangInvoker(CompilerInvoker):
    _FULL_VER_RE = re.compile(r'clang version\s+([0-9.]+)\s\((.*)\).*$')
    def __init__(self, path):
        CompilerInvoker.__init__(self, path)
        ver = self._cmd('--version')
        lines = ver.split('\n')
        m = ClangInvoker._FULL_VER_RE.match(lines[0])
        self._version = [int(x) for x in m.group(1).split('.')]
        self._frontend = FRONTEND_C if os.path.basename(path) == 'clang' else FRONTEND_CXX
        self._revision = m.group(2)
        if self._revision.endswith('/final'):
            self._revision = ''

    @property
    def family(self):
        return FAMILY_CLANG

    @property
    def build_str(self):
        return self._revision

class CompilerList:
    def __init__(self):
        self._compilers = []
        self._bin_names = re.compile(r'^(gcc|g\+\+|clang).*$')
        self._gcc_re = re.compile(r'^(gcc|g\+\+)\s\(GCC\).*$')
        self._clang_re = re.compile(r'^clang\s.*$')

    def _check_dir(env, self, path):
        con = env
        bin_path = os.path.join(path, 'bin')
        if not os.path.isdir(bin_path):
            return
        for name in os.listdir(bin_path):
            full_path = os.path.join(bin_path, name)
            if os.path.isfile(full_path) and os.access(full_path, os.X_OK) and \
                                                self._bin_names.match(name):
                cmd = sh.Command(full_path)
                try:
                    ver = cmd('--version')
                    lines = ver.split('\n')
                    line1 = lines[0].strip()
                    compiler = None
                    if self._gcc_re.match(line1):
                        compiler = GCCInvoker(full_path)
                    elif self._clang_re.match(line1):
                        compiler = ClangInvoker(full_path)

                    if compiler:
                        con.ok('Found: {0}'.format(compiler))
                        con.info(compiler.configuration + '\n')
                except sh.ErrorReturnCode:
                    continue

    def discover_versions(env, self, search_paths):
        con = env
        if isinstance(search_paths, str):
            search_paths = [ search_paths ]
        for path in search_paths:
            norm_path = os.path.normpath(path)
            if not os.path.isdir(norm_path):
                con.warn("Directory '{0}' does not exist!".format(norm_path))
            for name in os.listdir(norm_path):
                full_path = os.path.realpath(os.path.join(norm_path, name))
                if not os.path.isdir(full_path):
                    continue
                if 'gcc' in name or 'clang' in name:
                    con.info("Checking '{0}'".format(full_path))
                    self._check_dir(full_path)
    @property
    def comilers(self):
        return self._compilers[:]

    @property
    def get_by_family(self, family):
        return [comp for comp in self._compilers if comp.family == family]

    @property
    def gcc_compilers(self):
        return self.get_by_family(FAMILY_GCC)

    @property
    def llvm_compilers(self):
        return self.get_by_family(FAMILY_CLANG)
