import commands
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
    tool_arg_str = ''

    def check(self, path):
        """
        Return list of error dicts for all found errors in path.

        The default implementation expects `tool`, and `tool_err_re` to be
        defined.

        tool: external binary to use for checking.
        tool_err_re: regexp that can match output of `tool` -- must provide
            a groupdict with at least "filename", "lineno", "colno",
            and "msg" keys. See example checkers.
        """
        if not path:
            return ()

        cmd = self.tool
        if self.tool_arg_str:
            cmd += ' %s' % self.tool_arg_str

        return self._check_std(path, cmd)

    # End public API

    def _check_std(self, path, cmd):
        """
        Run `cmd` as a check on `path`.
        """
        status, output = commands.getstatusoutput('%s %s' % (cmd, path))
        result = []
        for line in output.splitlines():
            match = self.tool_err_re.match(line)
            if not match:
                if self.break_on_tool_re_mismatch:
                    raise ValueError(
                        'Unexpected `%s %s` output: %r' % (cmd, path, line))
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
    Checker integration with the nodelint.js tool.

    Sannis' fork is recommended: http://github.com/Sannis/nodelint-js
    """
    tool = 'nodelint.js'

    # Default output format bolds the first part of the line using
    # bash escapes -- hence the "\x1b\[1m" etc.
    # TODO: handle weird filenames
    tool_err_re = re.compile(
        r"\x1b\[1m(?P<filename>[^,]+), "
        r"line (?P<lineno>\d+), character "
        r"(?P<colno>\d+), :\x1b\[0m (?P<msg>.*)")


@register(filetypes=('py',))
class PEP8Checker(Checker):
    """
    Checker integration with the pep8 tool.
    """
    tool = 'pep8'
    tool_arg_str = '--repeat'

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
