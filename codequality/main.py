#!/usr/bin/env python
"""
Simple code checking metatool.

codequality is glue around multiple external code checking tools. Its goal
is easy integration with editing environments and version control (scm) tools.

All output follows a simple parseable format:

    filename:linenumber:columnnumber: message

where the column number is optional (some external tools don't provide it).
This makes it easy to integrate with editing environments.

Examples:

    codequality foo.py bar.js

Theo above run all relevant available external checkers against foo.py and
bar.js.  Relevance is determined currently by file extensions -- checkers are
registered against known file extensions.  See --list-checkers.

    codequality

Theo above check all files it can under the current working directory.

    codequality --ignore "*junk/*"

Theo above will check all files under the current working directory
except those that match the fnmatch pattern "*junk/*".

    codequality --scm git

Using the --scm option will pass responsibility of determining files
to check to your scm of choice (currently only git is supported).
In the case of the git handler, this means all modified files in the
working copy.

    codequality --scm git --rev HEAD

All scm handlers can take a --rev flag. In the case of git, the above
will check all relevant files created or modified (not deleted) in the
last-committed patch. This works well as a post-commit hook.
"""
import commands
import fnmatch
import optparse
import os
import sys

import checkers
import scmhandlers


class CommandError(Exception):
    pass


class CodeQuality(object):
    # Begin public API

    def __init__(self, options):
        self.options = options

    def codequality(self, paths):
        if self.options.list_checkers:
            self._list_checkers()
            return

        # If an scm handler is specified and no paths are given, we let
        # the scm handler choose paths -- otherwise, we default to
        # the current working directory.
        if not paths and not self.options.scmhandler:
            paths = ['.']

        if self.options.scmhandler \
                and self.options.scmhandler not in scmhandlers.scmhandlers:
            raise CommandError(
                'no registered scm handler for "%s".'
                % self.options.scmhandler)

        paths = self._resolve_paths(*paths)
        scmhandler = scmhandlers.scmhandlers.get(
            self.options.scmhandler,
            scmhandlers.NoSCMHandler)()
        errors_exist = False

        for filename, src in scmhandler.srcs_to_check(
                paths, rev=self.options.rev):

            if self.options.verbose:
                if src == filename:
                    print >> sys.stderr, \
                        'Checking "%s"...' % (filename,)
                else:
                    print >> sys.stderr, \
                        'Checking "%s" using path "%s"...' % (filename, src)

            errors_exist = self._check(filename, src) or errors_exist
        return errors_exist

    # End public API

    out_fmt = '%(filename)s:%(lineno)d:%(colno)s: %(msg)s'
    out_fmt_with_checker = '%(checker)s:' + out_fmt

    def _relevant_checkers(self, path):
        """
        Get set of checkers for the given path.

        TODO: currently this is based off the file extension.  We would like to
        honor magic bits as well, so that python binaries, shell scripts, etc
        but we're not guarunteed that `path` currently exists on the filesystem
        -- e.g. when version control for historical revs is used.
        """
        _, ext = os.path.splitext(path)
        ext = ext.lstrip('.')
        return checkers.checkers.get(ext, [])

    def _resolve_paths(self, *paths):
        """
        Resolve paths into a set of filenames (no directories) to check.

        External tools will handle directories as arguments differently, so for
        consistancy we just want to pass them filenames.

        This method will recursively walk all directories and filter out
        any paths that mach self.options.ignores.
        """
        result = set()
        for path in paths:
            if os.path.isdir(path):
                for dirpath, _, filenames in os.walk(path):
                    for filename in filenames:
                        path = os.path.join(dirpath, filename)
                        if path.startswith('.'):
                            path = path[1:].lstrip('/')
                        if not self._should_ignore(path):
                            result.add(path)
            else:
                result.add(path)
        return result

    def _list_checkers(self):
        """
        Print information about checkers and their external tools.

        Currently only works properly on systems with the `which` tool
        available.
        """
        classes = set()
        for checker_group in checkers.checkers.itervalues():
            for checker in checker_group:
                classes.add(checker)

        max_width = 0
        for clazz in classes:
            max_width = max(max_width, len(clazz.tool), len(clazz.__name__))

        for clazz in sorted(classes):
            status, _ = commands.getstatusoutput('which %s' % clazz.tool)
            result = 'missing' if status else 'installed'
            print '%s%s%s' % (
                clazz.__name__.ljust(max_width + 1),
                clazz.tool.ljust(max_width + 1),
                result)

    def _should_ignore(self, path):
        """
        Return True iff path should be ignored.
        """
        for ignore in self.options.ignores:
            if fnmatch.fnmatch(path, ignore):
                return True
        return False

    def _check(self, filename, src_path):
        """
        Check filename using src_path against all relevant code checkers.

        Returns True iff any errors were found.
        """
        errors_exist = False
        checker_classes = self._relevant_checkers(filename)
        for checker_class in checker_classes:
            checker = checker_class()
            errs = checker.check(src_path)
            for err in errs:
                errors_exist = True
                if self.options.list_matching_files:
                    print filename
                    return True
                err.update(
                    checker=checker.__class__.__name__,
                    filename=filename)
                fmt = self.out_fmt_with_checker \
                    if self.options.show_checker else self.out_fmt
                print fmt % err
        return errors_exist


def main():
    parser = optparse.OptionParser(
        usage="%%prog [--options] [<path>..]\n\n%s" % __doc__.strip(),
    )
    parser.add_option(
        '--scm', dest='scmhandler', default=None,
        help='SCM to use to choose which lines and files to check. '
            'Currently only "git" is supported.',
    )
    parser.add_option(
        '-i', '--ignore', dest='ignores',
        action='append', default=[], metavar='PATTERN',
        help='fnmatch pattern to ignore.',
    )
    parser.add_option(
        '--list', dest='list_matching_files',
        action='store_true', default=False,
        help='Just list filenames that have errors, '
            'not the errors themselves.',
    )
    parser.add_option(
        '--list-checkers', dest='list_checkers',
        action='store_true', default=False,
        help='List installed checkers and their external tools.',
    )
    parser.add_option(
        '--show-checker', dest='show_checker',
        action='store_true', default=False,
        help='Show checker used at beginning of each error '
            'line, before the filename.',
    )
    parser.add_option(
        '-r', '--rev', dest='rev',
        action='store', default=None,
        help='Revision to pass to scm tool. Used with --scm. '
            'If not specified, the current pending changes will '
            'be used, as determined by the scm tool specified.',
    )
    parser.add_option(
        '--verbose', dest='verbose',
        action='store_true', default=False,
        help='Prints extra information to stderr.',
    )

    options, paths = parser.parse_args()

    try:
        errs = CodeQuality(options).codequality(paths)
        if errs:
            return 1
    except CommandError, e:
        print >> sys.stderr, 'Error: %s' % e
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
