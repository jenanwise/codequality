import atexit
import commands
import os
import re
import tempfile


scmhandlers = {}


def register(name):
    """
    Decorator to register a class as a scmhandler for name.
    """
    def decorator(clazz):
        scmhandlers[name] = clazz
        return clazz
    return decorator


class SCMHandler(object):
    def srcs_to_check(self, paths, rev=None):
        """ Yields (filename, src path to check) for relevant paths at rev.

        What is "relevant" and how to interpret "rev" are determined by
        sub-classes.

        "filename" and "src path to check" may be different because the path
        to src may not exist on disk at the given filename anymore -- for
        example, if the revision refers to an old version.  In such cases,
        "filename" functions as a display name, and impelementing classes must
        provide a path on the filesystem that can be used to check the source
        (the `temp_filename()` function can be used for this).

        Ideally we would pass around pipes, but many code-checking external
        tools expect files and won't work with streams.
        """
        # Sub-classes must implement this method
        raise NotImplementedError()


class NoSCMHandler(SCMHandler):
    """
    Simple no-scm handler. Checks all paths provided.
    """
    def srcs_to_check(self, paths, rev=None):
        for path in sorted(paths):
            yield (path, path)


class GitError(Exception):
    """
    Unexpected git error.
    """


@register('git')
class GitHandler(SCMHandler):
    """
    Git-integration handler.

    When used, and no paths are provided, paths to check will be automatically
    determined by either a specified revision or the current working directory.

    Note that only paths underneath the current working directory will be used,
    even for historical revisions.
    """
    # Begin public API

    def srcs_to_check(self, limit_paths, rev=None, ignore_untracked=False):
        rev = self._resolve_rev(rev)

        relative_paths = self._add_and_modified_in_rev(rev) \
            if rev else self._add_and_modified_in_working_copy(
                ignore_untracked)

        if limit_paths:
            relative_paths = set(relative_paths).intersection(limit_paths)

        for path in sorted(relative_paths):
            if rev:
                yield (
                    path,
                    _temp_filename(self._file_contents(path, rev=rev)))
            else:
                yield (path, path)

    # End public API

    GIT_COMMIT_FMT = r'(?P<commit>[0-9a-f]{40})'
    GIT_COMMIT_RE = re.compile(GIT_COMMIT_FMT)
    GIT_DIFF_SUMMARY_RE = re.compile(
        r'^ (?P<type>\w+) mode (?P<mode>\w+) (?P<path>.+)')
    GIT_SUBMODULE_MODE = 160000

    def _add_and_modified_in_working_copy(self, ignore_untracked=False):
        inside_work_tree = \
            self._git_cmd('rev-parse --is-inside-work-tree') == 'true'
        if not inside_work_tree:
            raise GitError('Not inside a work tree. Use --rev option.')

        result = []

        prefix_from_repo_root = self._git_cmd('rev-parse --show-prefix')

        # `git status --porcelain` gives output in format "XY PATH",
        # where X and Y refer to staged vs unstaged statuses.
        #
        # However, we don't care about staged vs unstaged. We just want to know
        # which files have been changed or created, so for simplicity we use
        # `git status` to ask "what has possibly changed" and then ask the
        # filesystem which files from that list still exist.
        #
        # Note that we use "." at the end of the status command to limit
        # paths to those under the current working directory.
        if ignore_untracked:
            untracked = "no"
        else:
            untracked = "all"
        cmd = 'status --porcelain --untracked-files={untracked} .'.format(
                untracked=untracked)
        status_output = self._git_cmd(cmd)

        for line in status_output.splitlines():
            path = line[3:]

            # For renames, we just care about new filename
            if ' -> ' in path:
                path = path.split(' -> ', 1)[1]

            path = path[len(prefix_from_repo_root):]

            if os.path.isfile(path):
                result.append(path)

        return result

    def _add_and_modified_in_rev(self, rev):
        result = []

        cmd = ' '.join((
            'whatchanged',
            '-r',
            '--max-count=1',
            '--ignore-submodules',
            '--pretty=format:""',
            '--abbrev=40',  # no truncating commit ids
            '--diff-filter="AM"',
            '--name-status',
            '--relative',
            '--no-renames',  # rename = D + A, but we only care about A
            rev,
        ))
        whatchanged_output = self._git_cmd(cmd).strip()

        for line in whatchanged_output.splitlines():
            status, path = line.split(None, 1)
            if status not in "AM":
                raise ValueError('Unexpected "%s" output: %s' % (cmd, line))
            result.append(path)

        return result

    def _file_contents(self, path, rev=None):
        """
        Get content of `path` at `rev`.

        If `rev` is None, the current working version is returned.
        """
        rev = self._resolve_rev(rev)
        prefix_from_repo_root = self._git_cmd('rev-parse --show-prefix')
        if not rev:
            with open(path) as fp:
                result = ''.join(fp)
            return result
        else:
            path = os.path.join(prefix_from_repo_root, path)
            result = self._git_cmd('show %s:"%s"' % (rev, path))
            # `git show` messes with blank lines at ends of files,
            # so we have to append our own for non-empty files
            if result:
                result = result + '\n'
            return result

    def _resolve_rev(self, rev):
        """
        Resolve rev to a standard commit fmt to be matched in `git blame`.
        """
        if not rev:
            return None

        result = self._git_cmd('rev-parse %s' % rev)
        if not self.GIT_COMMIT_RE.match(result):
            raise GitError(
                '"%s" does not appear to be a commit.' % result)
        return result

    def _git_cmd(self, cmd):
        """
        Git git cmd in subprocess and return output.

        Raises: GitError on any error output.
        """
        status, output = commands.getstatusoutput('git %s' % cmd)
        if status:
            raise GitError('"%s" failed:\n%s' % (cmd, output))
        return output

_files_to_cleanup = []


def _temp_filename(contents):
    """
    Make a temporary file with `contents`.

    The file will be cleaned up on exit.
    """
    fp = tempfile.NamedTemporaryFile(
        prefix='codequalitytmp', delete=False)
    name = fp.name
    fp.write(contents)
    fp.close()
    _files_to_cleanup.append(name)
    return name


def _cleanup():
    for path in _files_to_cleanup:
        os.remove(path)
atexit.register(_cleanup)
