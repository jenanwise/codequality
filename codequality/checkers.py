from subprocess import PIPE
from subprocess import Popen
import re


checkers = {}


def register(filetypes):
    """
    Decorator to register a class as a checker for extensions.
    """
    def decorator(clazz):
        for ext in filetypes:
            checkers.setdefault(ext, []).append(clazz)
        return clazz
    return decorator


class Checker(object):
    """
    Base class for all src checker handlers.

    For simple external tools, subclasses can just overwrite the `tool`, and
    `tool_err_re` class-level variables.  If more complicated checking is
    needed, the `check()` method should be overwritten.
    """
    # Begin public API

    # Subclasses must overwrite these to use the standard `check()` method.
    tool = None
    tool_err_re = None

    # Optional
    break_on_tool_re_mismatch = False
    tool_args = []

    def check(self, paths):
        """
        Return list of error dicts for all found errors in paths.

        The default implementation expects `tool`, and `tool_err_re` to be
        defined.

        tool: external binary to use for checking.
        tool_err_re: regexp that can match output of `tool` -- must provide
            a groupdict with at least "filename", "lineno", "colno",
            and "msg" keys. See example checkers.
        """
        if not paths:
            return ()

        cmd_pieces = [self.tool]
        cmd_pieces.extend(self.tool_args)
        return self._check_std(paths, cmd_pieces)

    @classmethod
    def get_version(cls):
        """
        Return the version number of the tool.
        """
        cmd_pieces = [cls.tool, '--version']
        process = Popen(cmd_pieces, stdout=PIPE, stderr=PIPE)
        out, err = process.communicate()
        if err:
            return ''
        else:
            return out.splitlines()[0].strip()

    # End public API

    def _check_std(self, paths, cmd_pieces):
        """
        Run `cmd` as a check on `paths`.
        """
        cmd_pieces.extend(paths)
        process = Popen(cmd_pieces, stdout=PIPE, stderr=PIPE)
        out, err = process.communicate()
        lines = out.strip().splitlines() + err.strip().splitlines()
        result = []
        for line in lines:
            match = self.tool_err_re.match(line)
            if not match:
                if self.break_on_tool_re_mismatch:
                    raise ValueError(
                        'Unexpected `%s` output: %r' % (
                            ' '.join(cmd_pieces),
                            paths,
                            line))
                continue
            vals = match.groupdict()

            # All tools should at least give us line numbers, but only
            # some give column numbers.
            vals['lineno'] = int(vals['lineno'])
            vals['colno'] = \
                int(vals['colno']) if vals['colno'] is not None else ''

            result.append(vals)
        return result


# Simple builtin checkers


@register(filetypes=('js',))
class NodelintChecker(Checker):
    """
    Checker integration with the nodelint tool.

    tav's repo is recommended: http://github.com/tav/nodelint
    """
    tool = 'nodelint'
    tool_args = ['--reporter=vim']

    # For some reason the vim reporter output doesn't put a space after the
    # filename. Example:
    #
    # foo.jsline 1 column 1 Error: 'x' was used before it was defined. x = y
    tool_err_re = re.compile(r"""
        (?P<filename>.+)
        line\ (?P<lineno>\d+)
        \ column\ (?P<colno>\d+)
        \ (?P<msg>.*)
    """, re.VERBOSE)


@register(filetypes=('py',))
class PEP8Checker(Checker):
    """
    Checker integration with the pep8 tool.
    """
    tool = 'pep8'
    tool_args = ['--repeat']

    # TODO: handle weird filenames
    tool_err_re = re.compile(r"""
        (?P<filename>[^:]+):
        (?P<lineno>\d+):
        (?:(?P<colno>\d+):)?
        \ (?P<msg>.*)
    """, re.VERBOSE)


@register(filetypes=('py',))
class PyflakesChecker(Checker):
    """
    Checker integration with the pyflakes tool.
    """
    tool = 'pyflakes'

    # TODO: handle weird filenames
    tool_err_re = re.compile(r"""
        (?P<filename>[^:]+):
        (?P<lineno>\d+):
        (?:(?P<colno>\d+):)?
        \ (?P<msg>.*)
    """, re.VERBOSE)

    @classmethod
    def get_version(cls):
        cmd_pieces = [
            'python', '-c', "import pyflakes; print pyflakes.__version__"]
        process = Popen(cmd_pieces, stdout=PIPE, stderr=PIPE)
        out, err = process.communicate()
        if err:
            return ''
        else:
            return out.splitlines()[0].strip()
