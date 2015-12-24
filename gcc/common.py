# System
from __future__ import print_function

import sys, subprocess, traceback
import os, time
import re
import math

def dict_to_struct(dct):
    class Struct(object):
        def update(self, other):
            self.__dict__.update(other)
        def copy(self):
            return Struct(**self.__dict__)
        def __init__(self, **entries):
            self.update(entries)
        def __getattr__(self, name):
            return None

    return Struct(**dct)

_ansi_strip = re.compile(r'\x1b[^m]*m')

def strip_ansi_colors(s):
   return _ansi_strip.sub('', s)

class StopWatch:
    class TimeDelta:
        def __init__(self, sec):
            self._ms = math.trunc(sec * 1000)

        @property
        def ms(self):
            return self._ms

        @property
        def sec(self):
            return self._ms / 1000.0

        @property
        def format_sec(self):
            return '{}.{:03}'.format(self._ms / 1000, self._ms % 1000)

        @property
        def format_min(self):
            if self._ms > 60000:
                sec = self._ms / 1000
                return '{}:{:02}.{:03}'.format(sec / 60, sec % 60, self._ms % 1000)
            return self.format_sec

        @property
        def format_hr(self):
            msec = self.msec
            if msec > 3600000:
                sec = msec / 1000
                hr = sec / 3600
                sec = sec % 3600
                return '{}:{:02}:{:02}.{:03}'.format(hr,
                            sec / 60, sec % 60, msec % 1000)
            return self.format_min

        def __repr__(self):
            return 'StopWatch.TimeDelta({})'.format(self_sec)

        def __str__(self):
            return self.format_min


    def __init__(self, start_now=False):
        self._start = None
        self._delta = None
        self._running = False
        if start_now:
            self.start()

    def start(self):
        self._delta = None
        self._start = time.time()
        self._running = True

    def stop(self):
        assert(self._running)
        self._delta = time.time() - self._start
        self._running = False
        return self._delta

    def restart(self):
        assert(self._running)
        now = time.time()
        self._delta = now - self._start
        self._start = now
        return self._delta

    @property
    def delta(self):
        delta_sec = time.time() - self._start if self._running else self._delta
        return StopWatch.TimeDelta(delta_sec)

    @property
    def delta_str(self):
        return self.delta.format_min


def invoke(call_args):
    stdout_buf = sys.stdout
    if sys.version_info[0] == 3:
        stdout_buf = stdout_buf.buffer
    subprocess.check_call(call_args, stdout=stdout_buf,
                          stderr=subprocess.STDOUT)

def print_exception(env, ex, msg=None, skip_frames=1):
    bt_limit = 20
    if msg is None:
        if isinstance(ex, KeyboardInterrupt):
            msg = '\nInterrupted by user'
        elif isinstance(ex, subprocess.CalledProcessError):
            prog = os.path.basename(ex.cmd[0])
            msg = 'Program "{}" returned ' \
                  'non-zero exit status {}"'.format(prog, ex.returncode)
        else:
            msg = str(ex)
    env.error(msg)
    tp, _, tb = sys.exc_info()
    frames = traceback.extract_tb(tb, bt_limit + skip_frames)
    env.err_info('Notice: exception of type "{}" raised from:'.format(tp.__name__))
    paths = [p[0] for p in reversed(frames[1:]) if not p[0].startswith(sys.prefix)]
    common_pref = os.path.dirname(os.path.commonprefix(paths))
    for (fname, line, func, text) in reversed(frames[1:]):
        if fname.startswith(sys.prefix):
            continue
        relname = os.path.relpath(fname, common_pref)
        if func == '<module>':
            env.err_info('  {}:{}:'.format(relname, line))
        else:
            env.err_info('  function "{}" in {}:{}'.format(func, relname, line))
        env.info('    ' + text)
    if len(frames) > bt_limit:
        env.err_info('  ...')

