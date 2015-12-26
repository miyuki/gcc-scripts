# Bug triage and test-case management

## Some useful external links

* [A Guide to Testcase Reduction](https://gcc.gnu.org/wiki/A_guide_to_testcase_reduction)
* [C-Reduce](https://embed.cs.utah.edu/creduce/). Also available as a package in
Debian:

    `$ sudo apt-get install creduce`

## fortran_delta.pl

[fortran_delta.pl](fortran_delta.pl) is a patched version of
[delta](http://delta.tigris.org/) script adapted to work with Fortran sources,
by Joost VandeVondele. Originally posted on the
[mailing list](https://gcc.gnu.org/ml/gcc/2009-10/msg00618.html).

Run

    $ ./fortran_delta.pl -h

to get help on usage.

## strip_num.py

[strip_num.py](strip_num.py) processes debug dumps of GCC intermediate
representations (produced by `-fdump-tree-...`, `-fdump-ipa-...` options) and
removes numbers (e.g.: SSA names, virtual clone names), which are likely to
change when compiling the same source with slightly different versions of GCC.

This allows to run `diff` on such dumps and still get relevant differences.

## strip_testcase.py

[strip_testcase.py](strip_testcase.py) script can be used to postprocess the
preprocessed :) source code to make it:

* smaller
* compilable on different ISA
* compilable with older versions of GCC

Note that this script may change program semantics, but in some cases (e.g.:
debugging an ICE in the front end) this is OK.

### Examples

Remove blank lines, `#line` directives and pragmas from `in.ii`:

    $ ./strip_testcase.py -b -l -p in.ii > out.ii

Also remove definitions of CPU instrinsics:

    $ ./strip_testcase.py -a in.ii > out.ii
