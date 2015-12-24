# Various scripts related to GCC development

## Prerequisites and configuration

The scripts require [sh](https://amoffat.github.io/sh/) python package
(interface for subprocess module). Installation on Debian-like distributions:

    $ sudo apt-get install -y python-pip
    $ sudo pip install sh

Various options (such as path to your GCC working tree) as configured via
`config.py` script. Use [config.py.example](config.py.example) as a boilerplate
to create your own configuration, i.e.

    $ cp config.py.example config.py
    $ vim config.py

## build.py

[build.py](build.py) is a shortcut for running GCC build from scratch.
Essentially it runs configure and make with various commonly used options.

### Usage examples

Build the compiler proper for C and C++ languages (native):

    $ ./build.py

Same for aarch64-linux target:

    $ ./build.py --target aarch64-linux

Build debuggable version of the compiler (-Og -ggdb3):

    $ ./build.py -g

Bootstrap and install GCC to `/opt` (edit `config.py` to change default path):

    $ ./build.py --bootstrap --install

Run profiled bootstrap with --enable-checking="release":

    $ ./build.py --release --fdo

Also build and install fortran and libgccjit:

    $ ./build.py --languages=c,c++,lto,fortran,jit --bootstrap --install
