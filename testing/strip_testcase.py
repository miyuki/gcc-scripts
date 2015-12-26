#!/usr/bin/env python2.7

import os, os.path
import argparse
import sys
import re

# Strip linemarkers, pragmas and definitions of CPU intrinsics with declarations.

# This script might be useful for minimization of testcases related to C++ frontend bugs
# In some cases one might want to compile the testcase with a different version of
# GCC or another compiler (e.g., to produce valid code after reduction by creduce/delta/...)
# This might require some tweaking of testcase.
# This script is able to:
# * remove linemarkers
# * remove #pragma's
# * remove blank lines
# * replace definitions of CPU intrinsics with declarations
# * replace __is_trivially_xable(...) with "1" - to make the source parsable by GCC 4.9

include_re = re.compile(r'^#\s+\d+\s+".*"[ 0-9]+$')
intrin_include_re = re.compile(r'^#\s+\d+\s+".*/include/[a-z0-9]+'
                                '(?:intrin|3dnow)\.h"[ 0-9]*$')
enum_re = re.compile(r'^\s*(?:typedef\s+)?enum\s+[a-zA-Z0-9_]*\s*$')
trivially_re = re.compile(r'__is_trivially_(?:copyable|assignable|constructible)\s*\([^)]*\)')

def make_strip_re(args):
    """Returns a regular expression for line markers, pragmas or
    blank lines (or a combination of them - depending on args)"""
    re_list = []
    if args.blank:
        # Strip blank lines
        re_list.append(r'\s*')
    if args.line_markers:
        # Strip line markers:
        # #line ...
        # #<n>
        re_list.append(r'\s*#\s*line.*')
        re_list.append(r'\s*#\s*\d+\s*".*')
    if args.pragmas:
        re_list.append(r'\s*#\s*pragma.*')
    if not re_list:
        return None
    line_re_str = '^(?:' + '|'.join(re_list) + ')$'
    return re.compile(line_re_str)

def strip_trivially(line):
    return trivially_re.sub('1', line)

def strip_other(args, src):
    """Strip all stuff specified in args, except intrinsics"""
    line_re = make_strip_re(args)
    for line in src:
        if line_re is not None and line_re.match(line):
            continue
        if args.triv_copy:
            line = strip_trivially(line)
        yield line

def safe_match(regex, line):
    if regex is None:
        return None
    return regex.match(line)

def strip_intrin(args, src):
    include = False
    after_enum = False
    brace_balance = 0
    for line in src:
        m = intrin_include_re.match(line)
        if include:
            if include_re.match(line):
                yield line
                include = bool(m)
            else:
                if brace_balance > 0:
                    brace_balance += line.count('{') - line.count('}')
                else:
                    if '{' in line and not after_enum:
                        brace_balance = line.count('{') - line.count('}')
                        yield ';\n'
                    else:
                        yield line
                    after_enum = bool(enum_re.match(line))
        else:
            brace_balance = 0
            yield line
            include = bool(m)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--blank', action='store_true',
                        help='strip blank lines')
    parser.add_argument('-l', '--line-markers', action='store_true',
                        help='strip line markers (#line ...)')
    parser.add_argument('-p', '--pragmas', action='store_true',
                        help='strip #pragma directives')
    parser.add_argument('-i', '--intrin', action='store_true',
                        help='replace definitions of CPU intrinsics with declarations')
    parser.add_argument('-a', '--all', action='store_true',
                        help='all of above')
    parser.add_argument('-t', '--triv-copy', action='store_true',
                        help='replace __is_trivially_copyable/assignable/... '
                        'with 1 (for GCC 4.9 compat.)')
    parser.add_argument('input', metavar='INPUT', type=argparse.FileType('r'),
                        help='input file name')
    parser.add_argument('-o', '--output',
                        metavar='OUTPUT', type=argparse.FileType('w'),
                        default=sys.stdout,
                        help='output file name (stdout, if omitted)')
    args = parser.parse_args()
    if args.all:
        args.blank = True
        args.line_markers = True
        args.pragmas = True
        args.intin = True
    if not args.blank and not args.line_markers \
            and not args.pragmas and not args.triv_copy \
            and not args.intrin:
        parser.error('no actions specified')
    generator = strip_intrin(args, args.input) if args.intrin else args.input
    for line in strip_other(args, generator):
        args.output.write(line)


if __name__ == '__main__':
    main()
