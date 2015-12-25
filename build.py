#!/usr/bin/env python2.7

# System
import sys
import argparse
import multiprocessing
import os.path

# Local
import gcc.build as bld
from gcc.env import Environment

def main():
    env = Environment()
    try:
        from config import cfg
    except:
        env.fatal_error('config.py not found. Please create config.py '
                        '(see config.py.example)')

    DEFAULT_LANG = bld.default_lang[:]
    DEFAULT_LANG_STR = ','.join(DEFAULT_LANG)
    EXTRA_LANG = bld.extra_lang[:]

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-s', '--source', dest='source_dir', help='source directory',
                        default=cfg.source_dir)
    parser.add_argument('-b', '--build', dest='build_dir',
                        help='build directory',
                        default=cfg.build_dir)
    parser.add_argument('--dest', dest='install_dir',
                        help='installation top directory',
                        default=cfg.install_dir)
    parser.add_argument('-g', help='build with more debug information and optimization level -Og',
                        dest='debug', action='store_true')
    parser.add_argument('-j', dest='jobs', default=multiprocessing.cpu_count(),
                        help='number of jobs for make')
    parser.add_argument('--isl', help='path to libisl (one dir above)',
                        dest='isl', default=cfg.libs_dir)
    parser.add_argument('--languages', help='comma-separated list of enabled frontends'
                        ' (default: {}, also available: {})'.format(', '.join(DEFAULT_LANG),
                                                                    ', '.join(EXTRA_LANG)),
                        dest='languages', default=DEFAULT_LANG_STR)
    parser.add_argument('--extra-lang', help='build all supported languages',
                        dest='extra_lang', action='store_true')
    parser.add_argument('--install', help='install after build',
                        dest='install', action='store_true')
    parser.add_argument('--multilib', help='enable multilib configuration',
                        action='store_true')
    checking = parser.add_mutually_exclusive_group()
    checking.add_argument('--checking', default='yes', help='enabled checking types')
    checking.add_argument('--release', help='set checking to release', action='store_true',
                        dest='checking_release')
    parser.add_argument('--valgrind', action='store_true',
                        help='enable valgrind annotations')
    parser.add_argument('--prefix', default=None, help='installation subdirectory'
                        ' (by default, generated from version)')
    build_type = parser.add_mutually_exclusive_group()
    build_type.add_argument('--minimal',
                        help='build stage 1 compilers without libraries',
                        dest='build_type', action='store_const', const=bld.MINIMAL)
    build_type.add_argument('--stage1', help='build without bootstrap',
                        dest='build_type', action='store_const', const=bld.STAGE1)
    build_type.add_argument('--bootstrap', help='build with bootstrap',
                        dest='build_type', action='store_const', const=bld.BOOTSTRAP)
    build_type.add_argument('--coverage', help='build with gcov instrumentation',
                        dest='build_type', action='store_const', const=bld.COVERAGE)
    build_type.add_argument('--fdo', help='build with profiled bootstrap',
                        dest='build_type', action='store_const', const=bld.FDO)
    build_type.add_argument('--cc1', action='store_const', dest='build_type',
                        const=bld.C, help='build the C compiler proper')
    build_type.add_argument('--cc1plus', action='store_const', dest='build_type',
                        const=bld.CXX, help='build the C++ compiler proper')
    build_type.add_argument('--lto1', action='store_const', dest='build_type',
                        const=bld.LTO, help='build the LTO compiler proper')
    build_type.add_argument('--f951', '--fortran', action='store_const',
                        dest='build_type', const=bld.FORTRAN,
                        help='build the Fortran compiler proper')
    parser.set_defaults(build_type=cfg.default_build)
    parser.add_argument('--target', help='target architecture for cross-compiler',
                        dest='target')
    parser.add_argument('--config-options', help='addittional options for'
                        ' configure script', dest='config_options')
    parser.add_argument('--config-script', help='additional script which'
                        ' configure will run', dest='config_script')
    parser.add_argument('--no-make', '--nomake', '--configure',
                        action='store_true', dest='nomake',
                        help='only run "configure" script (do not run "make")')
    parser.add_argument('--cc', help='C compiler (stage 0).'
                        ' By default use system compiler')
    parser.add_argument('--cxx', help='C++ compiler (stage 0).'
                        ' By default use system compiler')
    parser.add_argument('--gcc', help='C/C++ compiler (stage 0) bin directory.'
                        ' If specified, gcc and g++ found in that directory will be used')
    parser.add_argument('--as', help='assembler to use',
                        default=cfg.assembler, dest='assembler') # Argh, 'as' is a keyword
    parser.add_argument('--flags', help='Flags for stage0 (C and C++), by default will use '
                        '"-pipe" and add normal flags for selected build type, '
                        '"-pipe -Og -ggdb3" for debug build (-g)')
    parser.add_argument('--mem-stats', help='Enable memory statistics',
                        action='store_true', dest='mem_stats')
    parser.add_argument('-q', '--quiet', dest='quiet', action='store_true',
                        help='Do not copy configure/make output to stdout')
    args = parser.parse_args()

    # Adjust "checking" level
    if args.checking_release:
        args.checking = 'release'

    if args.build_type in bld.all_lang:
        if args.languages != DEFAULT_LANG_STR:
            parser.error('languages argument is not compatible with '
                         'single-frontend build')
        args.languages = [args.build_type]
        args.build_type = bld.MINIMAL
    elif args.languages != DEFAULT_LANG_STR:
        if args.extra_lang:
            parser.error('--extra-lang argument is not compatible with custom '
                         '--languages list')
        langs = args.languages.split(',')
        if not len(langs):
            parser.error('empty languages list')
        for lang in langs:
            if lang not in DEFAULT_LANG and lang not in EXTRA_LANG:
                parser.error('invalid language: ' + lang)
        args.languages = langs
    else:
        langs = DEFAULT_LANG[:]
        if args.extra_lang:
            langs += EXTRA_LANG
        args.languages = langs

    # Set build type for cross-compiler
    if args.target is not None and args.build_type not in [bld.MINIMAL, bld.STAGE1]:
        args.build_type = bld.MINIMAL # Override default value

    # Stage 0 compiler
    if args.gcc is not None:
        if args.cc is not None or args.cxx is not None:
            parser.error('--gcc option is incompatible with --cc and --cxx')
        args.cc = os.path.join(args.gcc, 'gcc')
        args.cxx = os.path.join(args.gcc, 'g++')
    elif cfg.stage0_gcc is not None:
        if args.cc is None:
            args.cc = os.path.join(cfg.stage0_gcc, 'gcc')
        if args.cxx is None:
            args.cxx = os.path.join(cfg.stage0_gcc, 'g++')
    if args.cc is not None and not os.path.exists(args.cc):
        parser.error('C compiler "{}" not found'.format(args.cc))
    if args.cxx is not None and not os.path.exists(args.cxx):
        parser.error('C++ compiler "{}" not found'.format(args.cxx))

    builder = bld.GCCBuilder(env)
    builder.build(args)
    if args.install:
        builder.install(args)

if __name__ == '__main__':
    main()
