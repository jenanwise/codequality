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

    All paths are always limited to those in `git ls-files`, so untracked and
    `gitignore`ed files will never be checked.
    """
    # Begin public API

    def srcs_to_check(self, paths, rev=None):
        rev = self._resolve_rev(rev)
        commit_range = '%s^ %s' % (rev, rev) if rev else 'HEAD'

        paths = self._paths_to_check(paths, commit_range=commit_range)
        path_types = self._get_path_types(commit_range=commit_range)

        for filename, src in self._srcs(paths, path_types, rev):
            yield filename, src

    # End public API

    GIT_COMMIT_FMT = r'(?P<commit>[0-9a-f]{40})'
    GIT_COMMIT_RE = re.compile(GIT_COMMIT_FMT)
    GIT_DIFF_SUMMARY_RE = re.compile(
        r'^ (?P<type>\w+) mode (?P<mode>\w+) (?P<path>.+)')
    GIT_SUBMODULE_MODE = 160000

    def _file_contents(self, path, rev=None):
        """
        Get content of `path` at `rev`.

        If `rev` is None, the current working version is returned.
        """
        rev = self._resolve_rev(rev)
        if not rev:
            with open(path) as fp:
                result = ''.join(fp)
            return result
        else:
            path = self._path_from_repo_root(path)
            # `git show` messes with blank lines at ends of files,
            # so we have to append our own for non-empty files
            result = self._git_cmd('show %s:"%s"' % (rev, path))
            if result:
                result = result + '\n'
            return result

    def _path_from_repo_root(self, path):
        return os.path.join(self._git_cmd('rev-parse --show-prefix'), path)

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

    def _paths_to_check(self, paths, commit_range):
        """
        Collect paths to check if none specified manually.

        commit_range: string that can be passed as args to `git diff` and
        similar commands to represent a commit range, e.g. "HEAD" or
        "af939d0c^^ af939d0c".
        """
        # `git diff --name-only` gives paths relative to the root
        # of the repository, but we want paths relative to the current
        # directory.  Making "." the path arg to `git diff` will limit
        # paths to everything under the current directory, and then
        # we can just strip the prefix from each path.
        if not paths:
            paths = self._git_cmd('diff --name-only %s -- .'
                % (commit_range,)).splitlines()
            prefix = self._git_cmd('rev-parse --show-prefix')
            paths = [path[len(prefix):] for path in paths]
        paths = [path for path in paths if path in set(
            self._git_cmd('ls-files').splitlines())]
        return paths

    def _get_path_types(self, commit_range):
        """
        Collect a map of path to modification type.

        Modification type is a string 'create', 'delete', 'rename', etc, parsed
        from the output of `git diff --summary`.
        """
        result = {}
        summary = self._git_cmd(
            'diff --summary %s' % (commit_range,)).splitlines()
        for line in summary:
            match = self.GIT_DIFF_SUMMARY_RE.match(line)
            if not match:
                raise GitError(
                    'unexpected `git diff --summary` output: "%s"' % line)
            match_dict = match.groupdict()
            result[match_dict['path']] = match_dict['type']

        return result

    def _mode(self, path, rev):
        """
        Get git "mode" of a path at a given rev.

        The mode is git's numeric way of identifying the type of an object in
        its tree.
        """
        return int(
            self._git_cmd('ls-tree "%s" "%s"' % (rev, path)).split(' ')[0])

    def _srcs(self, paths, path_types, rev):
        """
        Yield (filename, path to src of filename at rev) for relevant paths.
        """
        for path in paths:
            type = path_types.get(path, None)

            # Ignore submodules
            if self._mode(path, rev) == self.GIT_SUBMODULE_MODE:
                continue

            # No type means it was a regular change
            if type in (None, 'create', 'rename'):
                yield (
                    path,
                    _temp_filename(self._file_contents(path, rev=rev)))

            # Don't need to check deletes
            elif type == 'delete':
                continue

            else:
                raise ValueError('Unexpected change type: %s' % type)


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
