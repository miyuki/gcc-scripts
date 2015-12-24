# This module implements a layer for interaction with environment
# That is, file system, I/O, process invocation. Can be replaced
# during unit tests

from __future__ import print_function

import os, os.path
import sys, subprocess

class ProcessExec:
    @staticmethod
    def invoke(call_args):
        stdout_buf = sys.stdout
        if sys.version_info[0] == 3:
            stdout_buf = stdout_buf.buffer
        subprocess.check_call(call_args, stdout=stdout_buf,
                            stderr=subprocess.STDOUT)

    @staticmethod
    def invoke_quiet(call_args):
        devnull = os.open(os.devnull, os.O_WRONLY)
        try:
            subprocess.check_call(call_args, stdout=devnull, stderr=devnull)
        except:
            os.close(devnull)
            raise
        os.close(devnull)

class Console:
    COLOR_ALWAYS = 0
    COLOR_AUTO = 1
    COLOR_NEVER = 2

    @staticmethod
    def _make_code(color):
        return "\x1b[1;{}m".format(30+color)

    def __init__(self, coloring_rule=COLOR_ALWAYS):
        BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

        self._coloring_rule = coloring_rule
        self._colored = True
        self._clr = "\x1b[0m"   # Clear

        self._red = Console._make_code(RED)
        self._green = Console._make_code(GREEN)
        self._yellow = Console._make_code(YELLOW)

    @property
    def color(self):
        return self._coloring_rule

    @color.setter
    def color(self, value):
        if value == Console.COLOR_ALWAYS:
            self._colored = True
        elif value == Console.COLOR_AUTO:
            self._colored = sys.stdout.isatty
        elif value == Console.COLOR_NEVER:
            self._colored = False
        else:
            assert(False)
        self._coloring_rule = value

    def _color_line(self, dest, msg, color):
        if self._colored:
            msg = ''.join([color, str(msg), self._clr, '\n'])
        else:
            msg = str(msg) + '\n'
        dest.write(msg)
        dest.flush()

    def _plain_stdout(self, msg):
        sys.stdout.write(str(msg) + '\n')
        sys.stdout.flush()

    def _plain_stderr(self, msg):
        sys.stderr.write(str(msg) + '\n')
        sys.stderr.flush()

    def _color_stdout(self, msg, color):
        self._color_line(sys.stdout, msg, color)

    def _color_stderr(self, msg, color):
        self._color_line(sys.stderr, msg, color)

    def warn(self, message):
        self._color_stderr(message, self._red)

    def info(self, message):
        self._plain_stdout(message)

    def err_info(self, message):
        self._plain_stderr(message)

    def ok(self, message):
        self._color_stdout(message, self._green)

    def alt_ok(self, message):
        self._color_stdout(message, self._yellow)


class Environment:
    def __init__(self, fatal_errors=False):
        self._console = Console()
        self.warn = self._console.warn
        self.ok = self._console.ok
        self.alt_ok = self._console.alt_ok
        self._set_verbosity(2)
        self.err = self._fatal_error if fatal_errors else self.warn
        self.error = self.err
        self.err_info = self._console.err_info
        self.con = self.console

    def _ignore_msg(self, message):
        pass

    def _fatal_error(self, message):
        self._console.warn(message)
        sys.exit(1)

    def _set_verbosity(self, value):
        self._verbosity = value
        self._invoke = ProcessExec.invoke if value == 2 else \
                       ProcessExec.invoke_quiet
        self.info = self._console.info if value >= 1 else self._ignore_msg

    @property
    def console(self):
        return self._console

    @property
    def verbosity(self):
        return self._verbosity

    @verbosity.setter
    def verbosity(self, value):
        assert(isinstance(value, int) and value >= 0 and value <= 2)
        self._set_verbosity(value)

    def invoke(self, *args):
        self._invoke(list(args))

