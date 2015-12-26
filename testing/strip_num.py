#!/usr/bin/env python2

import sys
import re

def main():
    if len(sys.argv) != 2:
        sys.stderr.write('Usage: strip_num.py FILE')
        sys.exit(1)
    hex_re = re.compile(r'(?<=@0x)[0-9a-f]+')
    num_re = re.compile(r'(/|\.(?:constprop|part|isra|D)\.)\d+')
    with open(sys.argv[1], 'rb') as f:
        for line in f:
            line = hex_re.sub('[..]', line)
            line = num_re.sub(r'\1[..]', line)
            sys.stdout.write(line)

if __name__ == '__main__':
    main()
